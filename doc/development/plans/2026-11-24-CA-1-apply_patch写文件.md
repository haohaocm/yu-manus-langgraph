# 计划：CA-1 apply_patch / 写文件

> 状态：✅ **S0～S5 全部完成**（2026-11-24）  
> 术语：apply_patch（应用补丁）、workspace（工作区）、sandbox（沙箱）、diff（差异）、rollback（回滚）

---

## 1. 背景与目标

**要解决：** Agent 已能检索/阅读工作区，但还不能**安全改文件**。CA-1 补上「在 `WORKSPACE_ROOT` 沙箱内创建/覆盖/按补丁修改文本文件」，形成 Cursor 类 Agent 的编辑闭环最小版。

**非目标（本阶段不做）：**

- HITL / 改前审批（→ **CA-6**）
- `run_shell`（→ **CA-2**）
- 完整 undo 栈 / git commit（可只做「写前备份一份 `.bak` 或侧车」）
- 二进制文件编辑、大文件整文件无上限写入
- 自动重建索引（可提示用户 `rebuild`；不强制钩 IDX）

---

## 2. 现状

| 已有 | 路径 / 行为 |
|------|-------------|
| 读工具 | `list_dir` / `read_file` / `grep`（`app/tools/fs_tools.py`） |
| 沙箱 | `resolve_safe`（`app/tools/path_sandbox.py`）拒逃逸 |
| 工具装载 | `load_agent_tools` 仅挂读侧 + `semantic_search`（`app/tools/loader.py`） |
| 路由提示 | `NEXT_STEP_PROMPT` 无写文件指引（`app/prompts.py`） |
| 写工具 | **尚无** `write_file` / `apply_patch` |

---

## 3. 步骤表

| 步 | 做什么 | 工作目标 | 如何测试 |
|----|--------|----------|----------|
| **S0** | 对齐接口形状 | ✅ 已按推荐拍板（见下表） | 用户确认 |
| **S1** | 纯函数写盘库 | ✅ `app/tools/fs_write.py`；config `max_write_bytes` / `write_backup` | `tests/test_fs_write.py` |
| **S2** | 挂成 Agent 工具 | ✅ `write_file` / `str_replace` → `loader` | `test_fs_write` + `test_fs_tools` |
| **S3** | 提示词路由 | ✅ `NEXT_STEP_PROMPT` 增 write/replace 路由 | `tests/test_ca1_prompt.py` |
| **S4** | Demo + 工具调用验收 | 见下方「S4 工作目标」；fixture + `scripts/demo_ca1_s4_write.py` + `tests/test_ca1_s4_demo.py` | demo 脚本打印 `S4 DEMO OK`；pytest 绿 |
| **S5** | 文档归档 | ✅ 待办/归档/records/启动清单 | 离线 17 passed；指针→CA-2 |

### S0 已拍板（按推荐）

| 项 | 决定 |
|----|------|
| 工具（MVP） | **`write_file(path, content)`** + **`str_replace(path, old, new, replace_all=false)`** |
| unified `apply_patch` | **本阶段不做**（需要时再加） |
| 备份 | 覆盖前写同目录 `*.ca1.bak`；Settings 可关，**默认开** |
| 上限 | `max_write_bytes`（建议 512KiB） |
| 返回 | 成功：`ok path=... bytes=... backup=...`；失败：`error: ...` |
| 编码 | UTF-8 文本；内容含 `\x00` → 拒绝 |

---

## 4. 涉及文件（预计）

| 路径 | 变更 |
|------|------|
| `app/tools/fs_write.py`（新）或扩 `fs_tools.py` | 写盘实现 |
| `app/tools/loader.py` | 注册工具 |
| `app/prompts.py` | 写文件路由 |
| `app/config.py` / `.env.example` | 可选 `write_backup` / `max_write_bytes` |
| `tests/test_fs_write*.py`（新） | 单测 |
| `doc/development/待办清单.md` / `已完成归档.md` / `records/` | S5 |
| `doc/development/项目启动清单.md` | 若有新配置项 |

---

## 5. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 模型误改重要文件 | 沙箱 + 备份；HITL 留给 CA-6 |
| patch 格式模型写错 | MVP 优先 `str_replace` / 整文件写，降低解析失败率 |
| 与检索索引不同步 | 文档说明改完需 `rebuild`；不自动重嵌 |
| 默认行为变化 | 新工具只增不改旧读工具语义 |

回滚：去掉 loader 注册与 prompt 段即可禁用写能力；bak 可手动恢复。

---

## 6. 验收清单

- [x] 工作区内可创建/覆盖文本文件；区外路径失败  
- [x] 覆盖前有可关备份（默认开）  
- [x] 超大/二进制拒绝并 `error:`  
- [x] Agent 工具列表含写工具；prompt 有路由  
- [x] 单测覆盖主路径；S4 工具调用改文件成功  
- [ ] 待办 CA-1 `[x]` + records；指针建议 → **CA-2**

---

### S4 工作目标（详细）

做完后你应能亲眼看到：**Agent 同款工具**真的改到了磁盘上的文件，而不是只跑通纯函数单测。

- **能力**：对 rtifacts/ca1_write_demo/hello.txt 依次调用 write_file → str_replace → 
ead_file → 故意 ../ 越界写并看到 error:。
- **概念**：测的是已注册的 @tool（invoke），与 S1 纯函数同一套落盘逻辑。
- **产物**：改后的 hello.txt、可选 hello.txt.ca1.bak；脚本打印 S4 DEMO OK。
- **非目标**：不启完整 Agent 对话、不上 HITL、不 rebuild 索引。
- **命令**：python scripts/demo_ca1_s4_write.py；pytest tests/test_ca1_s4_demo.py -q

## 7. 下一步

S0～S5 ✅。下一主线 **CA-2**（run_shell）；先写计划再编码。
