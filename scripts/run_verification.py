"""
LG-4 系统性验证脚本：环境探针 + 离线 pytest + 终态语义场景 + 本机 API 冒烟。

用法（项目根目录）:
  .\\.venv\\Scripts\\python.exe scripts\\run_verification.py

产出:
  doc/records/artifacts/verification-latest.json
  控制台摘要；exit 0 表示离线层全部通过（live 失败只记 SKIP/FAIL 不拖垮主结论，除非 --strict-live）
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "doc" / "records" / "artifacts"
ARTIFACT_JSON = ARTIFACT_DIR / "verification-latest.json"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def _http_get(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return True, f"HTTP {resp.status}: {body[:300]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _http_post_json(url: str, payload: dict, timeout: float = 120.0) -> tuple[bool, str, dict | None]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return True, f"HTTP {resp.status}", json.loads(raw)
            except json.JSONDecodeError:
                return True, f"HTTP {resp.status} non-json: {raw[:300]}", None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {body[:500]}", None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


def probe_env() -> dict[str, Any]:
    targets = {
        "api_8200": "http://127.0.0.1:8200/health",
        "qwen_18000": "http://127.0.0.1:18000/v1/models",
        "mcp_8090": "http://127.0.0.1:8090/ping",
    }
    out: dict[str, Any] = {}
    for name, url in targets.items():
        ok, detail = _http_get(url)
        out[name] = {"ok": ok, "url": url, "detail": detail}
    return out


def ensure_api() -> dict[str, Any]:
    ok, detail = _http_get("http://127.0.0.1:8200/health")
    if ok:
        return {"action": "reuse", "ok": True, "detail": detail}

    # 尝试后台启动
    log_path = ARTIFACT_DIR / "api-startup.log"
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            [str(PYTHON), "-m", "app.main"],
            cwd=str(ROOT),
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
    for _ in range(20):
        time.sleep(0.5)
        ok, detail = _http_get("http://127.0.0.1:8200/health")
        if ok:
            return {
                "action": "started",
                "ok": True,
                "pid": proc.pid,
                "detail": detail,
                "log": str(log_path),
            }
    return {
        "action": "started",
        "ok": False,
        "pid": proc.pid,
        "detail": detail,
        "log": str(log_path),
    }


def run_pytest_offline() -> dict[str, Any]:
    cmd = [
        str(PYTHON),
        "-m",
        "pytest",
        "-q",
        "tests/test_ending.py",
        "tests/test_phase0_scaffold.py",
        "tests/test_phase1_manus_graph.py",
        "tests/test_phase2_mcp_loader.py",
        "tests/test_phase3_api.py",
        # CE-6 search / semantic_search / prompt routing
        "tests/test_search_chunking.py",
        "tests/test_search_bm25.py",
        "tests/test_search_embedding.py",
        "tests/test_search_hybrid.py",
        "tests/test_search_tool.py",
        "tests/test_ce6_prompt_graph.py",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout": (proc.stdout or "")[-2000:],
        "stderr": (proc.stderr or "")[-1000:],
    }


def run_semantic_scenarios() -> dict[str, Any]:
    """假模型覆盖三种终态 + summarize。"""
    sys.path.insert(0, str(ROOT))
    from langchain_core.messages import AIMessage

    from app.manus import run_manus
    from app.tools.local_tools import get_phase1_tools
    from tests.test_phase1_manus_graph import ScriptedChatModel

    tools = get_phase1_tools()
    cases: list[dict[str, Any]] = []

    # completed
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="add",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 2, "b": 3},
                        "id": "a1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="done",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"outcome": "success", "reason": "sum ok"},
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="2 加 3 等于 5。"),
        ]
    )
    out = run_manus("计算 2+3", model=model, max_steps=5, tools=tools)
    cases.append(
        {
            "name": "completed_add_terminate",
            "ok": out["status"] == "completed"
            and "5" in out["answer"]
            and out.get("end_reason") == "sum ok"
            and any("summarize" in x for x in out["step_logs"]),
            "status": out["status"],
            "end_reason": out.get("end_reason"),
            "answer_preview": (out.get("answer") or "")[:120],
        }
    )

    # abandoned
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="give up",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"outcome": "abandon", "reason": "缺少搜索工具"},
                        "id": "t2",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="抱歉，当前缺少搜索工具，无法完成。"),
        ]
    )
    out = run_manus("搜索今日新闻", model=model, max_steps=3, tools=tools)
    cases.append(
        {
            "name": "abandoned_terminate",
            "ok": out["status"] == "abandoned" and bool(out.get("answer")),
            "status": out["status"],
            "end_reason": out.get("end_reason"),
            "answer_preview": (out.get("answer") or "")[:120],
        }
    )

    # budget_exceeded
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="loop1",
                tool_calls=[
                    {"name": "echo", "args": {"text": "a"}, "id": "e1", "type": "tool_call"}
                ],
            ),
            AIMessage(
                content="loop2",
                tool_calls=[
                    {"name": "echo", "args": {"text": "b"}, "id": "e2", "type": "tool_call"}
                ],
            ),
            AIMessage(content="已达到步数上限，任务未完成。"),
        ]
    )
    out = run_manus("空转", model=model, max_steps=2, tools=tools)
    cases.append(
        {
            "name": "budget_exceeded",
            "ok": out["status"] == "budget_exceeded" and bool(out.get("answer")),
            "status": out["status"],
            "end_reason": out.get("end_reason"),
            "answer_preview": (out.get("answer") or "")[:120],
        }
    )

    return {"ok": all(c["ok"] for c in cases), "cases": cases}


def run_api_smoke(env: dict[str, Any]) -> dict[str, Any]:
    api = env.get("api_8200") or {}
    if not api.get("ok"):
        return {"ok": False, "skipped": False, "detail": "API not up"}

    ok, detail = _http_get("http://127.0.0.1:8200/health")
    health = {"ok": ok, "detail": detail}

    live = {"attempted": False, "ok": False, "detail": "", "body": None}
    if (env.get("qwen_18000") or {}).get("ok"):
        live["attempted"] = True
        pok, pdetail, body = _http_post_json(
            "http://127.0.0.1:8200/agent/run",
            {
                "message": "请调用 add 计算 1+1，然后 terminate，outcome=success，reason=done",
                "max_steps": 6,
            },
            timeout=180,
        )
        live["ok"] = bool(
            pok
            and body
            and body.get("answer")
            and body.get("status")
            in {"completed", "abandoned", "budget_exceeded", "finished", "error"}
        )
        live["detail"] = pdetail
        if body:
            live["body"] = {
                "status": body.get("status"),
                "end_reason": body.get("end_reason"),
                "answer_preview": str(body.get("answer") or "")[:200],
                "steps": body.get("steps"),
            }
    else:
        live["detail"] = "SKIP: Qwen tunnel :18000 down"

    return {"ok": health["ok"], "health": health, "live_agent_run": live}


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    report: dict[str, Any] = {
        "title": "LG-4 verification",
        "started_at": started,
        "project": str(ROOT),
    }

    report["ensure_api"] = ensure_api()
    report["env"] = probe_env()
    report["pytest_offline"] = run_pytest_offline()
    report["semantic_scenarios"] = run_semantic_scenarios()
    report["api_smoke"] = run_api_smoke(report["env"])

    offline_ok = bool(report["pytest_offline"]["ok"] and report["semantic_scenarios"]["ok"])
    api_ok = bool(report["api_smoke"]["ok"])
    live = report["api_smoke"]["live_agent_run"]
    live_ok = (not live.get("attempted")) or bool(live.get("ok"))

    report["summary"] = {
        "offline_ok": offline_ok,
        "api_health_ok": api_ok,
        "live_ok_or_skipped": live_ok,
        "overall_pass_for_lg4": offline_ok and api_ok,
        "notes": [],
    }
    if not (report["env"].get("qwen_18000") or {}).get("ok"):
        report["summary"]["notes"].append("本机 Qwen 隧道 :18000 不可用，真模型 POST 已跳过")
    if not (report["env"].get("mcp_8090") or {}).get("ok"):
        report["summary"]["notes"].append("MCP :8090/ping 不可用（离线语义测试不依赖 MCP）")

    report["finished_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    ARTIFACT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"artifact: {ARTIFACT_JSON}")
    return 0 if report["summary"]["overall_pass_for_lg4"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
