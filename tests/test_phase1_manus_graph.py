"""Phase 1: Manus graph with scripted model (no remote LLM)."""

from typing import Any, Iterator

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app.graph.build import build_manus_graph
from app.manus import run_manus
from app.tools.local_tools import get_phase1_tools


class ScriptedChatModel(BaseChatModel):
    """Returns predetermined AIMessages in order (supports tool_calls).

    ``stream_chunk_chars``：``_stream`` 时按字符切片，便于 SSE-TOK 单测收到多段 token。
    """

    responses: list[AIMessage]
    idx: int = 0
    stream_chunk_chars: int = 4

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _next_message(self) -> AIMessage:
        """取出下一条脚本回复（耗尽则占位）。"""
        if self.idx >= len(self.responses):
            return AIMessage(content="(no more scripted responses)")
        msg = self.responses[self.idx]
        self.idx += 1
        return msg

    def _generate(self, messages: list, stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        """整段返回下一条脚本消息（``invoke`` 路径）。"""
        msg = self._next_message()
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _stream(
        self, messages: list, stop: list[str] | None = None, **kwargs: Any
    ) -> Iterator[ChatGenerationChunk]:
        """按块产出内容，供 summarize 的 ``llm.stream`` 使用。"""
        msg = self._next_message()
        content = msg.content if isinstance(msg.content, str) else str(msg.content or "")
        if msg.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(content=content, tool_calls=msg.tool_calls)
            )
            return
        size = max(1, int(self.stream_chunk_chars or 4))
        if not content:
            yield ChatGenerationChunk(message=AIMessageChunk(content=""))
            return
        for i in range(0, len(content), size):
            yield ChatGenerationChunk(message=AIMessageChunk(content=content[i : i + size]))

    def bind_tools(self, tools, **kwargs):
        return self


def test_local_tools_add():
    tools = {t.name: t for t in get_phase1_tools()}
    assert tools["add"].invoke({"a": 1, "b": 2}) == "3.0"
    out = tools["terminate"].invoke({"reason": "done", "outcome": "success"})
    assert out.startswith("terminated:outcome=success:")


def test_manus_add_then_terminate():
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="I will add first",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 1, "b": 2},
                        "id": "call_add_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="Done, terminating",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"reason": "sum computed", "outcome": "success"},
                        "id": "call_term_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="1 加 2 等于 3。"),
        ]
    )

    out = run_manus(
        "请计算 1+2，然后结束",
        model=model,
        max_steps=5,
        tools=get_phase1_tools(),
    )
    assert out["status"] == "completed"
    assert out["end_reason"] == "sum computed"
    assert out["steps"] >= 2
    assert "3" in out["answer"]
    assert "1 加 2" in out["answer"] or "等于 3" in out["answer"]
    logs = "\n".join(out["step_logs"])
    assert "add" in logs
    assert "terminate" in logs
    assert "summarize" in logs


def test_manus_abandon_terminate():
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="cannot finish",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {
                            "outcome": "abandon",
                            "reason": "没有可用的搜索工具",
                        },
                        "id": "call_term_ab",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="抱歉，当前没有搜索工具，无法完成该任务。"),
        ]
    )
    out = run_manus(
        "帮我搜索新闻",
        model=model,
        max_steps=3,
        tools=get_phase1_tools(),
    )
    assert out["status"] == "abandoned"
    assert "搜索" in out["end_reason"] or "工具" in out["end_reason"]
    assert out["answer"]


def test_manus_budget_exceeded():
    # 每步都调 echo，从不 terminate → 步数耗尽
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="loop",
                tool_calls=[
                    {
                        "name": "echo",
                        "args": {"text": "x"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="loop2",
                tool_calls=[
                    {
                        "name": "echo",
                        "args": {"text": "y"},
                        "id": "c2",
                        "type": "tool_call",
                    }
                ],
            ),
            # step=3 > max_steps=2 时 reason 不再调 LLM；下一条给 summarize
            AIMessage(content="已达到步数上限，未能完成。"),
        ]
    )
    out = run_manus("空转", model=model, max_steps=2, tools=get_phase1_tools())
    assert out["status"] == "budget_exceeded"
    assert "max_steps" in out["end_reason"]
    assert out["answer"]


def test_manus_no_tool_finishes():
    model = ScriptedChatModel(
        responses=[
            AIMessage(content="直接回答，无需工具"),
            AIMessage(content="你好！我是 YuManus。"),
        ],
    )
    out = run_manus("你好", model=model, max_steps=3, tools=get_phase1_tools())
    assert out["status"] == "completed"
    assert out["steps"] == 1
    assert "YuManus" in out["answer"] or "你好" in out["answer"]
    assert any("tools=[]" in x for x in out["step_logs"])


def test_graph_compiles():
    model = ScriptedChatModel(
        responses=[
            AIMessage(content="ok"),
            AIMessage(content="最终答复：ok"),
        ]
    )
    g = build_manus_graph(model, tools=get_phase1_tools())
    assert g is not None
    result = g.invoke(
        {
            "messages": [HumanMessage(content="hi")],
            "step": 0,
            "max_steps": 2,
            "status": "running",
            "step_logs": [],
            "final_answer": "",
            "end_reason": "",
        }
    )
    assert result["status"] == "completed"
    assert result.get("final_answer")
