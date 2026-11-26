"""SSE-TOK：summarize 正文 token 事件序列。"""

from langchain_core.messages import AIMessage

from app.manus import iter_manus_events, run_manus
from app.tools.local_tools import get_phase1_tools
from tests.test_phase1_manus_graph import ScriptedChatModel


def test_iter_manus_events_emits_summarize_tokens():
    """假模型：token 增量拼接应等于 done.answer。"""
    final_text = "2加3等于5。"
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
            AIMessage(content=final_text),
        ],
        stream_chunk_chars=2,
    )
    events = list(
        iter_manus_events(
            "请计算 2+3 然后结束",
            model=model,
            max_steps=5,
            tools=get_phase1_tools(),
            use_checkpoint=False,
            persist_event_log=False,
        )
    )
    types = [e.get("type") for e in events]
    assert types[0] == "start"
    assert "token" in types
    assert types[-1] == "done"
    deltas = [e.get("delta") or "" for e in events if e.get("type") == "token"]
    assert len(deltas) >= 2
    joined = "".join(deltas)
    done_answer = events[-1].get("answer") or ""
    assert joined == done_answer
    assert final_text in done_answer


def test_run_manus_still_works_with_stream_summarize():
    """非 SSE 的 run_manus 不回归（summarize 内部走 stream）。"""
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="t",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"outcome": "success", "reason": "bye"},
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="已结束。"),
        ],
        stream_chunk_chars=3,
    )
    out = run_manus(
        "直接结束",
        model=model,
        max_steps=3,
        tools=get_phase1_tools(),
        use_checkpoint=False,
        persist_event_log=False,
    )
    assert out["status"] == "completed"
    assert "结束" in (out.get("answer") or "")
