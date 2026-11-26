# 计划：默认工作区落位 + `/stream` 续聊可见上下文

> 状态：✅ **已完成**（2026-11-25）

## 背景与目标

1. Agent 写文件勿默认落仓库根；默认沙箱 `artifacts/agent_workspace`。换工程 = 改 `WORKSPACE_ROOT`。  
2. CE-5 近窗已实现，但 `/stream` 每次不传 `thread_id` → 每次新会话，看起来「没上下文」。试玩页保留/续传 `thread_id`。

## 非目标

改检索 Demo 默认仓、CTX-1 完备摘要、HITL。

## 步骤（压缩）

| 步 | 做什么 | 如何测 |
|----|--------|--------|
| A | 默认 `workspace_root=artifacts/agent_workspace`；建目录；gitignore；`.env.example`/清单 | `get_workspace_root()` 指向该目录；写文件单测仍用 tmp |
| B | `/stream` 记住 `thread_id`，可「新对话」清空 | 手工：第二轮问「我刚才叫你做什么」能接上 |
| C | 文档/待办一行 | 归档 |

## 等待确认

用户已要求修改 → 本轮直接落地。
