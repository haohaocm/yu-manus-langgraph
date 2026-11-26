"""CE-5：全量 event log——先内存，一轮结束后异步落盘（不分片、不做自动删除）。"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.tools.path_sandbox import get_workspace_root


@dataclass
class EventLog:
    """一轮 run 的内存事件流。"""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    events: list[dict[str, Any]] = field(default_factory=list)

    def add(self, event_type: str, **payload: Any) -> None:
        self.events.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": event_type,
                **payload,
            }
        )

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self.events)

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(e, ensure_ascii=False) for e in self.events) + (
            "\n" if self.events else ""
        )


def build_event_log_from_result(
    *,
    user_prompt: str,
    result: dict[str, Any],
    run_id: str | None = None,
) -> EventLog:
    """从一次 graph 结果组装全量日志（内存）。"""
    log = EventLog(run_id=run_id or uuid.uuid4().hex[:12])
    log.add("run_start", prompt=user_prompt)
    for i, line in enumerate(result.get("step_logs") or [], start=1):
        log.add("step_log", index=i, text=line)
    log.add(
        "run_end",
        status=result.get("status"),
        end_reason=result.get("end_reason") or "",
        steps=result.get("step", 0),
        final_answer=(result.get("final_answer") or "")[:500],
    )
    return log


def event_log_dir() -> Path:
    root = get_workspace_root()
    path = (root / "artifacts" / "event_logs").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def flush_event_log_sync(log: EventLog, *, directory: Path | None = None) -> Path:
    """同步写入 jsonl；测试与兜底用。"""
    out_dir = directory or event_log_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"{stamp}_{log.run_id}.jsonl"
    path.write_text(log.to_jsonl(), encoding="utf-8")
    return path


def schedule_flush_events(log: EventLog, *, directory: Path | None = None) -> None:
    """
    一轮对话结束后异步落盘（后台线程，不阻塞返回用户答案）。

    说明：比「每条事件同步 fsync」更轻；进程被强杀时可能丢最后一次 flush。
    需要更强耐久时可改为每事件 append（后续加强项）。
    """
    # 拷贝快照，避免线程里读到后续修改
    snapshot = EventLog(run_id=log.run_id, events=log.snapshot())
    target = directory

    def _worker() -> None:
        try:
            flush_event_log_sync(snapshot, directory=target)
        except Exception:
            # 落盘失败不影响主流程；可后续加日志
            pass

    threading.Thread(target=_worker, name=f"event-flush-{log.run_id}", daemon=True).start()
