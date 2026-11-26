"""CA-6 S3：interrupt 挂起 → approve/reject resume。"""

from pathlib import Path

from langchain_core.messages import AIMessage

from app.config import get_settings
from app.graph.checkpointing import reset_checkpointer_singleton_for_tests
from app.manus import iter_manus_events, iter_manus_hitl_resume
from app.tasks.store import reset_task_store_singleton_for_tests
from app.tools.local_tools import get_phase1_tools
from app.tools.loader import load_agent_tools
from tests.test_phase1_manus_graph import ScriptedChatModel


def _enable_hitl(monkeypatch, tmp_path: Path):
    """打开 HITL + checkpoint，工作区落 tmp。"""
    db = tmp_path / "hitl.sqlite"
    monkeypatch.setenv("HITL_ENABLED", "true")
    monkeypatch.setenv("CHECKPOINT_ENABLED", "true")
    monkeypatch.setenv("CHECKPOINT_SQLITE_PATH", str(db))
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    reset_checkpointer_singleton_for_tests()
    reset_task_store_singleton_for_tests()
    return db


def test_write_file_interrupt_then_approve(tmp_path: Path, monkeypatch):
    """未批准前不落盘；approve 后文件出现且可 done。"""
    _enable_hitl(monkeypatch, tmp_path)
    tools = load_agent_tools(include_phase1_helpers=True, persist_long_results=False)
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="write",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "path": "outputs/hitl_demo.txt",
                            "content": "hello-hitl",
                        },
                        "id": "w1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="term",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"outcome": "success", "reason": "written"},
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="已写入 outputs/hitl_demo.txt。"),
        ],
        stream_chunk_chars=8,
    )
    events = list(
        iter_manus_events(
            "写文件然后结束",
            model=model,
            max_steps=8,
            tools=tools,
            use_checkpoint=True,
            persist_event_log=False,
        )
    )
    types = [e.get("type") for e in events]
    assert "hitl_required" in types
    assert types[-1] == "hitl_required"
    assert not (tmp_path / "outputs" / "hitl_demo.txt").exists()
    tid = events[0]["thread_id"]

    events2 = list(
        iter_manus_hitl_resume(
            tid,
            decision="approve",
            model=model,
            tools=tools,
            persist_event_log=False,
        )
    )
    assert (tmp_path / "outputs" / "hitl_demo.txt").read_text(encoding="utf-8") == "hello-hitl"
    assert events2[-1].get("type") == "done"
    assert events2[-1].get("status") == "completed"


def test_write_file_reject_no_write(tmp_path: Path, monkeypatch):
    """拒绝后不落盘；模型收到 error 后可 text-only 结束。"""
    _enable_hitl(monkeypatch, tmp_path)
    tools = load_agent_tools(include_phase1_helpers=True, persist_long_results=False)
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="write",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"path": "outputs/nope.txt", "content": "x"},
                        "id": "w1",
                        "type": "tool_call",
                    }
                ],
            ),
            # reject 后回到 reason：不再调工具，直接文本结束
            AIMessage(content="用户拒绝了写文件，我改用口头说明。"),
            AIMessage(content="因用户拒绝，未写入文件。"),
        ],
        stream_chunk_chars=10,
    )
    events = list(
        iter_manus_events(
            "写个文件",
            model=model,
            max_steps=8,
            tools=tools,
            use_checkpoint=True,
            persist_event_log=False,
        )
    )
    tid = events[0]["thread_id"]
    assert events[-1]["type"] == "hitl_required"

    events2 = list(
        iter_manus_hitl_resume(
            tid,
            decision="reject",
            note="不要写盘",
            model=model,
            tools=tools,
            persist_event_log=False,
        )
    )
    assert not (tmp_path / "outputs" / "nope.txt").exists()
    assert events2[-1].get("type") == "done"
