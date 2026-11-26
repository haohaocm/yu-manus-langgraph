# Agent 结束策略：你的方案 vs 更成熟做法

> 适用项目：`yu-manus-langgraph`  
> 关联计划：[`../development/plans/2026-11-19-结束策略三种出口.md`](../development/plans/2026-11-19-结束策略三种出口.md)  
> 目的：把「要不要单独做一个结束函数、每步跑一遍」这件事讲清楚，便于后续实现不走弯路。

---

## 1. 先对齐：结束策略在解决什么

Agent 循环（ReAct）若不加约束，可能：

- 永远调工具、不给用户最终答复  
- 任务已完成却继续空转  
- 做不到也不说明原因  
- 步数/预算打满时静默失败或抛栈

因此需要 **明确的结束语义**：什么时候停、以什么身份停、停完后用户看到什么。

本项目约定三种（用户取消暂缓）：

| 出口 | 含义 | 典型触发 |
|------|------|----------|
| **成功结束** | 任务已完成（或已给出完整答复） | `terminate(outcome=success)`；或模型直接文本回复且无 tool_calls |
| **正常放弃** | 判断当前无法完成，但有结论 | `terminate(outcome=abandon, reason=…)` |
| **资源耗尽** | 系统强制停，不是模型「甘愿结束」 | `step > max_steps`；（以后）token 预算用尽 |

无论哪种出口，成熟产品几乎都：**先收口状态 → 再 Summarizer 写给人看的话 → 再 END**。  
「对内 status / end_reason」和「对外 answer」要分开。

---

## 2. 你的方案：核心想法

可以概括成两句话：

1. **把三种结束规则集中写进一个函数（或一个模块）**，避免逻辑散落在 reason、tools、路由各写一份。  
2. **每次任务（或每一步）执行完，再额外跑一遍这个函数**，统一判断「该不该结束」。

示意（概念上，不是当前代码）：

```text
reason / tools 跑完
       ↓
  check_should_end(state)   ← 你设想的「额外一步」
       ↓
  该停？ → summarize → END
  不该？ → 继续 reason
```

下面分开看：**哪些是对的、值得保留**；**哪些可以改成更稳的形态**。

---

## 3. 你的方案里「对的部分」（应保留）

### 3.1 结束规则要「单点定义」

三种出口的判定条件、写入的 `status`、`end_reason` 文案约定，应有 **唯一权威来源**（例如即将增加的 `ending.py`）。

否则常见问题是：

- `tools` 里写 `finished`，路由里又认 `error`，Summarizer 只处理其中一种  
- 超步有的地方叫 `error`，有的地方叫 `failed`，API 与测试对不齐

**结论：**「单独做成一套结束相关函数/模块」——方向正确，和大厂「策略集中、调用分散」一致。

### 3.2 用显式出口，而不是只靠模型「不再说话」

成熟系统很少只依赖「模型哪天不调工具了就算成功」。通常还有：

- 显式工具或动作：`terminate` / `final_answer` / `submit_result`  
- 硬约束：`max_steps`、超时、token 预算  
- （产品侧）用户取消

你把成功 / 放弃 / 资源耗尽拆开，而不是糊成一个 `finished`——**语义正确**，后面做监控（放弃率、超步率）也靠这个。

### 3.3 结束之后仍要 Summarize

停下来不等于把 `step_logs` 甩给用户。成功、放弃、耗尽都应进入总结节点，只是话术不同：

- 成功：直接回答问题  
- 放弃：说明做不到什么、已知什么  
- 耗尽：承认未完成 + 已有部分结果  

你强调「放弃也要进 summarize 说清原因」——**与当前图设计一致，也是产品正确做法**。

### 3.4 用户取消可以后做

第四种「用户点击停止」依赖可取消的执行模型（异步任务、流式 + cancel）。先做 1～3 种——**排期正确**。

---

## 4. 可以更好的部分：不要做成「每步后再挂一个结束阶段」

