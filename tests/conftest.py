"""全局测试夹具：默认关闭 checkpoint，避免污染仓库 SQLite、拖慢单测。"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.graph.checkpointing import reset_checkpointer_singleton_for_tests
from app.tasks.store import reset_task_store_singleton_for_tests


@pytest.fixture(autouse=True)
def _disable_checkpoint_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path_factory):
    # 默认关 checkpointer / HITL；TaskStore 仍写入临时库，避免污染仓库 manus.sqlite
    # HITL 单测需自行 monkeypatch HITL_ENABLED=true 且开 checkpoint
    monkeypatch.setenv("CHECKPOINT_ENABLED", "false")
    monkeypatch.setenv("HITL_ENABLED", "false")
    task_db = tmp_path_factory.mktemp("tasks") / "test_tasks.sqlite"
    monkeypatch.setenv("CHECKPOINT_SQLITE_PATH", str(task_db))
    get_settings.cache_clear()
    reset_checkpointer_singleton_for_tests()
    reset_task_store_singleton_for_tests()
    yield
    reset_checkpointer_singleton_for_tests()
    reset_task_store_singleton_for_tests()
    get_settings.cache_clear()
