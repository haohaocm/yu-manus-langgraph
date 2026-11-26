# 计划：SSE-TOK — 仅 summarize 正文 token 流式

> 状态：✅ **已完成**（2026-11-25）  
> 术语：SSE（Server-Sent Events）、token（词元）、summarize（总结节点）、stream_mode=updates（按图节点增量）

---

## 1. 背景与目标

**要解决：** CA-5 已能按图节点推 SSE；但「最终 answer」只在 `done` 时整包出现，观感像非流式。用户要的是 **ChatGPT 式正文打字机效果**，同时保留事件流的节点级进度。

**目标（确认后的流式思路）：**

| 通道 | 粒度 | 用途 |
|------|------|------|
| 事件流 | **整节点**（plan / reason / tools / summarize 起止） | 看 Agent 干了啥 |
| 最终 answer | **仅 summarize 内 LLM token 级** | 正文边生成边显示 |

**非目标：**

- 不改 `reason` / `plan` 为 token 流（可后置）  
- 不改 CA-6 HITL、不改写文件工作区（另题）  
- 不把整图改成纯 token 管道；`graph.stream(..., updates)` 仍保留

---

## 2. 现状

| 位置 | 行为 |
|------|------|
| `iter_manus_events` | `stream_mode="updates"` → `start` / `node` / `done` |
| `make_summarize_node` | `llm.invoke(prompt)` **整段返回** 再写 `final_answer` |
| `/stream` 前端 | `#answer` **只在 `done` 赋值**；`node` 不往答案框写 |
| 待办旧描述 | SSE-TOK =「reason 内 token」——**已过时，改为 summarize** |

---

## 3. 步骤表

### S0 — 对齐协议（事件形状）

| 项 | 内容 |
|----|------|
| **做什么** | 定 SSE 新增事件类型与字段，前后端同一份契约 |
| **工作目标** | 做完后：除原有 `start`/`node`/`done`/`error` 外，增加正文增量事件。**概念：** `token` = 模型输出的一小段文本增量（不必真是 1 个 BPE）。**形状建议：** `{"type":"token","node":"summarize","delta":"..."}`；可选 `{"type":"token_end","node":"summarize"}`。`done.answer` 仍带完整终稿（兼容旧客户端）。**边界：** 不在 `reason` 发 token。**关系：** S1～S3 都按此契约实现。 |
| **如何测试** | 文档/计划内贴示例 JSON；单测断言序列含 `token` |

### S1 — summarize 支持流式回调

| 项 | 内容 |
|----|------|
| **做什么** | `make_summarize_node`：有 writer/回调时用 `llm.stream`，否则仍 `invoke`（兼容 `run_manus` 非流式） |
| **工作目标** | 做完后：流式路径下每来一段 delta 就通知外层；节点结束 state 仍含完整 `final_answer`（与现语义一致）。**概念：** LangChain `ChatModel.stream` 产出 chunk，拼 content。**I/O：** 输入同现 prompt；输出 state 字段不变；副作用 = 多次回调 `on_delta(str)`。假模型需能逐段 yield。**边界：** 不改 reason。**关系：** 依赖 S0；交给 S2 接到 `iter_manus_events`。 |
| **如何测试** | 单测：假模型分 3 段 stream → 回调收到 3 次 → `final_answer` 为拼接全文；无回调时 `invoke` 行为与现一致 |

### S2 — `iter_manus_events` 转发 token

| 项 | 内容 |
|----|------|
| **做什么** | 流式跑图时把 summarize 的 delta yield 为 `type=token`；`node=summarize` 仍在节点结束推一条（可缩短 preview，避免与 token 三重重复） |
| **工作目标** | 做完后：客户端先持续收 `token`，再收 `node(summarize)` / `done`。**难点：** 标准 `graph.stream(updates)` 只在**节点结束后**给 update；token 必须在节点**内部**通过自定义通道漏出（例如：thread-local / 闭包 queue / LangGraph `StreamWriter` 若可用）。选一种简单、可测的方案写进实现注释。**边界：** 不保证多并发同一进程多请求的完美隔离以外的花活；单请求正确即可。**关系：** 依赖 S1；S3 前端消费。 |
| **如何测试** | `pytest`：假模型图 → 事件序列含 `start` →（可选中间 node）→ 多个 `token` → `node summarize` → `done`，且 `''.join(deltas)==done.answer` |

### S3 — `/stream` 前端打字机

| 项 | 内容 |
|----|------|
| **做什么** | 收到 `token` 往 `#answer` 追加；`done` 用终稿校正一次；事件流逻辑基本不动 |
| **工作目标** | 做完后：用户眼见正文逐段出现；事件流仍按节点刷。**边界：** 不做 Markdown 实时渲染美化。**关系：** 依赖 S0/S2。 |
| **如何测试** | 手工：`/stream` 提一短问，答案区边出边长；事件流仍有 reason/tools/summarize 条 |

### S4 — 文档与待办

| 项 | 内容 |
|----|------|
| **做什么** | records、CA 总览流式说明、归档一行 |
| **工作目标** | 后人只读待办/总览就知道「节点事件 + summarize 正文 token」 |
| **如何测试** | 文档互链无死链 |

---

## 4. 涉及文件

| 路径 | 变更 |
|------|------|
| `app/graph/nodes.py` | summarize：`stream` + 可选 on_delta |
| `app/graph/build.py` | 若需传入 writer/回调 |
| `app/manus.py` | `iter_manus_events` 发 `token`；减轻 summarize `node` 重复字段 |
| `app/main.py` | `_STREAM_HTML` 消费 `token` |
| `tests/test_ca5_stream.py` 或新建 `tests/test_sse_tok_summarize.py` | 假模型序列断言 |
| `doc/development/plans/` / `records/` / `待办清单.md` | 本计划落地后更新 |

---

## 5. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 节点内无法边跑边 SSE（被 updates 挡住） | 用队列/StreamWriter 在 invoke 线程推；测不通则改为「自定义跑 summarize、图外 stream」小重构 |
| 假模型不支持 stream | 测试用可迭代 chunk 的 Scripted 模型 |
| 前端与 `done` 重复闪烁 | `done` 时整段替换为权威终稿一次即可 |
| 回滚 | 关掉 token yield + summarize 回到 `invoke`；前端忽略未知 `type` |

默认：`run_manus`（非 SSE）行为不变。

---

## 6. 验收清单

- [x] 假模型：`token` 增量拼接 == `done.answer`  
- [x] `/stream`：答案区边收边显示；事件流仍按节点出现（前端已改，需重启应用后手工看）  
- [x] `run_manus` / 非流式单测不回归  
- [x] 文档流式思路已改为「节点事件 + summarize token」；待办 SSE-TOK 描述同步  
- [x] **不**对 reason 做 token 流  

---

## 7. 落地说明

实现要点：`get_stream_writer` + `stream_mode=["updates","custom"]`；假模型 `ScriptedChatModel._stream` 按字符切片。  
records：[`../../records/2026-11-25-SSE-TOK-summarize正文流式.md`](../../records/2026-11-25-SSE-TOK-summarize正文流式.md)