### 4.1 问题在哪

「每次执行完再额外跑一遍大检查函数」容易演变成：

```text
reason → tools → EndChecker节点 → reason → …
```

或在 `run_manus` 外包一层 while + 每步 `check_end()`。

这会带来：

| 问题 | 说明 |
|------|------|
| **与条件边重复** | LangGraph 已有 `route_after_reason` / `route_after_tools`；再套一层结束扫描，两处都可能改 `status`，难推理 |
| **时机含糊** | 「任务执行完」是指一次工具？一轮 reason？整次 run？三种结束的触发点本来就不在同一时刻 |
| **重复判读** | 工具刚返回 `terminated:`，节点里已能定 `completed`；若后再扫一遍，要防止覆盖或双写 |
| **测起来重** | 端到端才能测「检查器」；纯规则本可以几十个单测用例秒过 |

也就是说：**集中规则是对的；把「集中」理解成「图上多一个总检查阶段」通常多余。**

### 4.2 更成熟的结构：事件点写状态 + 纯函数裁决 + 路由只问一句

```text
┌─────────────────────────────────────────────────────────┐
│  ending.py（纯函数，无 I/O）                              │
│  - on_terminate(outcome, reason) → status, end_reason   │
│  - on_no_tool_calls()            → completed + …        │
│  - on_budget_exceeded(step, max) → budget_exceeded      │
│  - should_end(state) → bool                             │
└─────────────────────────────────────────────────────────┘
         ↑ 事件发生时调用              ↑ 路由调用
┌──────────────────┐         ┌────────────────────────────┐
│ reason / tools   │         │ route_after_reason/tools   │
│ 改 messages 等    │         │ should_end? → summarize    │
│ 并写入 status    │         │ else → tools / reason      │
└──────────────────┘         └────────────────────────────┘
```

**含义：**

1. **规则集中在 `ending.py`**（满足你「单独一个函数/模块」的诉求）。  
2. **谁撞上结束事件，谁立刻调用对应函数写 `status`**（不是步后再盲扫）。  
3. **路由不重新发明三种业务含义**，只问 `should_end(state)`，决定下一跳。  
4. **Summarize / END** 仍是图上的收口，不负责「发现」结束原因。

这与状态机常见写法一致：**transition 在事件上发生；guard（是否结束）读当前状态。**

### 4.3 三种结束各自应挂在哪个事件点

| 出口 | 更自然的触发点 | 为何不是「步后统一扫」 |
|------|----------------|------------------------|
| 成功 | `tools` 执行完发现 `terminate(success)`；或 `reason` 发现无 tool_calls | 信号已在本节点的输入/输出里 |
| 放弃 | `tools` 发现 `terminate(abandon)` | 同上；原因在 tool 参数里 |
| 资源耗尽 | `reason` **入口**发现 `step > max_steps`（或累计 token 超限） | 属于「不允许再思考」，应在调 LLM 前拦截 |

「步后扫一遍」也能工作，但会把上述三种不同时机揉成同一种调度，可读性和单测都变差。

### 4.4 和本仓库现状的对应

当前已接近成熟形态的雏形：

- `reason`：无 tool_calls → `finished`；超步 → `error`  
- `tools`：见到 `terminate` → `finished`  
- `route_after_*`：`status in (finished, error)` → `summarize`

差距主要在 **语义命名**（`completed` / `abandoned` / `budget_exceeded`）和 **把判定收进纯函数模块**，而不是再加一个 EndChecker 节点。

---

## 5. 对照总表

| 维度 | 你的方案 | 更成熟做法 | 关系 |
|------|----------|------------|------|
| 三种出口拆分 | ✅ | ✅ 同 | 直接保留 |
| 规则集中 | ✅ 单独函数 | ✅ 单独模块 + 多个小纯函数 | 保留并细化 |
| 调用方式 | 每步后额外执行一遍 | 事件点调用 + 路由 `should_end` | **这里升级** |
| 与 LangGraph | 易变成外挂阶段 | 条件边 + state 字段 | 贴合框架 |
| 测试 | 偏集成 | 纯函数单测 + 少量图测 | 成熟做法更易测 |
| Summarize | 结束要总结 | 同；按 status 换话术 | 保留 |
| 用户取消 | 暂缓 | 暂缓；以后 `cancelled` | 同 |

