# 计划：CA-4 Checkpointer（SQLite）+ 任务信息层

> 状态：✅ **S0～S6 全部完成**（2026-11-25）  
> 术语：checkpointer、checkpoint、thread_id、TaskInfo（任务元数据）、TaskStore（任务仓储）

---

## 1. 背景与目标

**要解决：**

1. 图状态可 SQLite 持久化、按 `thread_id` 续跑（S0～S5 已完成）。  
2. **另建轻量「任务信息」模型/仓储**，存标题、状态、时间、关联 `thread_id` 等**业务侧**信息，避免后续 SSE/HITL/多会话时到处散落字典（S6）。

**非目标：**

- 用 TaskInfo **重复**存整份 `messages` / 完整 checkpoint（那是 SqliteSaver 的活）  
- 替代 CE-5 event log  
- 完整任务中心 UI（CA-8）  
- Postgres  

---

## 2. 心智模型（读写 + 内存）

### 2.1 节点要不要每次读库？

**对：一次 `invoke` 进行中，节点拿的是内存里的 state（上下文），不必每个节点前再读 SQLite。**

| 时机 | 行为 |
|------|------|
| `invoke` **开始**（含续跑） | 框架按 `thread_id` **加载最新 checkpoint → 内存** |
| **节点执行中** | 读写**内存 state**（已知上下文） |
| **节点结束后** | 框架 **自动写回** SQLite（新 checkpoint） |
| 你调 `get_thread_state` | **显式读库**（调试 / API / 任务列表展示） |

### 2.2 写 / 读（引擎层，已落地）

- **写：** LangGraph + `SqliteSaver`，节点后自动 put。  
- **读当前：** `read_thread_state` / `GET /agent/threads/{id}`  
- **读历史快照：** `read_thread_history`  
- **续跑：** 同 `thread_id` 再 `run_manus`（从**最新**状态继续；专用「回滚到第 N 步」API 仍后置）

### 2.3 任务信息层 vs checkpoint（S6 要分清）

| 层 | 存什么 | 谁写 |
|----|--------|------|
| **Checkpoint（已有）** | 可恢复图状态：messages、plan、step… | LangGraph 自动 |
| **TaskInfo（S6）** | 任务名片：id、thread_id、title、status、created_at、updated_at、可选 user 备注 | 我们在 `run_manus` 开跑/结束时 upsert |
| **Event log（已有）** | 给人看的过程轨迹 | CE-5 |

**工程师评审（同意你「先建类」的方向，但有边界）：**

- **优点：** 多会话列表、SSE 关联、HITL 挂起、评测集都需要稳定的 `task_id`；早点有模型能降低后续改散装 dict 的成本。  
- **风险：** 若把 messages 再抄一份进 TaskInfo → 双源真相、难同步。  
- **约定：** TaskInfo **只元数据**；正文状态仍以 checkpoint 为准；`task_id` 可与 `thread_id` 相同（MVP）或一对一映射。

---

## 3. 步骤表

| 步 | 状态 | 做什么 | 工作目标（详细） | 如何测试 |
|----|------|--------|------------------|----------|
| **S0** | ✅ | 拍板 | SQLite；路径在仓库内；thread_id 默认随机，续跑回传 | 用户确认 |
| **S1** | ✅ | 依赖与配置 | `langgraph-checkpoint-sqlite`；`CHECKPOINT_*` | import / Settings |
| **S2** | ✅ | checkpointer 封装 | `checkpointing.py` 读写辅助 | `test_ca4_checkpoint` |
| **S3** | ✅ | 图 + `run_manus` | compile + thread 续跑 | 假模型续跑 |
| **S4** | ✅ | API | POST thread_id；GET threads | 已接线 |
| **S5** | ✅ | 文档 | records / 待办曾切 CA-5 | 文档链 |
| **S6** | ✅ | **TaskInfo + TaskStore** | `app/tasks/`；同库表 `manus_tasks`；run 开跑/结束挂钩 | `test_ca4_task_store` |

### S0 拍板（用户确认）

| 项 | 决定 |
|----|------|
| 后端 | **SQLite**（官方 `langgraph-checkpoint-sqlite` + Python sqlite3） |
| 路径 | **本项目** `artifacts/checkpoints/manus.sqlite`（`CHECKPOINT_SQLITE_PATH`） |
| thread_id | **默认程序随机 UUID**；续跑客户端回传 |
| CLI | 可选 `D:\support\sqlite\sqlite3.exe` 查看库（与运行时无关） |
| TaskInfo | **要做（S6）**；元数据与 checkpoint 分家 |

### S6 工作目标（详细，面向自学）

做完后系统里有一个清晰的 **「任务」对象**，而不是只有裸 `thread_id` 字符串。

1. **能力：** 创建/更新/按 id 查询任务；`run_manus` 开始时登记任务，结束时更新 `status`；列表最近 N 条便于以后 UI。  
2. **概念：** `TaskInfo` = 名片；`TaskStore` = 持久化（建议**同一 SQLite 文件另表** `manus_tasks`，或旁路 `artifacts/checkpoints/tasks.sqlite`——优先**同库另表**少文件）。  
3. **字段（MVP）：** `task_id`、`thread_id`、`title`（可取用户消息前 80 字）、`status`（running/completed/…）、`created_at`、`updated_at`；预留 `extra_json` 文本列便于扩展。  
4. **非目标：** 不存 messages；不做权限；不做分布式锁。  
5. **与前后关系：** 依赖 S0～S5 checkpointer；之后 CA-5 SSE / CA-6 HITL 用 `task_id` 关联事件。

---

## 4. 涉及文件

**已有：** `checkpointing.py`、`build.py`、`manus.py`、`main.py`、`test_ca4_checkpoint.py`  

**S6 预计：**

- `app/tasks/models.py`（`TaskInfo` dataclass/pydantic）  
- `app/tasks/store.py`（`SqliteTaskStore`）  
- `app/manus.py`（开跑/结束挂钩）  
- `app/main.py`（可选 `GET /agent/tasks`、`GET /agent/tasks/{id}`）  
- `tests/test_ca4_task_store.py`  

---

## 5. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 与 checkpoint 双写不一致 | Task 只元数据；status 以 run 结束结果为准 |
| 表与 LangGraph 表同库冲突 | 表名 `manus_tasks`，不碰官方 checkpoint 表名 |
| 范围膨胀 | 禁止把 messages 塞进 TaskInfo |

回滚：去掉 TaskStore 挂钩即可；checkpointer 仍可用。

---

## 6. 验收清单

- [x] SQLite checkpoint 文件生成；同 thread 续跑；state/history 可读  
- [x] 假模型单测（checkpointer）通过  
- [x] **S6：** `TaskInfo`/`TaskStore` 可 CRUD；`run_manus` 自动 upsert；单测绿  
- [x] **S6：** 任务名片 ≠ 图状态（见本文 §2.3）  

---

## 7. 收尾

CA-4 全完成。下一主线 **CA-5** SSE。
