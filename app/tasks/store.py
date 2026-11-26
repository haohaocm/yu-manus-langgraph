"""TaskInfo 的 SQLite 仓储（表 ``manus_tasks``，可与 checkpoint 同库）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.graph.checkpointing import resolve_checkpoint_path
from app.tasks.models import TaskInfo, title_from_prompt, utc_now_iso

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS manus_tasks (
    task_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    extra_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_manus_tasks_updated ON manus_tasks(updated_at DESC);
"""


class SqliteTaskStore:
    """任务名片 CRUD；不写入 messages/plan。"""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_CREATE_SQL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert(self, info: TaskInfo) -> TaskInfo:
        self._conn.execute(
            """
            INSERT INTO manus_tasks (
                task_id, thread_id, title, status, created_at, updated_at, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                thread_id=excluded.thread_id,
                title=excluded.title,
                status=excluded.status,
                updated_at=excluded.updated_at,
                extra_json=excluded.extra_json
            """,
            (
                info.task_id,
                info.thread_id,
                info.title,
                info.status,
                info.created_at,
                info.updated_at,
                info.extra_json,
            ),
        )
        self._conn.commit()
        return info

    def get(self, task_id: str) -> TaskInfo | None:
        cur = self._conn.execute(
            "SELECT * FROM manus_tasks WHERE task_id = ?", (task_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return TaskInfo.from_row(dict(row))

    def get_by_thread(self, thread_id: str) -> TaskInfo | None:
        cur = self._conn.execute(
            "SELECT * FROM manus_tasks WHERE thread_id = ? ORDER BY updated_at DESC LIMIT 1",
            (thread_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return TaskInfo.from_row(dict(row))

    def list_recent(self, *, limit: int = 20) -> list[TaskInfo]:
        cur = self._conn.execute(
            "SELECT * FROM manus_tasks ORDER BY updated_at DESC LIMIT ?",
            (max(1, int(limit)),),
        )
        return [TaskInfo.from_row(dict(r)) for r in cur.fetchall()]

    def mark_running(self, task_id: str, *, thread_id: str, title: str) -> TaskInfo:
        existing = self.get(task_id)
        now = utc_now_iso()
        if existing is None:
            info = TaskInfo(
                task_id=task_id,
                thread_id=thread_id,
                title=title_from_prompt(title),
                status="running",
                created_at=now,
                updated_at=now,
            )
        else:
            info = TaskInfo(
                task_id=existing.task_id,
                thread_id=thread_id,
                title=existing.title or title_from_prompt(title),
                status="running",
                created_at=existing.created_at,
                updated_at=now,
                extra_json=existing.extra_json,
            )
        return self.upsert(info)

    def mark_finished(self, task_id: str, *, status: str) -> TaskInfo | None:
        existing = self.get(task_id)
        if existing is None:
            return None
        existing.status = status or "completed"
        existing.updated_at = utc_now_iso()
        return self.upsert(existing)

    def delete(self, task_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM manus_tasks WHERE task_id = ?", (task_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0


_store: SqliteTaskStore | None = None
_store_path: str | None = None


def get_task_store(
    settings: Settings | None = None,
    *,
    path: Path | str | None = None,
) -> SqliteTaskStore:
    """进程级 TaskStore；默认与 checkpoint 同一 SQLite 文件。"""
    global _store, _store_path
    s = settings or get_settings()
    target = Path(path) if path is not None else resolve_checkpoint_path(s)
    key = str(target.resolve())
    if _store is not None and _store_path == key:
        return _store
    if _store is not None:
        try:
            _store.close()
        except Exception:  # noqa: BLE001
            pass
    _store = SqliteTaskStore(key)
    _store_path = key
    return _store


def reset_task_store_singleton_for_tests() -> None:
    global _store, _store_path
    if _store is not None:
        try:
            _store.close()
        except Exception:  # noqa: BLE001
            pass
    _store = None
    _store_path = None
