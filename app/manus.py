"""Manus 运行门面：组装模型 / 工具 / 图，并返回统一结果字典；CA-5 提供事件流。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from app.config import get_settings
from app.context.events import build_event_log_from_result, schedule_flush_events
from app.graph.build import build_manus_graph
from app.graph.checkpointing import (
    get_sqlite_checkpointer,
    get_thread_history,
    get_thread_state,
    new_thread_id,
    resolve_checkpoint_path,
    thread_config,
    thread_has_state,
)
from app.llm import build_chat_model
from app.tasks.store import get_task_store
from app.tools.loader import load_agent_tools


def _extract_interrupt_payload(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """
    从 stream updates 里取出 HITL 提案。

    LangGraph 在挂起时会发 ``{'__interrupt__': (Interrupt(value=提案), ...)}``。
    """
    if "__interrupt__" not in chunk:
        return None
    inter = chunk["__interrupt__"]
    items = inter if isinstance(inter, (list, tuple)) else (inter,)
    for item in items:
        val = getattr(item, "value", item)
        if isinstance(val, dict):
            return val
    return {"raw": str(inter)}


def _consume_graph_stream(
    stream_iter: Any,
    *,
    tid: str,
    last_values: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """
    消费 graph.stream 的 updates/custom，产出 SSE 事件；遇 HITL 则 yield hitl_required 后结束。

    返回的生成器若最后一事件是 hitl_required，调用方不应再发 done。
    """
    for mode, chunk in stream_iter:
        if mode == "custom":
            if isinstance(chunk, dict) and chunk.get("type") == "token":
                yield {
                    "type": "token",
                    "node": chunk.get("node") or "summarize",
                    "delta": chunk.get("delta") or "",
                    "thread_id": tid,
                    "task_id": tid,
                }
            continue
        if mode != "updates" or not isinstance(chunk, dict):
            continue
        payload = _extract_interrupt_payload(chunk)
        if payload is not None:
            yield {
                "type": "hitl_required",
                "thread_id": tid,
                "task_id": tid,
                "proposal": payload,
                # 扁平字段方便前端少一层取值
                "tool": payload.get("tool"),
                "path": payload.get("path"),
                "command": payload.get("command"),
                "diff_text": payload.get("diff_text"),
                "preview_text": payload.get("preview_text"),
                "risk": (payload.get("verdict") or {}).get("risk")
                if isinstance(payload.get("verdict"), dict)
                else payload.get("risk"),
            }
            return
        for node_name, update in chunk.items():
            if node_name == "__interrupt__":
                continue
            if not isinstance(update, dict):
                continue
            last_values.update(update)
            yield {
                "type": "node",
                **_summarize_node_update(str(node_name), update),
            }


def _fresh_input(user_prompt: str, max_steps: int) -> dict:
    """构造新 thread 的初始图输入。"""
    return {
        "messages": [HumanMessage(content=user_prompt)],
        "step": 0,
        "max_steps": max_steps,
        "status": "running",
        "step_logs": [],
        "final_answer": "",
        "end_reason": "",
        "plan": [],
        "plan_skipped": True,
        "plan_step_index": 0,
    }


def _preview_text(value: Any, *, limit: int = 240) -> str:
    """把任意对象压成短预览字符串，便于 SSE 推送。"""
    text = "" if value is None else str(value)
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _summarize_node_update(node: str, update: dict[str, Any]) -> dict[str, Any]:
    """把节点 state 增量收成前端可读的小字典（不含完整 messages）。"""
    out: dict[str, Any] = {"node": node}
    if "status" in update:
        out["status"] = update.get("status")
    if "step" in update:
        out["step"] = update.get("step")
    if "end_reason" in update:
        out["end_reason"] = _preview_text(update.get("end_reason"), limit=120)
    if "final_answer" in update and update.get("final_answer"):
        # summarize 正文已由 token 事件推送；此处只留短预览，避免与 answer 三重重复
        limit = 120 if node == "summarize" else 400
        out["final_answer"] = _preview_text(update.get("final_answer"), limit=limit)
    if "plan" in update:
        plan = list(update.get("plan") or [])
        out["plan"] = plan
        out["plan_skipped"] = update.get("plan_skipped")
    logs = list(update.get("step_logs") or [])
    if logs and node != "summarize":
        out["log_tail"] = _preview_text(logs[-1], limit=300)
    # summarize：不重复刷 think/log（token 已承担正文）
    if node == "summarize":
        return out
    # 最近一条 AI / Tool 预览
    for msg in reversed(list(update.get("messages") or [])):
        if isinstance(msg, ToolMessage):
            out["tool"] = msg.name
            out["tool_preview"] = _preview_text(msg.content, limit=200)
            break
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                out["tool_calls"] = [
                    (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None))
                    for tc in msg.tool_calls
                ]
            if msg.content:
                out["think_preview"] = _preview_text(msg.content, limit=200)
            break
    return out


def run_manus(
    user_prompt: str,
    *,
    model: BaseChatModel | None = None,
    max_steps: int | None = None,
    tools: list | None = None,
    persist_event_log: bool = True,
    thread_id: str | None = None,
    use_checkpoint: bool | None = None,
    checkpoint_path: str | None = None,
) -> dict:
    """
    跑一轮 YuManus（含最终 summarize）。

    CA-4：
      - ``thread_id`` 空则新建 UUID；同 id 再次调用会**续跑**（只追加用户消息，不重置 step）。
      - 默认启用 SQLite checkpointer（``CHECKPOINT_ENABLED``）；测试可关或指定 ``checkpoint_path``。

    返回中含 ``thread_id``，便于客户端续聊 / 调 ``read_thread_state``。
    """
    settings = get_settings()
    llm = model or build_chat_model(settings)
    steps = max_steps if max_steps is not None else settings.max_steps
    tool_list = tools if tools is not None else load_agent_tools(settings)

    enabled = settings.checkpoint_enabled if use_checkpoint is None else use_checkpoint
    checkpointer = None
    tid = thread_id or new_thread_id()
    db_path = checkpoint_path or str(resolve_checkpoint_path(settings))
    if enabled:
        checkpointer = get_sqlite_checkpointer(
            settings,
            path=db_path,
        )

    # S6：任务名片（与 checkpoint 同库另表）；开跑登记
    task_store = get_task_store(settings, path=db_path)
    task_store.mark_running(tid, thread_id=tid, title=user_prompt)

    graph = build_manus_graph(llm, tool_list, checkpointer=checkpointer)
    recursion = max(steps * 4, 24)
    config = thread_config(tid, recursion_limit=recursion) if checkpointer else {
        "recursion_limit": recursion
    }

    if checkpointer and thread_has_state(graph, tid):
        # 续跑：只追加用户消息，保留 plan/step/messages
        graph_input: dict = {
            "messages": [HumanMessage(content=user_prompt)],
            "status": "running",
            "final_answer": "",
            "end_reason": "",
        }
    else:
        graph_input = _fresh_input(user_prompt, steps)

    result = graph.invoke(graph_input, config=config)

    # CA-6：invoke 路径遇 interrupt 时结果里带 __interrupt__，尚未写完
    if isinstance(result, dict) and result.get("__interrupt__"):
        payload = _extract_interrupt_payload(
            {"__interrupt__": result.get("__interrupt__")}
        ) or {}
        task_store.mark_finished(tid, status="waiting_hitl")
        return {
            "answer": "",
            "final_answer": "",
            "status": "waiting_hitl",
            "end_reason": "waiting for human approval",
            "steps": result.get("step", 0),
            "step_logs": list(result.get("step_logs") or []),
            "messages": result.get("messages") or [],
            "plan": list(result.get("plan") or []),
            "plan_skipped": bool(result.get("plan_skipped", True)),
            "thread_id": tid,
            "task_id": tid,
            "hitl_proposal": payload,
            "event_log": {},
            "run_id": "",
        }

    logs: list[str] = list(result.get("step_logs") or [])
    final = (result.get("final_answer") or "").strip()
    if not final:
        final = "\n".join(logs) if logs else ""

    status = result.get("status", "completed")
    task_store.mark_finished(tid, status=str(status))

    event_log = build_event_log_from_result(user_prompt=user_prompt, result=result)
    if persist_event_log:
        schedule_flush_events(event_log)

    return {
        "answer": final,
        "final_answer": final,
        "status": status,
        "end_reason": result.get("end_reason") or "",
        "steps": result.get("step", 0),
        "step_logs": logs,
        "messages": result.get("messages") or [],
        "plan": list(result.get("plan") or []),
        "plan_skipped": bool(result.get("plan_skipped", True)),
        "thread_id": tid,
        "task_id": tid,
        "event_log": event_log.snapshot(),
        "run_id": event_log.run_id,
    }


def iter_manus_events(
    user_prompt: str,
    *,
    model: BaseChatModel | None = None,
    max_steps: int | None = None,
    tools: list | None = None,
    persist_event_log: bool = True,
    thread_id: str | None = None,
    use_checkpoint: bool | None = None,
    checkpoint_path: str | None = None,
) -> Iterator[dict[str, Any]]:
    """
    CA-5 + SSE-TOK：按图节点产出事件，并转发 summarize 正文 token。

    事件类型：
      - start：开跑（含 thread_id/task_id）
      - node：某节点刚跑完的摘要
      - token：summarize 正文增量（``delta``）
      - done：最终答复与状态
      - error：异常
    """
    settings = get_settings()
    llm = model or build_chat_model(settings)
    steps = max_steps if max_steps is not None else settings.max_steps
    tool_list = tools if tools is not None else load_agent_tools(settings)

    # HITL 依赖 checkpointer；开启 HITL 时强制落库，否则 interrupt 无法 resume
    enabled = settings.checkpoint_enabled if use_checkpoint is None else use_checkpoint
    if settings.hitl_enabled:
        enabled = True
    checkpointer = None
    tid = thread_id or new_thread_id()
    db_path = checkpoint_path or str(resolve_checkpoint_path(settings))
    if enabled:
        checkpointer = get_sqlite_checkpointer(settings, path=db_path)

    task_store = get_task_store(settings, path=db_path)
    task_store.mark_running(tid, thread_id=tid, title=user_prompt)

    graph = build_manus_graph(llm, tool_list, checkpointer=checkpointer)
    recursion = max(steps * 4, 24)
    config = (
        thread_config(tid, recursion_limit=recursion)
        if checkpointer
        else {"recursion_limit": recursion}
    )

    resumed = bool(checkpointer and thread_has_state(graph, tid))
    if resumed:
        graph_input: dict = {
            "messages": [HumanMessage(content=user_prompt)],
            "status": "running",
            "final_answer": "",
            "end_reason": "",
        }
    else:
        graph_input = _fresh_input(user_prompt, steps)

    yield {
        "type": "start",
        "thread_id": tid,
        "task_id": tid,
        "resumed": resumed,
        "message_preview": _preview_text(user_prompt, limit=120),
    }

    last_values: dict[str, Any] = {}
    hitl_pending = False
    try:
        stream_iter = graph.stream(
            graph_input,
            config=config,
            stream_mode=["updates", "custom"],
        )
        for ev in _consume_graph_stream(stream_iter, tid=tid, last_values=last_values):
            if ev.get("type") == "hitl_required":
                hitl_pending = True
                task_store.mark_finished(tid, status="waiting_hitl")
            yield ev
            if hitl_pending:
                return
    except Exception as exc:  # noqa: BLE001
        task_store.mark_finished(tid, status="error")
        yield {"type": "error", "error": str(exc), "thread_id": tid, "task_id": tid}
        return

    logs: list[str] = list(last_values.get("step_logs") or [])
    final = (last_values.get("final_answer") or "").strip()
    if not final:
        final = "\n".join(logs) if logs else ""
    status = last_values.get("status", "completed")
    task_store.mark_finished(tid, status=str(status))

    result_for_log = {
        "status": status,
        "end_reason": last_values.get("end_reason") or "",
        "step": last_values.get("step", 0),
        "step_logs": logs,
        "messages": last_values.get("messages") or [],
        "final_answer": final,
    }
    event_log = build_event_log_from_result(user_prompt=user_prompt, result=result_for_log)
    if persist_event_log:
        schedule_flush_events(event_log)

    yield {
        "type": "done",
        "thread_id": tid,
        "task_id": tid,
        "status": status,
        "end_reason": last_values.get("end_reason") or "",
        "steps": last_values.get("step", 0),
        "answer": final,
        "final_answer": final,
        "plan": list(last_values.get("plan") or []),
        "run_id": event_log.run_id,
    }


def iter_manus_hitl_resume(
    thread_id: str,
    *,
    decision: str,
    note: str = "",
    model: BaseChatModel | None = None,
    tools: list | None = None,
    persist_event_log: bool = True,
    checkpoint_path: str | None = None,
) -> Iterator[dict[str, Any]]:
    """
    CA-6：人对 hitl_required 做出 approve/reject 后，用 Command(resume=…) 继续跑图。

    可能再次 yield hitl_required（一次多个写工具逐个批），或最终 done。
    """
    settings = get_settings()
    llm = model or build_chat_model(settings)
    tool_list = tools if tools is not None else load_agent_tools(settings)
    db_path = checkpoint_path or str(resolve_checkpoint_path(settings))
    checkpointer = get_sqlite_checkpointer(settings, path=db_path)
    task_store = get_task_store(settings, path=db_path)
    task_store.mark_running(thread_id, thread_id=thread_id, title="(hitl resume)")

    graph = build_manus_graph(llm, tool_list, checkpointer=checkpointer)
    config = thread_config(thread_id, recursion_limit=max(settings.max_steps * 4, 24))

    yield {
        "type": "hitl_resumed",
        "thread_id": thread_id,
        "task_id": thread_id,
        "decision": decision,
        "note": note,
    }

    last_values: dict[str, Any] = {}
    hitl_pending = False
    try:
        stream_iter = graph.stream(
            Command(resume={"decision": decision, "note": note}),
            config=config,
            stream_mode=["updates", "custom"],
        )
        for ev in _consume_graph_stream(stream_iter, tid=thread_id, last_values=last_values):
            if ev.get("type") == "hitl_required":
                hitl_pending = True
                task_store.mark_finished(thread_id, status="waiting_hitl")
            yield ev
            if hitl_pending:
                return
    except Exception as exc:  # noqa: BLE001
        task_store.mark_finished(thread_id, status="error")
        yield {
            "type": "error",
            "error": str(exc),
            "thread_id": thread_id,
            "task_id": thread_id,
        }
        return

    # resume 后 last_values 可能只有增量；从 checkpoint 快照补全终态
    try:
        snap = graph.get_state(config)
        values = dict(snap.values or {})
        for key in (
            "final_answer",
            "status",
            "step",
            "step_logs",
            "plan",
            "end_reason",
            "messages",
        ):
            if key not in last_values or last_values.get(key) in (None, "", [], 0):
                if key in values and values.get(key) not in (None, ""):
                    last_values[key] = values.get(key)
    except Exception:  # noqa: BLE001
        pass

    logs: list[str] = list(last_values.get("step_logs") or [])
    final = (last_values.get("final_answer") or "").strip()
    if not final:
        final = "\n".join(logs) if logs else ""
    status = last_values.get("status", "completed")
    task_store.mark_finished(thread_id, status=str(status))

    result_for_log = {
        "status": status,
        "end_reason": last_values.get("end_reason") or "",
        "step": last_values.get("step", 0),
        "step_logs": logs,
        "messages": last_values.get("messages") or [],
        "final_answer": final,
    }
    event_log = build_event_log_from_result(user_prompt="(hitl resume)", result=result_for_log)
    if persist_event_log:
        schedule_flush_events(event_log)

    yield {
        "type": "done",
        "thread_id": thread_id,
        "task_id": thread_id,
        "status": status,
        "end_reason": last_values.get("end_reason") or "",
        "steps": last_values.get("step", 0),
        "answer": final,
        "final_answer": final,
        "plan": list(last_values.get("plan") or []),
        "run_id": event_log.run_id,
    }


def read_thread_state(
    thread_id: str,
    *,
    model: BaseChatModel | None = None,
    tools: list | None = None,
    checkpoint_path: str | None = None,
) -> dict:
    """读取 SQLite 中某 thread 的**当前**状态摘要（不跑模型）。"""
    settings = get_settings()
    llm = model or build_chat_model(settings)
    tool_list = tools if tools is not None else load_agent_tools(settings)
    checkpointer = get_sqlite_checkpointer(settings, path=checkpoint_path)
    graph = build_manus_graph(llm, tool_list, checkpointer=checkpointer)
    return get_thread_state(graph, thread_id)


def read_thread_history(
    thread_id: str,
    *,
    limit: int = 20,
    model: BaseChatModel | None = None,
    tools: list | None = None,
    checkpoint_path: str | None = None,
) -> list[dict]:
    """读取某 thread 的 checkpoint 历史列表。"""
    settings = get_settings()
    llm = model or build_chat_model(settings)
    tool_list = tools if tools is not None else load_agent_tools(settings)
    checkpointer = get_sqlite_checkpointer(settings, path=checkpoint_path)
    graph = build_manus_graph(llm, tool_list, checkpointer=checkpointer)
    return get_thread_history(graph, thread_id, limit=limit)
