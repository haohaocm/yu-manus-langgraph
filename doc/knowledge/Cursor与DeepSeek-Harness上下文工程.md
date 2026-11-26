# Cursor 与 DeepSeek Harness 的上下文工程（详解）

> 目标：搞懂「模型每一步到底看见什么、怎么少塞垃圾、长任务怎么不崩」。  
> 依据：Cursor 官方博客（公开部分）；DeepSeek Harness 开源文档（可对照源码）。  
> 说明：Cursor 内部实现未开源，下文写的是其**公开披露的设计**；Harness 可精确到包职责。

---

## 0. 什么叫上下文工程？

不是「把 system prompt 写漂亮」而已，而是一整套：

1. **选**：哪些信息值得进窗口（检索 / 工具结果 / 规则）  
2. **装**：按什么顺序、什么角色、什么 schema 发给模型  
3. **控**：工具描述、历史、长输出如何防止撑爆 token  
4. **压**：超长时摘要/折叠，且还能找回细节  
5. **观**：能否复盘「某次请求实际发了什么」

一句话：**上下文工程 = 控制「模型每一步的输入分布」**。

---

## 1. 两个产品的定位差异

| | **Cursor Agent** | **DeepSeek Harness（dsh）** |
|--|------------------|----------------------------|
| 形态 | IDE 内编码 Agent（闭源 harness） | 开源「一切皆插件」Agent 运行时 |
| 强项场景 | 大仓库读改跑、语义/精确搜索、产品化体验 | 可扩展装配：prompt 段、工具、会话、压缩可插拔 |
| 上下文哲学（公开） | **Dynamic context discovery**：少静态塞，多按需拉 | **agent-loop 组装**：system + tools + 由 session log 派生的历史；超长走 compaction |
| 你能学到什么 | 产品级「省 token + 不丢信息」手法 | 工程级「谁组装、谁注入、谁压缩」分层 |

二者并不互斥：做 Cursor 类系统时，**Cursor 给「招式」，Harness 给「骨架」**。

---

## 2. Cursor：上下文工程怎么做（公开设计）

### 2.1 总思路：Dynamic Context Discovery

Cursor 明确对比了两种模式：

- **Static context**：一上来全塞进 prompt（规则、工具说明、大段日志……）  
- **Dynamic context discovery**：静态只给「线索」，真正内容由 Agent **用工具自己拉**

原因：模型更擅长当 Agent 后，「少给细节、让它自己取」往往 **更省 token、也更少被矛盾信息带偏**。

### 2.2 代码库如何进入「可检索世界」（不是一次塞进窗口）

公开描述的流水线大致是：

1. **索引，而非整库进上下文**  
   - 文件切成 **句法块（syntactic chunks）** → **embedding** → 语义检索  
   - 另有本机高速 **精确/正则搜索（Instant Grep）**，符号名、报错串优先走它  
2. **增量同步**  
   - 用 **Merkle 树** 对文件/目录哈希，只同步变更路径；embedding 按 chunk 内容缓存，未改块可命中缓存  
3. **Agent 检索时**  
   - 按需打开匹配片段；**不是**把整个 index 倒进上下文  
4. **Explore 子代理**  
   - 大范围搜索可放到 **独立上下文窗口** 的 Explore subagent（更快模型、可并行搜）  
   - 只把 **摘要/结论** 回主对话，避免主会话被搜索过程撑爆  

语义检索还用 Agent 真实工作轨迹做反馈训练 embedding（「事后看本该更早检索到什么」），提升「自然语言问代码位置」的命中——这对大仓库很关键。

### 2.3 五条「动态发现」落地手法（Cursor 博客）

#### （1）长工具结果 → 写成文件，再按需读

- 问题：shell / MCP 大 JSON 直接回灌会爆窗口；简单截断会丢关键信息。  
- 做法：输出 **落到文件**；Agent 用 `tail` / 再 `read` 需要的部分。  
- 效果：减少「因为上下文满了而被迫摘要」。

#### （2）摘要时仍保留「可搜索的历史文件」

- 窗口满 → **summarization** 开新窗口（有损）。  
- 做法：历史当作 **文件引用** 留给 Agent；摘要里缺细节时，可再 **搜历史** 找回。  
- 要点：**压缩可见上下文 ≠ 删除真相源**。

