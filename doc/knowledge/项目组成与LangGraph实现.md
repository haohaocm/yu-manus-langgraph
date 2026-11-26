# yu-manus-langgraph：项目组成与 LangGraph 实现说明

> 本文说明 **当前 Python Manus 项目** 的边界、目录、运行时依赖，以及 LangGraph 如何对应原 Java YuManus。  
> 文档分类见 [`../README.md`](../README.md)；学习路线与待办见 [`../development/`](../development/)。

---

## 1. 和周边目录的关系（先分清边界）

在 `C:\Users\hhcm\Desktop\123\开发\` 下有多个目录，**本项目只指 `yu-manus-langgraph`**：

| 目录 | 是否本项目 | 说明 |
|------|------------|------|
| **yu-manus-langgraph** | ✅ 是 | 用 LangGraph 重构的 YuManus（Python） |
| yu-ai-agent（`E:\project\java\yu-ai-agent`） | 参考源 | 原 Java Spring AI 版；含 LoveAgent / YuManus / LabEnv |
| MCP工具网关-mcp-gateway | 运行时依赖 | 工具执行在网关；本项目经 MCP 调用它 |
| **agent-core** | ❌ 暂不考虑 | 早期「连网关 + 调模型」的 **中间/学习用 Java 客户端**，不是本次重构目标 |
| 其它（星座展示、实时拓扑等） | ❌ | 无关 |

**结论：** `agent-core` 属于开发过程中的中间项目，**不算在本次「外面要交付的 Manus 重构」范围内**；当前主线是 `yu-manus-langgraph` ↔ MCP 网关 ↔ Qwen（vLLM）↔ **bge（embeddings）**。

**启动步骤（含双隧道）：** [`../development/项目启动清单.md`](../development/项目启动清单.md)

---

## 2. 本项目要解决什么

把 Java 版 `YuManus`（`BaseAgent` → `ReActAgent` → `ToolCallAgent`）的核心能力迁到 Python：

- ReAct 循环：思考（reason）→ 调工具（tools）→ 再思考…
- 系统提示 + 每步 next-step 提示
- 工具来自 MCP 网关（可选）；本地保留 `terminate`、读仓与 `semantic_search`
- 步数上限 `max_steps`；终态见 `ending.py`（`completed` / `abandoned` / `budget_exceeded`，预留 `cancelled`）
- 对外提供 HTTP，便于以后 Java 只做转发
- 小仓库检索：BM25 + **bge embedding** + hybrid（混合检索）

**当前不做：** LoveAgent RAG / PGVector 全量迁移、Java 转发层、多轮会话持久化、完整 Cursor 级产品壳。

---

## 3. 运行时拓扑

```
浏览器 / curl
    │  POST /agent/run  或  页面 GET /  /embed-compare
    ▼
yu-manus-langgraph  (:8200)
    │  LangGraph: reason ⇄ tools
    ├─► ChatOpenAI ──► 本机隧道 :18000 ──► 实验室 vLLM Qwen :8000
    ├─► HttpOpenAIEmbedder ──► 本机隧道 :18001 ──► 实验室 bge-m3 :8001
    └─► MCP Client ──► mcp-gateway :8090/mcp ──► 业务工具（add/echo/…）
