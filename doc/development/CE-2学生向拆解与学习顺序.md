# CE-2 学生向拆解：本地读仓库三件套

> 目标：给 Manus 加上 **`list_dir` / `read_file` / `grep`**，让 Agent 能按需发现文件，而不是猜代码。  
> 这是上下文工程 P0 的第 1 步（见 [`../knowledge/Cursor与DeepSeek-Harness上下文工程.md`](../knowledge/Cursor与DeepSeek-Harness上下文工程.md)）。  
> **本文件是学习/拆解；正式编码前仍须单独出开发计划并等确认。**

---

## 0. CE-2 要解决什么

| 没有 CE-2 | 有了 CE-2 |
|-----------|-----------|
| 模型只能靠 MCP 通用工具或瞎猜路径 | 能列出目录、读文件片段、按关键词搜 |
| 上下文工程无从谈起 | 为 CE-3（长输出落盘）、CE-6（小仓库检索）打底 |

**非目标（本阶段不做）：** 写文件/`apply_patch`（CA-1）、语义向量检索（CE-6）、MCP 上挂载同名工具（可后做）。

---

## 1. 能力拆分（建议实现顺序 = 学习顺序）

| 编号 | 做什么 | 学到什么 | 完成标准（测试） |
|------|--------|----------|------------------|
| **CE-2.1** | ✅ 定「工作根目录」与安全边界 | `path_sandbox.py` + `WORKSPACE_ROOT` | `tests/test_path_sandbox.py` |
| **CE-2.2** | ✅ 实现 `list_dir` | `fs_tools.list_dir`；条数上限 | `tests/test_fs_tools.py` |
| **CE-2.3** | ✅ 实现 `read_file` | 行切片 offset/limit；拒二进制 | 同上 |
| **CE-2.4** | ✅ 实现 `grep` | 纯 Python 正则；非系统 grep；Win/Linux 通用 | `test_fs_tools` |
| **CE-2.5** | ✅ 挂到 `load_agent_tools` | `list_dir`/`read_file`/`grep` 始终本地挂载 | loader 名称集合单测 |
| **CE-2.6** | ✅ 提示词轻改 | `NEXT_STEP_PROMPT` 含先搜再读 | 文案断言 + 图测 |
| **CE-2.7** | ✅ 单测 + 短 records | `test_ce2_fs_graph`；records | **20 passed**；CE-2 收尾 |

推荐：**严格按 2.1 → 2.7**，不要先做 grep 再回头补沙箱。

---

## 1.1 关于 CE-2.1 的设计共识（答疑）

### 2.1 到底在做什么？

**对一半：** 主要是 **路径安全检测 + 给后续 FS 工具用的小工具函数（内部库）**，不是另起一套大框架。

| 做 | 不做（本步） |
|----|----------------|
| `workspace_root` 配置 | 完整「文件保存子系统」 |
| `resolve_safe(相对路径) → 绝对路径` | 把「路径检查」做成给模型调用的 Agent 工具 |
| 越界 / 逃逸拒绝 | 写文件、落盘缓存（那是 CE-3 / CA-1） |

`list_dir` / `read_file` / `grep` **内部调用** `resolve_safe`；模型看不到、也不需要单独调一个「检查路径」工具。

### 根目录设成和 `app` 同级 —— 对不对？

**对，且这是最常见默认：仓库根目录**（`yu-manus-langgraph/`，与 `app/` 同级）。

```text
yu-manus-langgraph/          ← workspace_root（默认）
  app/
  tests/
  doc/
  scripts/
```

**好处：**

- Agent 读的就是本项目，和「代码 Agent」场景一致  
- 移植：换机器只要根配置指到新 clone 路径  
- 单测可用临时目录覆盖 `workspace_root`，不污染仓库  

**更好的做法（推荐）：**

- **默认** = 项目根（与 `app` 同级）  
- **可配置**（`.env` / Settings）：`WORKSPACE_ROOT=.` 或绝对路径  
- **以后**若演示「读别人的小仓库」，再指到别的目录；不必现在建空文件夹  