#### （3）Agent Skills（技能）按需拉取

- Skills：领域任务说明书（+ 可带脚本），类似可发现的 Rules。  
- 静态：可只放 name/description；  
- 动态：用 grep / 语义搜索把相关 Skill **拉进** 当前任务。

#### （4）MCP 工具：不全量塞 schema

- 问题：多个 MCP、工具描述很长 → 大量工具永远不用也占满前缀。  
- 做法：工具描述 **同步到文件夹**（按 server 分目录）；静态只给少量线索（如工具名），需要时再 list/读描述。  
- A/B：在「确实调用了 MCP」的运行里，总 token 约降 **46.9%**（方差大，取决于装了多少 MCP）。  
- 额外收益：可表达「某 MCP 需重新登录」等状态（工具「消失」不如「可见但提示鉴权」）。

#### （5）集成终端输出也当文件

- IDE 终端历史同步到本地文件；用户问「命令为啥挂了」时，Agent **grep 相关日志**，而不是整段粘贴进输入框。

### 2.4 Cursor 侧可提炼的「设计口诀」

1. **Index for retrieval, load for reasoning**（索引为了找，进窗为了想）  
2. **Files as the universal spillway**（长东西先落盘）  
3. **Subagent for exploration**（探索与主决策分窗）  
4. **Names static, bodies dynamic**（MCP/Skills：名录静态、正文动态）  
5. **Summary + recoverable source**（摘要 + 可回查原文）

---

## 3. DeepSeek Harness：上下文工程怎么做（开源结构）

### 3.1 先纠正常见误解

很多人以为「`context/` 包负责拼上下文」。  
Harness 文档的分工是：

| 层 | 职责 | 归属 |
|----|------|------|
| **组装主体** | 每步把 system prompt + tool schemas + **派生历史** 打成一次模型请求 | **agent-loop**（`buildRequest` / `assembleContextFor`） |
| System prompt 注册表 | 插件按 order 贡献段落、变量、工具 schema | `core/system-prompt` |
| 工具如何呈现 | native / ptc / both | `core/tools` + presentation |
| 会话历史 | **追加事件日志** → 投影成「模型可见消息」 | `core/session` |
| 额外注入 | 文件引用、时间、tmux、工作区说明等（**不定义工具**） | `context/*` |
| 过长处理 | **compaction（折叠）**，不是砍头 truncation | `compaction/*` |

口诀：**组装是 loop 的事；`context/*` 只是可选加料；压缩是折叠可见面，日志仍在。**

### 3.2 一次请求里模型看见什么

逻辑上（每一步）：

```
system prompt（按 order 拼好的各 section + 变量渲染）
+ tool schemas（与「能做什么」视为同一套装配）
+ derived messages（从 session event log 投影出来的表面历史）
+ （可选）context/* 在 pre-step 注入的额外可见消息
```

要点：

- **Session 是 event-sourced**：append-only 日志是真相；发给模型的是 **deriveMessages()** 投影。  
- 失败/取消的 attempt 可留在日志里但不一定进入表面历史。  
- System prompt 可记入 session（如 `system/message`），便于审计「当时拼了啥」。  
- 请求还有 **request header**（模型、maxTokens、tools 列表等），便于 KV cache / 复盘。

### 3.3 System prompt：可插拔、有序、严格变量

插件通过例如：

- `section({ name, order, text })`：按 **order 升序** 拼接  
- `context({ ... })`：动态上下文（按次求值）  
- `tools(provider)`：工具 schema 贡献  
- `variable(name, provider)`：`{{var}}` **严格插值**（未注册就失败，有利于稳定前缀 / KV-cache）

order 约定示例（文档）：负值 harness 身份 → 人设前缀 → 策略段 → 工具指导 → … → 人设后缀。  
可用 `complete: true` 表示「只要这一段」等高级约束。

### 3.4 `context/*` 注入源（加料，不装工具）

例如：

- 其它 session 的有界引用  
- 文件引用（定义 + 本地搜索后端）  
- 时间 / tmux 位置（可选）  
- 工作区指令（agent-instructions）

通常在 `agent/pre-step` 注入为模型可见消息；**不走** system-prompt 的 order 注册表。