```

| 依赖 | 本机 | 用途 |
|------|------|------|
| Qwen | `:18000` | Agent 对话 |
| **bge-m3** | `:18001` | embedding / `semantic_search`（**无 stub 回退**） |
| MCP（可选） | `:8090` | 网关工具 |

环境变量见 `.env` / `.env.example`（`OPENAI_BASE_URL`、`EMBEDDING_*`、`MCP_*` 等）。

---

## 4. 目录组成

```
yu-manus-langgraph/
├─ app/
│  ├─ main.py           # FastAPI：/、/embed-compare、/agent/run、/docs
│  ├─ manus.py          # 对外入口 run_manus()
│  ├─ config.py         # pydantic-settings（含 EMBEDDING_*）
│  ├─ llm.py            # ChatOpenAI（trust_env=False）
│  ├─ prompts.py        # SYSTEM / NEXT_STEP
│  ├─ search/           # chunking / BM25 / embed / hybrid
│  ├─ context/          # event log、近窗
│  ├─ graph/            # state / nodes / build
│  └─ tools/            # fs / search / MCP / terminate
├─ artifacts/corpus/    # CE-6 语料；索引在 search_index/
├─ tests/
├─ doc/
├─ requirements.txt
└─ README.md
```
---

## 5. 与 Java YuManus 的对应关系

| Java | Python（本项目） |
|------|------------------|
| `BaseAgent.run` + `maxStep` | `run_manus` + `ManusState.max_steps` / `step` |
| `ReActAgent` think / act | 节点 `reason` / `tools` |
| `ToolCallAgent` + `ToolCallback[]` | `bind_tools` + `ToolNode` + `load_agent_tools` |
| `TerminateTool` | 本地工具 `terminate` |
| `messageList` | `ManusState.messages`（`add_messages`） |
| `AgentStatus` | `ManusState.status`：`running` / `completed` / `abandoned` / `budget_exceeded` / `cancelled`（预留） |
| Spring MVC 控制器 | FastAPI `main.py` |

---

## 6. LangGraph 如何实现（核心）

### 6.1 状态（State）

`ManusState` 在图的每一步节点之间传递：

- `messages`：对话与工具结果（用 `add_messages` 追加，不覆盖）
- `step` / `max_steps`：当前步与上限
- `status` / `end_reason`：终态与原因（`app/graph/ending.py`）
- `step_logs`：类似 Java 的 `stepN : ...` 文本轨迹

### 6.2 图结构

```
START → reason ──(有 tool_calls)──► tools ──(未结束)──► reason → …
              └─(无工具 / 结束)──► END
                         └─(terminate / 超步)──► END
```

- **reason**：绑定工具的 LLM 调用；注入 `SYSTEM_PROMPT` + 历史 + `NEXT_STEP_PROMPT`（对齐 Java 每轮 think）
- **tools**：`ToolNode` 执行工具；仅 `terminate(outcome=…)` 写入 `completed`/`abandoned`
- **条件边**：`route_after_reason` / `route_after_tools` 决定下一跳

`build_manus_graph()` 用 `StateGraph(ManusState)` 注册节点与边后 `compile()`。

### 6.3 工具加载

- `MCP_ENABLED=false`：`terminate` + 本地 `add` / `echo`（便于无网关单测）
- `MCP_ENABLED=true`：`terminate` + 网关 `list_tools` 转成 `StructuredTool`（参数 schema 来自网关 JSON Schema）

### 6.4 HTTP 入口

- `POST /agent/run`：正式 JSON 接口
- `GET /agent/run`：说明用法（避免浏览器地址栏 GET 得到 405）；可带 `?message=` 调试
- `GET /`：简易试跑页
- `GET /docs`：OpenAPI

---

## 7. 测试分层

| 测试 | 依赖 | 作用 |
|------|------|------|
| `test_phase0_*` | 无外部服务 | 配置 / 导入 |
| `test_phase1_*` | 脚本化假模型 | 图循环、terminate |
| `test_phase2_*` | Fake MCP | 工具加载与转发 |
| `test_phase3_*` | TestClient | HTTP 契约 |
| `test_e2e_live.py` | Qwen 隧道 + 网关 | 真模型联调（`RUN_LIVE_E2E=1`） |
| `test_search_*` / EMB | **bge 隧道 `:18001`** | hybrid / embedding；连不上则 fail |

---

## 8. 常用命令

```powershell
cd "C:\Users\hhcm\Desktop\123\开发\yu-manus-langgraph"
.\.venv\Scripts\Activate.ps1
# 先确认 18000（Qwen）与 18001（bge）可用，见项目启动清单
pytest -q
python -m app.main
# Agent：http://127.0.0.1:8200/
# bge 试玩：http://127.0.0.1:8200/embed-compare
```

前置：实验室 Qwen + **bge** → 本机隧道 **18000 + 18001** →（可选）MCP 8090 → 本服务 8200。  
细节：[`../development/项目启动清单.md`](../development/项目启动清单.md)。

---

## 9. 后续可选

- **CA-1**～**CA-4**（✅）：写文件 / run_shell / Plan / SQLite Checkpointer；下一指针 **CA-5** SSE  
- **IDX-INC** / **VEC-DB** / **CHUNK-AST**：检索增强（见待办中优）  
- Java 薄转发、多轮记忆、SSE、HITL 等（见待办）

全仓索引已落地：`SEARCH_MODE=workspace` + `semantic_search`；重建见 `python -m app.search.reindex`。
