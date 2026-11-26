# Changelog

## 0.0.1 — 2026-11-26

首个公开打包版本。

### 能力

- LangGraph Manus：Plan（可选）+ reason ⇄ tools + summarize
- 工具：读/写/shell/检索/terminate；默认工作区 `artifacts/agent_workspace`
- SSE：节点事件 + summarize token；`/stream` 续聊 thread
- HITL：写文件/shell 审批（interrupt + resume）
- 评测：`python -m evals.ca7.run_ca7`（离线 + 真模型题）

### 说明

- 需本机隧道 Qwen `18000`、bge `18001` 做真联调
- 产品壳暂用 `/stream`；UI 优化见待办 FE-OPT