「后续文件都放到根下」——对 **CE-2 读代码** 来说，根下已有的 `app/` `tests/` 就是要读的内容。  
**新产生的落盘文件**（长工具输出）建议以后用根下子目录如 `artifacts/` 或 `.manus_workdir/`（CE-3），不要和源码混放无约定——那是下一步，不是 2.1 必做。

### 用配置写相对目录再拼接 —— 对不对？

**正确，且比写死路径更好。**

建议落在现有 `app/config.py`（Settings / `.env`），例如：

- `workspace_root: str = "."`（相对**进程工作目录**或相对项目根解析一次成绝对路径）

移植时改 `.env` 一行即可。不必再单独搞一个难找的 ini，除非你想与 Settings 分离（一般不必要）。

### 越界拒绝是不是一个「工具」？

- **对 Agent：** 不是新工具，是 **内部函数**（如 `resolve_safe`）。  
- **对开发：** 可以交给实现者写好 + 单测；你说「交给你开发没问题」——等正式计划确认后编码即可。

### 根目录最后「保存」什么？

更准确说：**根目录是「沙箱视野」——Agent 被允许 list/read/grep 的那棵目录树。**

| 阶段 | 根下主要是什么 |
|------|----------------|
| **CE-2 现在** | 源码与文档（`app/`、`tests/`、`doc/`…）——**读**，不是存生成物 |
| **CE-3 以后** | 可另设子目录存「长工具输出」等生成物 |
| **CA-1 以后** | 才在根（或指定仓）里 **改/写** 业务文件 |

所以：2.1 的根 = **可读工作区**，不是「专门用来存结果的文件夹」。

---

## 2. 学生每日路径（约 3～5 个会话可做完）

### Day 1 — 边界与 `list_dir`（CE-2.1～2.2）

1. 读对照文里「Dynamic discovery / Instant Grep」两段。  
2. 设计：`workspace_root`（配置或默认项目根）、`resolve_safe(path)`。  
3. 实现并单测 `list_dir`。

### Day 2 — `read_file`（CE-2.3）

1. 参数：`path`，可选 `offset`/`limit`（行）。  
2. 拒绝二进制/超大文件或只返回前 N 字符 + 提示。  
3. 单测：正常读、越界、缺文件。

### Day 3 — `grep`（CE-2.4）

1. 最小版：目录下按 glob/`**/*.py` 搜正则，返回 `path:line:text`（条数上限）。  
2. 单测：构造临时目录含两文件，断言命中。

### Day 4 — 接入图 + 假模型场景（CE-2.5～2.7）

1. `loader` 始终加入三工具。  
2. ScriptedChatModel：`list_dir` → `read_file` → `terminate(success)`。  
3. 跑 pytest；需要时写极短 records。

---

## 3. 建议落点文件（实现时）

| 文件 | 职责 |
|------|------|
| `app/tools/fs_tools.py`（新建） | list_dir / read_file / grep + 安全解析 |
| `app/tools/loader.py` | 注册本地 FS 工具 |
| `app/config.py` | 可选 `workspace_root` |
| `app/prompts.py` | 一句引导先检索再读 |
| `tests/test_fs_tools.py`（新建） | 纯工具单测 |
| `tests/test_phase1_…` 或新图测 | 假模型串联 |

---

## 4. 与后续 CE 的衔接

```text
CE-2 能读仓库
  → CE-3 长结果落盘后再 read
  → CE-4 工具 schema 按需加载
  → CE-5 历史投影
  → CE-6 语义检索 Demo
```

CE-2 做砸（无路径沙箱）会把后面全部变成安全债，故 **2.1 不可跳**。

---

## 5. 你现在该做什么

1. 读本文 + 对照文相关小节。  
2. 让 Agent **出 CE-2 正式开发计划**（步骤/目标/如何测）。  
3. 你确认后 → 再编码。  
4. 日常只盯 [`待办清单.md`](待办清单.md) 里的 **#1 CE-2**。
