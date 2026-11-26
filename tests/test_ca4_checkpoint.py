"""CA-4：SQLite checkpointer 写入 / 读取 / 同 thread 续跑。"""

from pathlib import Path

from langchain_core.messages import AIMessage

from app.config import get_settings
from app.graph.checkpointing import reset_checkpointer_singleton_for_tests
from app.manus import read_thread_history, read_thread_state, run_manus
from app.tools.local_tools import get_phase1_tools
from tests.test_phase1_manus_graph import ScriptedChatModel


def _scripted_add_once(then_text: str = "结果是 3。") -> ScriptedChatModel:
    return ScriptedChatModel(
        responses=[
            AIMessage(
                content="add",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 1, "b": 2},
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
            AIMessage(content=then_text),
        ]
    )


def test_sqlite_checkpoint_write_and_read(tmp_path: Path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("CHECKPOINT_ENABLED", "true")
    monkeypatch.setenv("CHECKPOINT_SQLITE_PATH", str(db))
    get_settings.cache_clear()
    reset_checkpointer_singleton_for_tests()

    model = _scripted_add_once()
    out = run_manus(
        "请计算 1+2，然后结束",
        model=model,
        max_steps=5,
        tools=get_phase1_tools(),
        use_checkpoint=True,
        checkpoint_path=str(db),
        persist_event_log=False,
    )
    assert out["status"] == "completed"
    assert out["thread_id"]
    assert db.is_file()

    st = read_thread_state(
        out["thread_id"],
        model=model,
        tools=get_phase1_tools(),
        checkpoint_path=str(db),
    )
    assert st["exists"] is True
    assert st["thread_id"] == out["thread_id"]
    assert st["status"] in {"completed", "finished"}
    assert len(st["messages_preview"]) >= 1

    hist = read_thread_history(
        out["thread_id"],
        model=model,
        tools=get_phase1_tools(),
        checkpoint_path=str(db),
        limit=10,
    )
    assert len(hist) >= 1


def test_same_thread_resume_appends_messages(tmp_path: Path, monkeypatch):
    db = tmp_path / "resume.sqlite"
    monkeypatch.setenv("CHECKPOINT_ENABLED", "true")
    get_settings.cache_clear()
    reset_checkpointer_singleton_for_tests()

    # 第一轮
    m1 = _scripted_add_once("第一轮完成。")
    out1 = run_manus(
        "请计算 1+2，然后结束",
        model=m1,
        max_steps=5,
        tools=get_phase1_tools(),
        use_checkpoint=True,
        checkpoint_path=str(db),
        persist_event_log=False,
    )
    tid = out1["thread_id"]
    assert tid

    # 第二轮：同 thread；需要足够脚本响应
    m2 = ScriptedChatModel(
        responses=[
            AIMessage(
                content="add again",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 3, "b": 4},
                        "id": "a2",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="done",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"outcome": "success", "reason": "round2"},
                        "id": "t2",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="第二轮完成。"),
        ]
    )
    out2 = run_manus(
        "请再计算 3+4 然后结束",
        model=m2,
        max_steps=5,
        tools=get_phase1_tools(),
        thread_id=tid,
        use_checkpoint=True,
        checkpoint_path=str(db),
        persist_event_log=False,
    )
    assert out2["thread_id"] == tid
    assert out2["status"] == "completed"

    st = read_thread_state(
        tid, model=m2, tools=get_phase1_tools(), checkpoint_path=str(db)
    )
    # 两轮用户消息都应在预览里（或至少消息数明显多于单轮）
    assert st["exists"] is True
    assert len(st["messages_preview"]) >= 4
