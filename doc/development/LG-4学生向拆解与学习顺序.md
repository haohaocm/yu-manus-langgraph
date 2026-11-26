# LG-4 学生向拆解：学什么、按什么顺序做

> 目的：把「写联调记录」背后的能力拆开，方便你当作业一步步学会。  
> 工程状态：LG-4 **最小交付已完成**（计划 + 脚本 + records）；下文含 **已会的** 与 **建议接着练的**。  
> 关联：[`plans/2026-11-19-LG4联调测试计划.md`](plans/2026-11-19-LG4联调测试计划.md) · [`../records/2026-11-19-总结器与结束语义联调.md`](../records/2026-11-19-总结器与结束语义联调.md)

---

## 0. LG-4 到底是什么（先建立正确预期）

LG-4 **不是**再做一个 Agent 节点，而是练这套工程习惯：

```text
功能做完 → 分层测试计划 → 可复跑脚本 → 跑起来 → 写人读结论 + 机器摘要
```

大厂对应物：smoke gate、golden scenarios、launch notes、eval 样例归档。  
学生收益：以后每做 CE-2 / 结束策略改动，都能自己「证明它还好」。

---

## 1. 能力拆分（LG-4 = 6 个小技能）

| 编号 | 技能 | 你要能回答 / 做到 | 本仓库落点 | 状态 |
|------|------|-------------------|------------|------|
| **LG-4.1** | 分层测试思维 | 分清单测 / 语义场景 / 环境探针 / 真 E2E | 计划 L0–L3 | ✅ 已写进计划 |
| **LG-4.2** | 写验收标准 | 每步有「期望字段」（如 `status=completed`） | 计划步骤表 | ✅ |
| **LG-4.3** | 假模型语义场景 | 不用真 LLM 也能测终态 + summarize | `run_verification` L2；phase1 | ✅ |
| **LG-4.4** | 一键验证脚本 | 环境探测 + pytest + 场景 + 写 JSON | `scripts/run_verification.py` | ✅ |
| **LG-4.5** | 写 records | 环境、命令、结果表、结论、后续 | `records/2026-11-19-…` | ✅ |
| **LG-4.6** | 真依赖联调 | 隧道 + 真模型 `POST /agent/run`，失败可解释 | 上次 **SKIP**（无 `:18000`） | ⏳ 建议补练 |

把 **4.1→4.6** 当作学习顺序；前五项已跟做完一遍，第六项是「升级作业」。

---

## 2. 推荐学习与实现顺序（学生路径）

按天估时（可拆开做，不必一天内赶完）。

### 第 1 步 — 读懂「为什么要分层」（约 0.5h）· LG-4.1

**学：**

- 假模型测的是 **图与状态机**；真模型测的是 **提示词 + 模型听话程度**。  
- 环境挂了应标 SKIP，不要当成产品 bug。

**做：**

- 打开联调记录里的 L0–L3 表，用自己的话各写一句「这一层证明什么」。

**自检：** 能说出「为什么没有 Qwen 隧道时 LG-4 仍可判定通过」。

---

### 第 2 步 — 跟读验收标准（约 0.5h）· LG-4.2

**学：** 好的验收写「输入 + 期望 status/answer 要点」，坏的验收只写「测一下」。

**做：**

- 对照 `ending.py` 三种终态，各写一条「若我改坏了，哪条断言会红」。

**自检：** 不看代码也能列出 completed / abandoned / budget_exceeded 的触发点。

---

### 第 3 步 — 手跑离线单测（约 0.5–1h）· LG-4.3 前半

**做：**

```powershell
cd C:\Users\hhcm\Desktop\123\开发\yu-manus-langgraph
.\.venv\Scripts\python.exe -m pytest -q tests/test_ending.py tests/test_phase1_manus_graph.py
```

**学：** 读 `ScriptedChatModel`：预设 `AIMessage` + `tool_calls` 如何驱动图。

**自检：** 能解释「abandon 用例为什么不需要真搜索工具」。

---

### 第 4 步 — 读懂并改一处验证脚本（约 1–2h）· LG-4.3 / 4.4

**做：**

