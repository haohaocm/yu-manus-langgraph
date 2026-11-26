"""发给模型的历史投影（最小版：近窗）。完备「近窗+摘要+可回查」见待办 CTX-1。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def project_messages(
    messages: list[BaseMessage],
    *,
    max_turns: int = 5,
) -> list[BaseMessage]:
    """
    最小投影：保留首条用户问题 + 最近 ``max_turns`` 个模型回合。

    回合：从一条 AIMessage 起，到下一条 AIMessage 之前的消息（含中间 ToolMessage）。
    不做摘要 / 线索（留给 CTX-1）。
    """
    if not messages or max_turns <= 0:
        return list(messages)

    first_user: HumanMessage | None = None
    rest: list[BaseMessage] = []
    for msg in messages:
        if first_user is None and isinstance(msg, HumanMessage):
            first_user = msg
            continue
        rest.append(msg)

    ai_indices = [i for i, m in enumerate(rest) if isinstance(m, AIMessage)]
    if not ai_indices:
        out: list[BaseMessage] = []
        if first_user is not None:
            out.append(first_user)
        out.extend(rest)
        return out

    start_ai = ai_indices[-max_turns] if len(ai_indices) > max_turns else ai_indices[0]
    kept_rest = rest[start_ai:]

    out = []
    if first_user is not None:
        out.append(first_user)
    out.extend(kept_rest)
    return out
