"""CA-5：iter_manus_events 节点级事件流。"""

from langchain_core.messages import AIMessage

from app.manus import iter_manus_events
from app.tools.local_tools import get_phase1_tools
from tests.test_phase1_manus_graph import ScriptedChatModel


def test_iter_manus_events_start_node_done():
    """假模型应产出 start → 若干 node → done。"""
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
    assert "node" in types
    assert types[-1] == "done"
    assert events[-1].get("status") == "completed"
    assert "5" in (events[-1].get("answer") or "") or events[-1].get("answer")
