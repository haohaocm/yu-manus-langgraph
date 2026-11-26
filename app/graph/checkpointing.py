"""CA-4：SQLite Checkpointer 封装与读状态辅助。

写入：由 LangGraph 在 ``graph.invoke(..., config=thread_config)`` 时自动完成。
读取：本模块 ``get_thread_state`` / ``get_thread_history`` 供调试与 API。
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import Settings, get_settings
from app.tools.path_sandbox import project_root

# 进程内单例（FastAPI / 多次 run_manus 共用同一连接）
_saver: SqliteSaver | None = None
_conn: sqlite3.Connection | None = None
_saver_path: str | None = None


def resolve_checkpoint_path(settings: Settings | None = None) -> Path:
    """解析 SQLite 文件绝对路径（相对路径相对仓库根）。"""
    s = settings or get_settings()
    raw = (s.checkpoint_sqlite_path or "artifacts/checkpoints/manus.sqlite").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = project_root() / p
    return p.resolve()


def get_sqlite_checkpointer(
    settings: Settings | None = None,
    *,
    path: Path | str | None = None,
) -> SqliteSaver:
    """
    返回进程级 SqliteSaver；自动 ``setup()`` 建表。

    注意：不要用 ``from_conn_string`` 的 with 块做长生命周期服务
    （退出 with 会关连接）；此处保持连接打开。
    """
    global _saver, _conn, _saver_path
    s = settings or get_settings()
    target = Path(path) if path is not None else resolve_checkpoint_path(s)
    target.parent.mkdir(parents=True, exist_ok=True)
    key = str(target)

    if _saver is not None and _saver_path == key:
        return _saver

    # 切换路径时关闭旧连接
    if _conn is not None:
        try:
            _conn.close()
        except Exception:  # noqa: BLE001
            pass
        _conn = None
        _saver = None

    _conn = sqlite3.connect(key, check_same_thread=False)
    _saver = SqliteSaver(_conn)
    _saver.setup()
    _saver_path = key
    return _saver


def reset_checkpointer_singleton_for_tests() -> None:
    """测试用：关闭并清空单例，避免跨测共用连接。"""
    global _saver, _conn, _saver_path
    if _conn is not None:
        try:
            _conn.close()
        except Exception:  # noqa: BLE001
            pass
    _saver = None
    _conn = None
    _saver_path = None


def new_thread_id() -> str:
    return str(uuid.uuid4())


def thread_config(thread_id: str, *, recursion_limit: int | None = None) -> dict[str, Any]:
    """LangGraph ``invoke`` / ``get_state`` 用的 config。"""
    cfg: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if recursion_limit is not None:
        cfg["recursion_limit"] = recursion_limit
    return cfg


def _summarize_messages(messages: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages or []:
        name = type(m).__name__
        content = getattr(m, "content", "")
        text = str(content) if content is not None else ""
        if len(text) > 240:
            text = text[:240] + "…"
        item: dict[str, Any] = {"type": name, "content_preview": text}
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            item["tool_calls"] = [
                tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                for tc in tool_calls
            ]
        out.append(item)
    return out


def get_thread_state(graph: Any, thread_id: str) -> dict[str, Any]:
    """
    读某 thread **当前**最新 checkpoint 中的业务字段摘要。

    ``graph`` 须为带 checkpointer 编译后的图。
    """
    snap = graph.get_state(thread_config(thread_id))
    values = dict(snap.values or {})
    return {
        "thread_id": thread_id,
        "exists": bool(values),
        "next": list(snap.next or ()),
        "step": values.get("step"),
        "status": values.get("status"),
        "end_reason": values.get("end_reason"),
        "plan": list(values.get("plan") or []),
        "plan_skipped": values.get("plan_skipped"),
        "plan_step_index": values.get("plan_step_index"),
        "step_logs_tail": list(values.get("step_logs") or [])[-8:],
        "messages_preview": _summarize_messages(list(values.get("messages") or [])),
        "final_answer_preview": str(values.get("final_answer") or "")[:200],
    }


def get_thread_history(graph: Any, thread_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """读该 thread 的 checkpoint **历史**（新→旧，最多 limit 条）。"""
    rows: list[dict[str, Any]] = []
    for i, snap in enumerate(graph.get_state_history(thread_config(thread_id))):
        if i >= limit:
            break
        values = dict(snap.values or {})
        rows.append(
            {
                "index": i,
                "next": list(snap.next or ()),
                "step": values.get("step"),
                "status": values.get("status"),
                "plan_len": len(values.get("plan") or []),
                "messages_len": len(values.get("messages") or []),
                "step_logs_len": len(values.get("step_logs") or []),
            }
        )
    return rows


def thread_has_state(graph: Any, thread_id: str) -> bool:
    snap = graph.get_state(thread_config(thread_id))
    return bool(snap.values)
