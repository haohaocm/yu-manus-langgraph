"""组装并编译 Manus 状态图。"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    make_plan_node,
    make_reason_node,
    make_summarize_node,
    make_tools_node,
    route_after_reason,
    route_after_tools,
    route_need_plan,
)
from app.graph.state import ManusState
from app.tools.loader import load_agent_tools


def build_manus_graph(
    model: BaseChatModel,
    tools: list | None = None,
    *,
    checkpointer: Any | None = None,
):
    """
    构建 Plan（可选）+ ReAct + 总结 图：

        START → need_plan? → (plan →)? reason ⇄ tools → summarize → END

    - checkpointer：传入 SqliteSaver 等则启用断点续跑（CA-4）
    """
    tool_list = tools if tools is not None else load_agent_tools()
    graph = StateGraph(ManusState)
    graph.add_node("plan", make_plan_node(model))
    graph.add_node("reason", make_reason_node(model, tool_list))
    graph.add_node("tools", make_tools_node(tool_list))
    graph.add_node("summarize", make_summarize_node(model))

    graph.add_conditional_edges(
        START,
        route_need_plan,
        {"plan": "plan", "reason": "reason"},
    )
    graph.add_edge("plan", "reason")
    graph.add_conditional_edges(
        "reason",
        route_after_reason,
        {"tools": "tools", "summarize": "summarize"},
    )
    graph.add_conditional_edges(
        "tools",
        route_after_tools,
        {"reason": "reason", "summarize": "summarize"},
    )
    graph.add_edge("summarize", END)
    return graph.compile(checkpointer=checkpointer)
