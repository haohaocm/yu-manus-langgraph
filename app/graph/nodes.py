"""图节点与路由：reason（思考）/ tools（执行）/ summarize（总结）。"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.prebuilt import ToolNode

from app.config import get_settings
from app.context.project import project_messages
from app.graph.ending import (
    on_budget_exceeded,
    on_terminate,
    on_text_only_finish,
    parse_terminate_from_tool_content,
    should_end,
)
from app.graph.planning import (
    first_user_text,
    format_plan_context,
    need_plan,
    parse_plan_output,
)
from app.prompts import NEXT_STEP_PROMPT, PLAN_PROMPT, SUMMARIZE_PROMPT, SYSTEM_PROMPT


def _message_content_text(content: object) -> str:
    """把 LLM chunk/消息的 content 收成纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def _emit_summarize_token(delta: str) -> None:
    """
    SSE-TOK：经 LangGraph StreamWriter 推送 summarize 正文增量。

    在 ``stream_mode`` 含 ``custom`` 时客户端能收到；``invoke`` 路径下写入会被丢弃。
    """
    if not delta:
        return
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer({"type": "token", "node": "summarize", "delta": delta})


def _summarize_via_stream(llm: BaseChatModel, prompt: list) -> str:
    """用 ``llm.stream`` 生成总结全文，边生成边 ``_emit_summarize_token``。"""
    parts: list[str] = []
    for chunk in llm.stream(prompt):
        delta = _message_content_text(getattr(chunk, "content", None))
        if not delta:
            continue
        parts.append(delta)
        _emit_summarize_token(delta)
    return "".join(parts).strip()

_TERMINAL_FOR_SUMMARIZE = frozenset(
    {
        "completed",
        "abandoned",
        "budget_exceeded",
        "cancelled",
        "finished",
        "error",
    }
)


def make_reason_node(model: BaseChatModel, tools: list):
    """
    工厂：生成 reason 节点闭包。

    对齐 Java ToolCallAgent.think：
    - 每轮追加 NEXT_STEP_PROMPT
    - bind_tools 后由模型决定是否调用工具
    - 无 tool_calls → completed（随后 summarize）
    - 步数超限 → budget_exceeded
    """
    llm_with_tools = model.bind_tools(tools)

    def reason(state: dict) -> dict:
        step = int(state.get("step", 0)) + 1
        max_steps = int(state.get("max_steps", 10))
        logs: list[str] = list(state.get("step_logs") or [])

        if step > max_steps:
            ending = on_budget_exceeded(step=step, max_steps=max_steps)
            logs.append(f"step{step} : {ending['end_reason']}")
            return {
                "step": step,
                "status": ending["status"],
                "end_reason": ending["end_reason"],
                "step_logs": logs,
                "messages": [AIMessage(content=ending["end_reason"])],
            }

        history = list(state.get("messages") or [])
        max_turns = int(get_settings().context_max_turns)
        projected = project_messages(history, max_turns=max_turns)
        plan_ctx = format_plan_context(
            plan=list(state.get("plan") or []),
            plan_skipped=bool(state.get("plan_skipped", True)),
            plan_step_index=int(state.get("plan_step_index") or 0),
        )
        next_prompt = (
            f"{plan_ctx}\n\n{NEXT_STEP_PROMPT}" if plan_ctx else NEXT_STEP_PROMPT
        )
        invoke_messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            *projected,
            HumanMessage(content=next_prompt),
        ]
        ai: AIMessage = llm_with_tools.invoke(invoke_messages)

        tool_calls = ai.tool_calls or []
        thought = (ai.content or "").strip()
        if tool_calls:
            names = ", ".join(tc.get("name", "?") for tc in tool_calls)
            logs.append(f"step{step} : think={thought or '(tool-only)'} tools=[{names}]")
            return {
                "messages": [ai],
                "step": step,
                "status": "running",
                "step_logs": logs,
            }

        ending = on_text_only_finish(thought=thought)
        logs.append(f"step{step} : think={thought or '(empty)'} tools=[] → {ending['status']}")
        return {
            "messages": [ai],
            "step": step,
            "status": ending["status"],
            "end_reason": ending["end_reason"],
            "step_logs": logs,
        }

    return reason


def make_tools_node(tools: list):
    """
    工厂：生成 tools 节点。

    内部用 LangGraph 预置 ToolNode 执行 tool_calls；
    仅当执行到 terminate 时写入 completed/abandoned（随后 summarize）。
    普通工具失败不在此结束。
    """
    base = ToolNode(tools)

    def tools_node(state: dict) -> dict:
        result = base.invoke(state)
        messages = result.get("messages") or []
        logs: list[str] = list(state.get("step_logs") or [])
        step = int(state.get("step", 0))
        updates: dict = {"messages": messages, "step_logs": logs, "status": "running"}

        # 优先从本轮 AI 的 terminate 参数取 outcome（比解析返回串更稳）
        terminate_args = _last_terminate_args(state.get("messages") or [])

        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            logs.append(f"step{step} : tool={msg.name} result={msg.content}")
            if msg.name != "terminate" and not str(msg.content).startswith("terminated:"):
                continue

            outcome = "success"
            reason = "task completed"
            if terminate_args:
                outcome = str(terminate_args.get("outcome") or "success")
                reason = str(terminate_args.get("reason") or reason)
            else:
                parsed = parse_terminate_from_tool_content(str(msg.content))
                if parsed:
                    outcome, reason = parsed

            ending = on_terminate(outcome=outcome, reason=reason)
            updates["status"] = ending["status"]
            updates["end_reason"] = ending["end_reason"]
            break

        updates["step_logs"] = logs
        return updates

    return tools_node


