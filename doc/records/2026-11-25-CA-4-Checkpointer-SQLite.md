# 2026-11-25 CA-4 Checkpointer（SQLite）

## 范围

用 LangGraph `SqliteSaver` 持久化图状态，支持 `thread_id` 续跑；提供读当前状态 / 历史的辅助函数与 HTTP 接口。

## 读写位置（心智模型）

| 方向 | 谁做 | 位置 |
|------|------|------|
| **写** | LangGraph 运行时自动 | `graph.invoke(..., config={thread_id})` 节点之间写入 SQLite |
| **读** | 我们封装 | `read_thread_state` / `read_thread_history`；`GET /agent/threads/{id}` |
| **续跑** | `run_manus(thread_id=...)` | 同 id 只追加用户消息，不重置 step/plan |

与 CE-5 event log **并存**：checkpoint=续跑引擎状态；event log=过程日志。

## 本机 SQLite

- **运行时：** Python 内置 `sqlite3`（当前环境约 3.49.x），**不依赖** `D:\support\sqlite` 安装目录。  
- **手工查看：** `D:\support\sqlite\sqlite3.exe artifacts/checkpoints/manus.sqlite`

## 关键路径

| 模块 | 路径 |
|------|------|
| 封装 | `app/graph/checkpointing.py` |
| 门面 | `app/manus.py`（`thread_id` / `read_thread_*`） |
| 图 | `app/graph/build.py`（`compile(checkpointer=...)`） |
| API | `POST /agent/run`（thread_id）；`GET /agent/threads/{thread_id}` |
| 依赖 | `langgraph-checkpoint-sqlite` |
| 计划 | `doc/development/plans/2026-11-25-CA-4-Checkpointer-SQLite.md` |

## 回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ca4_checkpoint.py tests/test_phase1_manus_graph.py tests/test_ca3_planning.py -q
```

**结果：** 相关测通过（含续跑）。

## S6 TaskInfo（同日补完）

- `TaskInfo` / `SqliteTaskStore`（表 `manus_tasks`，与 checkpoint 同库）  
- `run_manus` 开跑 `mark_running`、结束 `mark_finished`  
- API：`GET /agent/tasks`、`GET /agent/tasks/{task_id}`  
- 返回字段增加 `task_id`（MVP = `thread_id`）

## 下一主线

**CA-5** SSE（流式事件）。
