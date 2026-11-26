"""任务名片数据模型（元数据 only，不含 messages/plan 正文）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class TaskInfo:
    """
    任务封面信息：列表/管理用；执行进度仍以 checkpoint 为准。

    MVP：``task_id`` 与 ``thread_id`` 相同，便于关联 LangGraph 存档。
    """

    task_id: str
    thread_id: str
    title: str
    status: str = "running"  # running / completed / abandoned / budget_exceeded / …
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    extra_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TaskInfo:
        return cls(
            task_id=str(row["task_id"]),
            thread_id=str(row["thread_id"]),
            title=str(row.get("title") or ""),
            status=str(row.get("status") or "running"),
            created_at=str(row.get("created_at") or utc_now_iso()),
            updated_at=str(row.get("updated_at") or utc_now_iso()),
            extra_json=str(row.get("extra_json") or "{}"),
        )


def title_from_prompt(user_prompt: str, *, max_len: int = 80) -> str:
    """从用户首句生成任务标题：压空白；过长则截断并加省略号。"""
    text = " ".join((user_prompt or "").strip().split())
    if len(text) <= max_len:
        return text or "(empty)"
    return text[: max_len - 1] + "…"