1. 通读 `scripts/run_verification.py`（probe → pytest → semantic → api_smoke）。  
2. **小作业：** 在 L2 再加一个场景，例如「无工具纯文本 → `completed`」。  
3. 再跑：`python scripts/run_verification.py`，看 JSON 里多出一条 case。

**自检：** 知道 JSON 里 `overall_pass_for_lg4` 由哪些字段决定。

---

### 第 5 步 — 独立写一篇 records（约 1h）· LG-4.5

**做：** 用同一模板，把你「加纯文本 completed 场景」的一次运行写成短记录（可附在原记录「附录」或新开 `records/YYYY-MM-DD-…补充.md`）。

**模板字段（必须有）：** 环境表 · 命令 · 结果表 · 通过/失败 · 结论与下一步。

**自检：** 三个月后只看这篇，能复现你那天做了什么。

---

### 第 6 步 — 真模型补测（约 1–2h，依赖环境）· LG-4.6

**前置：**

1. 实验室 Qwen/vLLM 已起（或按实验室 SSH 规则检查）。  
2. 本机 SSH 隧道：`18000→8000`（及需要的 MCP）。  
3. `curl http://127.0.0.1:18000/v1/models` 有响应。  
4. 如改过代码，重启 `:8200`。

**做：**

```powershell
.\.venv\Scripts\python.exe scripts\run_verification.py
# 或
curl.exe --noproxy "*" -sS -X POST http://127.0.0.1:8200/agent/run -H "Content-Type: application/json" -d "{\"message\":\"现在几点？\",\"max_steps\":6}"
```

**验收：**

- 返回有自然语言 `answer`  
- `status` 多为 `completed`  
- `step_logs` 与 `answer` 分离  

**自检：** 在 records 里补一节「Live 补测」，写清隧道与样例 JSON 摘要。

---

### 第 7 步 — 把习惯迁到下一功能（转 CE-2）

做 CE-2 前先复制 LG-4 习惯：

1. 先写 1 页计划（步骤 / 目标 / 如何测）  
2. 假模型或本地工具单测  
3. 跑通再写 records 三五行  

**不要**等功能全做完才第一次想测试。

---

## 3. 与「已完成 LG-4」的关系

| 项 | 说明 |
|----|------|
| 工程勾选 LG-4 | ✅ 最小闭环已有：计划、脚本、22 pytest、三终态、records |
| 学生路径 4.1–4.5 | ✅ 你已走过主路径（或可按上面复习） |
| 学生路径 4.6 | ⏳ **可选加强**：真模型 live；待办记为 `LG-4b` |
| 脚本小扩展 | ⏳ **可选练习**：加「纯文本 completed」场景 → `LG-4c` |

主线下一题仍是 **CE-2**；4.6/4.6 练习可穿插，不挡上下文工程。

---

## 4. 建议时间表（示例一周内）

| 顺序 | 内容 | 产出 |
|------|------|------|
| Day A | 4.1 + 4.2 阅读与自检 | 笔记几句即可 |
| Day B | 4.3 手跑 pytest + 读 ScriptedChatModel | 能口述假模型原理 |
| Day C | 4.4 给 verification 加一个 case | 脚本改动 + 新 JSON |
| Day D | 4.5 补一段 records | 文档 |
| 有隧道时 | 4.6 live | records 追加 Live 节 |
| 之后 | **CE-2 计划 → 实现** | 新计划文件 |

---

## 5. 常见误区

1. 把 LG-4 理解成「再写一个 Summarizer」——不是。  
2. 没有隧道却强行判产品失败——应 SKIP 并写原因。  
3. 只跑真模型、不写假模型场景——慢、贵、不稳定，不适合日常回归。  
4. records 只贴一大段日志、没有结论表——三个月后无法用。

---

## 6. 下一步（学完 LG-4 习惯之后）

1. （可选）完成 `LG-4b` live 补测。  
2. 打开 [`学习路线-Cursor类Agent.md`](学习路线-Cursor类Agent.md) 的 CE-2。  
3. 先出 CE-2 开发计划（等确认再编码）——继续用 LG-4 同一套「计划→测→记录」。
