"""CA-7 各题执行逻辑（离线假模型 + 真模型 live）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from langchain_core.messages import AIMessage

from app.config import get_settings
from app.graph.checkpointing import reset_checkpointer_singleton_for_tests
from app.hitl.policy import HitlDecision, classify_tool_call
from app.manus import iter_manus_events, iter_manus_hitl_resume, run_manus
from app.tasks.store import reset_task_store_singleton_for_tests
from app.tools.loader import load_agent_tools
from evals.ca7.cases import EvalResult
from tests.test_context_resume_stream import HistoryAwareModel
from tests.test_phase1_manus_graph import ScriptedChatModel


def _tmp_env(hitl: bool, checkpoint: bool) -> tuple[Path, Path]:
    """创建临时工作区+库，并清 settings 缓存。须由调用方 os.environ 已设好。"""
    root = Path(tempfile.mkdtemp(prefix="ca7_"))
    db = root / "ck.sqlite"
    # 环境变量由 run_ca7 在外部 monkeypatch 风格设置；此处只返回路径
    return root, db


def _reset_singletons() -> None:
    get_settings.cache_clear()
    reset_checkpointer_singleton_for_tests()
    reset_task_store_singleton_for_tests()


def run_e1_add_terminate(**kwargs) -> EvalResult:
    """E1：假模型 add→terminate→summarize。"""
    import os

    root = Path(tempfile.mkdtemp(prefix="ca7_e1_"))
    os.environ["WORKSPACE_ROOT"] = str(root)
    os.environ["HITL_ENABLED"] = "false"
    os.environ["CHECKPOINT_ENABLED"] = "false"
    _reset_singletons()
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
                        "args": {"outcome": "success", "reason": "ok"},
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="2+3=5"),
        ]
    )
    out = run_manus(
        "计算 2+3 然后结束",
        model=model,
        max_steps=6,
        tools=load_agent_tools(persist_long_results=False),
        use_checkpoint=False,
        persist_event_log=False,
    )
    ok = out.get("status") == "completed" and "5" in (out.get("answer") or "")
    return EvalResult(
        "E1_add_terminate",
        "假模型：add 后 terminate",
        ok,
        detail=f"status={out.get('status')} steps={out.get('steps')} answer={out.get('answer')!r}",
        metrics={"steps": out.get("steps"), "status": out.get("status")},
    )


def run_e2_hitl_approve_write(**kwargs) -> EvalResult:
    """E2：HITL 批准写文件。"""
    import os

    root = Path(tempfile.mkdtemp(prefix="ca7_e2_"))
    db = root / "ck.sqlite"
    os.environ["WORKSPACE_ROOT"] = str(root)
    os.environ["HITL_ENABLED"] = "true"
    os.environ["CHECKPOINT_ENABLED"] = "true"
    os.environ["CHECKPOINT_SQLITE_PATH"] = str(db)
    _reset_singletons()
    tools = load_agent_tools(persist_long_results=False)
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="w",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"path": "outputs/ca7_e2.txt", "content": "ca7-e2-ok"},
                        "id": "w1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="t",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"outcome": "success", "reason": "written"},
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="已写入。"),
        ]
    )
    ev1 = list(
        iter_manus_events(
            "写 ca7_e2",
            model=model,
            max_steps=8,
            tools=tools,
            use_checkpoint=True,
            persist_event_log=False,
        )
    )
    before = (root / "outputs" / "ca7_e2.txt").exists()
    tid = ev1[0]["thread_id"]
    hitl = ev1[-1].get("type") == "hitl_required"
    ev2 = list(
        iter_manus_hitl_resume(
            tid, decision="approve", model=model, tools=tools, persist_event_log=False
        )
    )
    path = root / "outputs" / "ca7_e2.txt"
    after_ok = path.is_file() and path.read_text(encoding="utf-8") == "ca7-e2-ok"
    done = ev2[-1].get("type") == "done" and ev2[-1].get("status") == "completed"
    ok = (not before) and hitl and after_ok and done
    return EvalResult(
        "E2_hitl_approve_write",
        "假模型：HITL 批准写文件",
        ok,
        detail=f"hitl={hitl} before_exists={before} after_ok={after_ok} done={done}",
    )


def run_e3_hitl_reject_write(**kwargs) -> EvalResult:
    """E3：HITL 拒绝写文件。"""
    import os

    root = Path(tempfile.mkdtemp(prefix="ca7_e3_"))
    db = root / "ck.sqlite"
    os.environ["WORKSPACE_ROOT"] = str(root)
    os.environ["HITL_ENABLED"] = "true"
    os.environ["CHECKPOINT_ENABLED"] = "true"
    os.environ["CHECKPOINT_SQLITE_PATH"] = str(db)
    _reset_singletons()
    tools = load_agent_tools(persist_long_results=False)
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="w",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"path": "outputs/ca7_e3.txt", "content": "nope"},
                        "id": "w1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="用户拒绝了，不再写入。"),
            AIMessage(content="未写入文件。"),
        ]
    )
    ev1 = list(
        iter_manus_events(
            "写文件",
            model=model,
            max_steps=8,
            tools=tools,
            use_checkpoint=True,
            persist_event_log=False,
        )
    )
    tid = ev1[0]["thread_id"]
    ev2 = list(
        iter_manus_hitl_resume(
            tid,
            decision="reject",
            note="no",
            model=model,
            tools=tools,
            persist_event_log=False,
        )
    )
    exists = (root / "outputs" / "ca7_e3.txt").exists()
    done = ev2[-1].get("type") == "done"
    ok = (not exists) and done
    return EvalResult(
        "E3_hitl_reject_write",
        "假模型：HITL 拒绝写文件",
        ok,
        detail=f"exists={exists} last={ev2[-1].get('type')} status={ev2[-1].get('status')}",
    )


def run_e4_shell_blacklist(**kwargs) -> EvalResult:
    """E4：黑名单策略。"""
    v = classify_tool_call(
        "run_shell", {"command": "rm -rf /tmp/x"}, hitl_enabled=True
    )
    ok = v.decision == HitlDecision.HARD_DENY
    return EvalResult(
        "E4_shell_blacklist",
        "策略：shell 黑名单 hard_deny",
        ok,
        detail=v.reason,
    )


def run_e5_context_resume(**kwargs) -> EvalResult:
    """E5：续聊上下文（HistoryAwareModel）。"""
    import os

    root = Path(tempfile.mkdtemp(prefix="ca7_e5_"))
    db = root / "ck.sqlite"
    os.environ["WORKSPACE_ROOT"] = str(root)
    os.environ["HITL_ENABLED"] = "false"
    os.environ["CHECKPOINT_ENABLED"] = "true"
    os.environ["CHECKPOINT_SQLITE_PATH"] = str(db)
    _reset_singletons()
    tools = load_agent_tools(persist_long_results=False)
    m1 = HistoryAwareModel()
    ev1 = list(
        iter_manus_events(
            "你好我叫郁皓宇",
            model=m1,
            max_steps=5,
            tools=tools,
            use_checkpoint=True,
            persist_event_log=False,
        )
    )
    tid = ev1[0]["thread_id"]
    m2 = HistoryAwareModel()
    ev2 = list(
        iter_manus_events(
            "我叫什么名字",
            model=m2,
            max_steps=5,
            tools=tools,
            thread_id=tid,
            use_checkpoint=True,
            persist_event_log=False,
        )
    )
    ok = m2.saw_name_in_history and "郁皓宇" in (ev2[-1].get("answer") or "")
    return EvalResult(
        "E5_context_resume",
        "假模型：同 thread 续聊记名字",
        ok,
        detail=f"saw_name={m2.saw_name_in_history} answer={ev2[-1].get('answer')!r}",
    )


def _probe_qwen() -> str | None:
    """探测本机 Qwen 隧道；成功返回 None，失败返回错误文案。禁用系统代理（与 llm.py 一致）。"""
    import httpx

    try:
        with httpx.Client(trust_env=False, timeout=8.0) as client:
            client.get("http://127.0.0.1:18000/v1/models").raise_for_status()
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def run_e6_live_chat(**kwargs) -> EvalResult:
    """E6：真模型短问答（无工具）。"""
    import os

    err = _probe_qwen()
    if err:
        return EvalResult(
            "E6_live_chat",
            "真模型：短问答冒烟",
            False,
            detail=f"Qwen 18000 不可用: {err}",
        )

    root = Path(tempfile.mkdtemp(prefix="ca7_e6_"))
    os.environ["WORKSPACE_ROOT"] = str(root)
    os.environ["HITL_ENABLED"] = "false"
    os.environ["CHECKPOINT_ENABLED"] = "false"
    _reset_singletons()
    out = run_manus(
        "用一句话回答：1+1等于几？不要调用工具。",
        max_steps=4,
        tools=load_agent_tools(persist_long_results=False),
        use_checkpoint=False,
        persist_event_log=False,
    )
    ans = (out.get("answer") or "").strip()
    ok = out.get("status") not in {"error"} and len(ans) > 0 and (
        "2" in ans or "两" in ans
    )
    return EvalResult(
        "E6_live_chat",
        "真模型：短问答冒烟",
        ok,
        detail=f"status={out.get('status')} steps={out.get('steps')} answer={ans[:120]!r}",
        metrics={"steps": out.get("steps"), "status": out.get("status")},
    )


def run_e7_live_write_no_hitl(**kwargs) -> EvalResult:
    """E7：真模型写文件（关 HITL，避免人工打断评测）。"""
    import os

    err = _probe_qwen()
    if err:
        return EvalResult(
            "E7_live_write_no_hitl",
            "真模型：关 HITL 写文件",
            False,
            detail=f"Qwen 18000 不可用: {err}",
        )

    root = Path(tempfile.mkdtemp(prefix="ca7_e7_"))
    os.environ["WORKSPACE_ROOT"] = str(root)
    os.environ["HITL_ENABLED"] = "false"
    os.environ["CHECKPOINT_ENABLED"] = "false"
    _reset_singletons()
    out = run_manus(
        "请只用 write_file 把文本 ca7-live-e7 写入 outputs/ca7_e7.txt，"
        "成功后 terminate，outcome=success。不要跑 shell。",
        max_steps=10,
        tools=load_agent_tools(persist_long_results=False),
        use_checkpoint=False,
        persist_event_log=False,
    )
    path = root / "outputs" / "ca7_e7.txt"
    content_ok = path.is_file() and "ca7-live-e7" in path.read_text(encoding="utf-8")
    ok = content_ok and out.get("status") in {"completed", "finished"}
    return EvalResult(
        "E7_live_write_no_hitl",
        "真模型：关 HITL 写文件",
        ok,
        detail=(
            f"status={out.get('status')} steps={out.get('steps')} "
            f"file_exists={path.is_file()} content_ok={content_ok} "
            f"answer={(out.get('answer') or '')[:80]!r}"
        ),
        metrics={"steps": out.get("steps"), "status": out.get("status")},
    )
