"""CA-4 S6：TaskInfo / SqliteTaskStore CRUD + run_manus 挂钩。"""

from pathlib import Path

from langchain_core.messages import AIMessage

from app.config import get_settings
from app.graph.checkpointing import reset_checkpointer_singleton_for_tests
from app.manus import run_manus
from app.tasks.models import TaskInfo, title_from_prompt
from app.tasks.store import SqliteTaskStore, get_task_store, reset_task_store_singleton_for_tests
from app.tools.local_tools import get_phase1_tools
from tests.test_phase1_manus_graph import ScriptedChatModel


def test_title_from_prompt_truncates():
    assert title_from_prompt("短") == "短"
    long = "字" * 100
    t = title_from_prompt(long, max_len=80)
    assert len(t) == 80
    assert t.endswith("…")


def test_task_store_crud(tmp_path: Path):
    db = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(db)
    info = TaskInfo(
        task_id="t1",
        thread_id="t1",
        title="demo",
        status="running",
    )
    store.upsert(info)
    got = store.get("t1")
    assert got is not None
    assert got.title == "demo"
    store.mark_finished("t1", status="completed")
    assert store.get("t1").status == "completed"
    assert store.list_recent(limit=5)[0].task_id == "t1"
    assert store.delete("t1") is True
    assert store.get("t1") is None
    store.close()


def test_run_manus_registers_task(tmp_path: Path, monkeypatch):
    db = tmp_path / "hook.sqlite"
    monkeypatch.setenv("CHECKPOINT_ENABLED", "false")
    monkeypatch.setenv("CHECKPOINT_SQLITE_PATH", str(db))
    get_settings.cache_clear()
    reset_checkpointer_singleton_for_tests()
    reset_task_store_singleton_for_tests()

    model = ScriptedChatModel(
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
            AIMessage(content="3"),
        ]
    )
    out = run_manus(
        "请计算 1+2，然后结束",
        model=model,
        max_steps=5,
        tools=get_phase1_tools(),
        use_checkpoint=False,
        checkpoint_path=str(db),
        persist_event_log=False,
    )
    assert out["task_id"]
    assert out["task_id"] == out["thread_id"]
    store = get_task_store(path=str(db))
    info = store.get(out["task_id"])
    assert info is not None
    assert info.status == "completed"
    assert "1+2" in info.title or "计算" in info.title
