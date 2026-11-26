# yu-manus-langgraph

用 **LangGraph** 实现的 Cursor 类 Agent（YuManus 路线）：可检索、可改文件、可跑命令、可计划、可断点、可 SSE、可 HITL、可固定题评测。

**版本：** `0.0.1`  
**完成情况：** [`doc/development/平台完成情况-v0.0.1.md`](doc/development/平台完成情况-v0.0.1.md)  
**每日待办：** [`doc/development/待办清单.md`](doc/development/待办清单.md)  
**启动清单：** [`doc/development/项目启动清单.md`](doc/development/项目启动清单.md)

## 功能一览（v0.0.1）

| 能力 | 说明 |
|------|------|
| Agent 图 | Plan（可选）→ reason ⇄ tools → summarize |
| 写/改文件 | 沙箱内 `write_file` / `str_replace`（默认工作区 `artifacts/agent_workspace`） |
| Shell | 受控 `run_shell` |
| 检索 | hybrid + `semantic_search`（需 bge） |
| 流式 | SSE 节点事件 + summarize 正文 token（`/stream`） |
| HITL | 写文件/shell 前人工批准/拒绝 |
| 评测 | `python -m evals.ca7.run_ca7` |

**产品壳：** 暂用现有 `/stream` 试玩页；后续前端优化见待办 **FE-OPT**（中）。

## 快速开始

```powershell
cd yu-manus-langgraph
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # 按需改 OPENAI_BASE_URL / WORKSPACE_ROOT / HITL_ENABLED
```

真联调需隧道：

| 服务 | 本机 | 用途 |
|------|------|------|
| Qwen（vLLM） | `127.0.0.1:18000` | 对话 |
| bge-m3 | `127.0.0.1:18001` | embedding / 检索 |

```powershell
.\scripts\ensure_env.ps1          # 检测；缺服务可 -StartMissing
python -m app.main                # http://127.0.0.1:8200
```

| 页面 | URL |
|------|-----|
| SSE + HITL | http://127.0.0.1:8200/stream |
| 非流式 | http://127.0.0.1:8200/ |
| 检索试玩 | http://127.0.0.1:8200/embed-compare |
| OpenAPI | http://127.0.0.1:8200/docs |

## 测试与评测

```powershell
pytest -q
python -m evals.ca7.run_ca7              # 含真模型题（需 18000）
python -m evals.ca7.run_ca7 --offline-only
```

## 目录

| 路径 | 内容 |
|------|------|
| `app/` | Agent、图、工具、HITL、FastAPI |
| `evals/ca7/` | 固定题评测 |
| `scripts/` | 环境启停检测 |
| `doc/` | 知识 / 计划 / 待办 / records |

## License

学习/实验用途；使用前请配置自有模型与密钥，勿提交 `.env`。