### 3.5 Compaction：折叠而不是截断

长会话：

- **不是**简单丢掉最早若干条；  
- 而是把一段历史的 **模型可见面** 换成 summary/report（「遮蔽」）；  
- **完整事件日志仍持久化**，需要时可再派生/查阅。

这与 Cursor「摘要 + 历史文件可搜」是同一哲学的不同实现：**有损可见层 + 无损真相层**。

### 3.6 与 Hooks / Skills / MCP 的关系（影响上下文）

- **Hooks**（如 PreToolUse / UserPromptSubmit）：可拦截、改写、或通过 stdout **追加注入指令**。  
- **Skills**：可复用的 Markdown 能力说明（偏「持久说明书」）。  
- **MCP Client**：外接工具；工具 schema 仍进入「装配整体」，需要自己注意膨胀（Cursor 用「文件夹动态发现」优化这一点，Harness 则可在插件层做类似策略）。

### 3.7 Harness 侧可提炼的「设计口诀」

1. **One assembler（agent-loop）**  
2. **Event log is source of truth**  
3. **Prompt = ordered plugin sections**  
4. **Inject ≠ assemble**（`context/*` 加料）  
5. **Compact by folding, not chopping**  

---

## 4. 对照表（方便背）

| 维度 | Cursor（公开） | DeepSeek Harness |
|------|----------------|------------------|
| 静态 vs 动态 | 强调 dynamic discovery | 每步 loop 组装；额外源可动态注入 |
| 代码库 | 索引 + grep + 语义检索 + Explore 子代理 | 文件引用等插件；编码能力靠工具/插件 |
| 长输出 | 落盘再读 | 由工具与注入策略决定；历史靠 log+投影 |
| 工具描述膨胀 | MCP 描述进文件夹，按需看 | schema 进装配；可用插件自制「按需」 |
| 超长会话 | Summarize + 历史可搜 | Compaction 折叠可见面，log 保留 |
| 可扩展性 | 产品内 Skills/Rules/MCP | 插件 / Cordis「一切皆插件」 |
| 可审计 | 产品行为；细节闭源 | session JSONL + request header 可查 |

---

## 5. 对本项目（yu-manus-langgraph）的启示

当前实现更接近「**小型静态+全量工具 bind**」：

- `SYSTEM` + `NEXT_STEP` + 全量 `messages` +（MCP 开启时）**整表工具 schema** 绑给模型  
- `step_logs` 便于人看，但还不是 event-sourced session  
- 长工具结果直接进 `ToolMessage`，**尚未落盘**

建议对齐业界的最小升级路径（已写入待办 CE-2～CE-5）：

| 步骤 | 做法 | 更像谁 |
|------|------|--------|
| 1 | 加 `read_file` / `grep`，让模型自己拉代码 | Cursor 检索习惯 |
| 2 | 工具输出超长 → 写临时文件，回路径 | Cursor (1) |
| 3 | MCP：静态工具名录，schema 按需 | Cursor (4) |
| 4 | 全量事件日志 + 发给模型的窗口/摘要 | Harness session + Cursor (2) |
| 5 | （可选）探索类搜索用子图/子 Agent | Cursor Explore |

**不要一上来重写框架**：先在现有 LangGraph `reason ⇄ tools` 上加「发现型工具」和「输出落盘」。

---

## 6. 延伸阅读（原文）

- Cursor：[Dynamic context discovery](https://cursor.com/blog/dynamic-context-discovery)  
- Cursor：[Semantic search](https://cursor.com/blog/semsearch) · [Secure codebase indexing](https://cursor.com/blog/secure-codebase-indexing) · [Search / Explore](https://cursor.com/docs/agent/tools/search)  
- DeepSeek Harness：[The Context System](https://deepseekdocs.com/en/docs/learn/core/context) · [GitHub deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)

---

## 7. 学习检查清单

读完本文后，应能口头答出：

1. 什么是 dynamic context discovery？和「静态塞满」差在哪？  
2. Cursor 为何把长 MCP/终端输出写成文件？  
3. Harness 里谁负责「组装」？`context/*` 做什么、不做什么？  
4. compaction / summarization 为何都强调「保留可回查源」？  
5. 我们项目下一步最小改动是哪两步？（答案：检索工具 + 长输出落盘）
