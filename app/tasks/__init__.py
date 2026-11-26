"""CA-4 S6：任务名片（TaskInfo）与仓储；与 checkpoint 分责、用 thread_id 关联。"""

from app.tasks.models import TaskInfo
from app.tasks.store import SqliteTaskStore, get_task_store

__all__ = ["TaskInfo", "SqliteTaskStore", "get_task_store"]