def make_plan_node(model: BaseChatModel):
    """
    CA-3 plan 节点：不绑工具；产出 steps 写入 state.plan。

    仅在 route_need_plan 判定为需要规划时进入本节点。
    """
    llm = model

    def plan_node(state: dict) -> dict:
        logs: list[str] = list(state.get("step_logs") or [])
        user_q = first_user_text(state.get("messages") or [])
        prompt = [
            SystemMessage(content=PLAN_PROMPT),
            HumanMessage(content=f"User task:\n{user_q}\n\nReturn JSON plan now."),
        ]
        ai: AIMessage = llm.invoke(prompt)
        raw = (ai.content or "").strip()
        steps = parse_plan_output(raw)
        logs.append(
            f"plan : steps={len(steps)} preview={steps[:3]!r}"
            f"{'…' if len(steps) > 3 else ''}"
        )
        return {
            "plan": steps,
            "plan_skipped": False,
            "plan_step_index": 0,
            "step_logs": logs,
            "messages": [AIMessage(content=f"[plan]\n{raw}" if raw else "[plan]\n(empty)")],
            "status": "running",
        }

    return plan_node


def route_need_plan(state: dict) -> str:
    """START 之后：规则判断 → plan 或直接 reason（无额外分类 LLM）。"""
    user_q = first_user_text(state.get("messages") or [])
    if need_plan(user_q):
        return "plan"
    return "reason"


def make_summarize_node(model: BaseChatModel):
    """
    总结节点：不绑定工具，把执行过程收成给用户看的最终答复。

    SSE-TOK：优先 ``llm.stream`` + StreamWriter 推 token；失败则回退 ``invoke``。
    大厂常见做法：执行轨迹与「对用户可见答案」分离；
    总结只基于已发生的事实（尤其是 ToolMessage），避免编造。
    """
    llm = model

    def summarize(state: dict) -> dict:
        """跑总结 LLM，写入 final_answer；流式路径下边推 token。"""
        logs: list[str] = list(state.get("step_logs") or [])
        status = state.get("status") or "completed"
        end_reason = state.get("end_reason") or ""
        history = list(state.get("messages") or [])

        user_question = _first_user_question(history)
        tool_digest = _tool_results_digest(history)
        log_text = "\n".join(logs) if logs else "(no step logs)"

        prompt = [
            SystemMessage(content=SUMMARIZE_PROMPT),
            HumanMessage(
                content=(
                    f"用户问题：\n{user_question}\n\n"
                    f"运行状态：{status}\n"
                    f"结束原因：{end_reason or '(无)'}\n\n"
                    f"工具结果摘要：\n{tool_digest}\n\n"
                    f"内部步骤日志（仅供参考，不要照抄格式）：\n{log_text}\n\n"
                    "请写出给用户的最终答复。"
                )
            ),
        ]
        final = ""
        try:
            final = _summarize_via_stream(llm, prompt)
        except Exception:  # noqa: BLE001 — 流式失败则整段 invoke
            ai: AIMessage = llm.invoke(prompt)
            final = _message_content_text(ai.content).strip()
        if not final:
            final = _fallback_answer(logs, tool_digest, status, end_reason)
        logs.append(f"summarize : {final[:200]}{'…' if len(final) > 200 else ''}")
        return {
            "final_answer": final,
            "step_logs": logs,
            "messages": [AIMessage(content=final)],
            "status": status if status in _TERMINAL_FOR_SUMMARIZE else "completed",
            "end_reason": end_reason,
        }

    return summarize


def route_after_reason(state: dict) -> str:
    """reason 之后：有 tool_calls → tools；否则 → summarize。"""
    if should_end(state):
        return "summarize"
    messages = state.get("messages") or []
    if not messages:
        return "summarize"
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "summarize"


def route_after_tools(state: dict) -> str:
    """tools 之后：未结束 → 再 reason（由 reason 入口做超步判定）；否则 → summarize。"""
    if should_end(state):
        return "summarize"
    return "reason"


def _last_terminate_args(messages: list) -> dict | None:
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        for tc in msg.tool_calls or []:
            if tc.get("name") == "terminate":
                args = tc.get("args") or {}
                return dict(args) if isinstance(args, dict) else {}
        break
    return None


def _first_user_question(messages: list) -> str:
    for msg in messages:
        if isinstance(msg, HumanMessage):
            text = (msg.content or "").strip()
            if text and text != NEXT_STEP_PROMPT:
                return text
    return "(未找到用户问题)"


def _tool_results_digest(messages: list) -> str:
    lines: list[str] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            lines.append(f"- {msg.name}: {msg.content}")
    return "\n".join(lines) if lines else "(本轮未调用工具)"


def _fallback_answer(logs: list[str], tool_digest: str, status: str, end_reason: str) -> str:
    if status == "abandoned":
        return f"目前无法完成该任务。原因：{end_reason or '未说明'}。"
    if status == "budget_exceeded":
        base = f"已达到步数上限，任务未能完成。{end_reason}"
        if tool_digest and tool_digest != "(本轮未调用工具)":
            return f"{base}\n已有工具结果：\n{tool_digest}"
        return base
    if tool_digest and tool_digest != "(本轮未调用工具)":
        return f"任务状态：{status}\n根据工具结果：\n{tool_digest}"
    if logs:
        return "\n".join(logs[-3:])
    return f"已结束（status={status}），但没有可展示的结果。"