一句话：

> **保留「集中定义三种结束」；把「每步后再检查」改成「事件发生时写入 + 路由只读状态」。**

---

## 6. 推荐的最小 API 形态（实现时参照）

仅作知识约定，具体以已确认的开发计划为准：

```python
# 概念示例 —— 纯函数，不访问网络/模型

def on_terminate(outcome: str, reason: str) -> dict:
    """success → completed；abandon → abandoned；附带 end_reason。"""
    ...

def on_text_only_finish() -> dict:
    """reason 轮无 tool_calls：视为 completed（纯答复）。"""
    ...

def on_budget_exceeded(*, step: int, max_steps: int) -> dict:
    """→ budget_exceeded + end_reason。"""
    ...

def should_end(state: dict) -> bool:
    return state.get("status") in {
        "completed",
        "abandoned",
        "budget_exceeded",
        # 兼容旧值
        "finished",
        "error",
    }
```

节点内：

```text
若发生某事件 → state.update(on_xxx(...))
路由：should_end(state) ? "summarize" : "reason"|"tools"
```

---

## 7. 常见误区

1. **用 Summarizer 判断该不该结束**  
   总结器只负责「已经决定结束后怎么说话」，不负责发现结束。

2. **放弃当成 error**  
   放弃是模型有结论的正常出口；`budget_exceeded` / 未捕获异常才偏系统失败。监控上应分开。

3. **无 tool_calls 与放弃混用**  
   闲聊直接答完 → `completed`；明确做不到 → 应走 `terminate(abandon)`，并在 prompt 里写清。

4. **只加 max_steps，不写清对外语义**  
   超步后若仍返回含糊 `error` 且 answer 像成功，前端与评测都会误判。

5. **把「工具失败」当成「正常放弃」**  
   参数不对、工具抛错、返回内容异常 → 默认是 **错误回喂**，图继续 `reason`，让模型改参或换工具。  
   **正常放弃** = 模型（或上层策略）**显式**决定停，并给出做不到的原因（如 `terminate(abandon)`）。  
   二者都可能在 `tools` 节点附近被看到，但语义与是否结束完全不同。

6. **把成功也叫做「失败原因」**  
   更准确的说法是「终态 / 结束出口」：`completed` | `abandoned` | `budget_exceeded` |（预留）`cancelled`。  
   其中成功不是失败分类；失败/未成功侧主要是放弃与耗尽（以及以后的取消、系统 fault）。

---

## 8. 和后续工作的衔接

- **实现：** 按计划 LG-3 / `plans/2026-11-19-结束策略三种出口.md`（需你确认后再编码）。  
- **Token：** 可先累计 `token_usage` 做观测；硬上限打断与超步同一类「资源耗尽」事件，仍走 `on_budget_exceeded` 同源语义。  
- **用户停止：** 将来在运行句柄上设 `cancel_requested`，事件点同样调用 `ending` 写入 `cancelled`，路由 `should_end` 即可，不必再发明第四套调度框架。

---

## 9. 小结

| 你的判断 | 结论 |
|----------|------|
| 三种结束要说清 | ✅ 正确 |
| 结束逻辑应集中 | ✅ 正确 |
| 每次执行完再跑一遍检查函数 | ⚠️ 能跑，但不如「事件点写入 + should_end」清晰 |
| 放弃也进 summarize | ✅ 正确 |
| 用户取消后做 | ✅ 正确 |

**成熟做法的优点：** 与 StateGraph 条件边同构、无重复阶段、结束原因在触发点就可测、状态机可读、扩展第四种取消时零改调度骨架。
