# 计划：CA-2 run_shell（受控终端）

> 状态：✅ **已完成**（2026-11-24）  
> 术语：run_shell（跑命令）、subprocess（子进程）、cwd（工作目录）、timeout（超时）、exit code（退出码）

---

## 1. 背景与目标

**要解决：** Agent 已能读/写工作区，但还不能**跑命令验证**（如 `pytest`）。CA-2 增加受控 `run_shell`，把 stdout/stderr/exit_code 回喂模型。

**非目标：** HITL 审批（CA-6）；完整命令黑名单；交互式 TTY；远程 SSH；改图结构（那是 CA-3）。

---

## 2. 现状

| 已有 | 说明 |
|------|------|
| 工具装载 | `load_agent_tools`：读/写/检索/`terminate` |
| 沙箱 | `resolve_safe` 管路径 |
| 图 | `START → reason ⇄ tools → summarize`（`app/graph/build.py`） |
| shell 工具 | **尚无** |

---

## 3. 步骤表

| 步 | 做什么 | 工作目标（详细） | 如何测试 |
|----|--------|------------------|----------|
| **S0** | 拍板接口 | 工具名 `run_shell(command, working_directory=".")`；成功返回含 `exit_code`/`timed_out`/stdout/stderr；失败 `error:`；默认 timeout/输出上限进 Settings | 本表即拍板 |
| **S1** | 纯函数 | `run_shell_safe`：`cwd` 经沙箱；`subprocess` 捕获输出；超时返回 `timed_out=true` 与已捕获输出；空命令拒绝 | `pytest`：echo 成功；坏 cwd；超时；空命令 |
| **S2** | 挂工具 | `@tool run_shell` → loader；长输出走 CE-3 落盘包装 | loader 含名；invoke 通过 |
| **S3** | 提示词 | `NEXT_STEP_PROMPT`：何时跑命令（验测/看版本）；禁止瞎造破坏性命令的**软约束**（文案级）；先写文件再测时的顺序 | `test_ca2_prompt` 关键字 |
| **S4** | Demo | 脚本对仓库跑一条无害命令（如 `python -c "print(1)"`）并打印结果 | 脚本退出 0 |
| **S5** | 归档 | 待办指针可留在 CA-2 完成或 → CA-3；records | 文档链 |

### S0 已拍板

| 项 | 决定 |
|----|------|
| 工具 | `run_shell(command: str, working_directory: str = ".")` |
| cwd | 相对 `WORKSPACE_ROOT`，经 `resolve_safe`；须为已存在目录 |
| 超时 | `SHELL_TIMEOUT_SEC` 默认 **60** |
| 输出上限 | `SHELL_MAX_OUTPUT_CHARS` 默认 **80000**（超则截断并注明） |
| shell | Windows/Unix 均 `shell=True`（便于 `python -m ...`）；MVP 不做 argv 数组 |
| 黑名单 | **本阶段不做**硬拦截；prompt 提醒避免 `rm -rf` / 格式化等 |
| 返回 | 多行文本：`ok`/`error:` 首行 + exit/timed_out + stdout/stderr 段 |

---

## 4. 涉及文件

- `app/tools/shell_tools.py`（新）
- `app/tools/loader.py`、`app/prompts.py`、`app/config.py`、`.env.example`
- `tests/test_shell_tools.py`、`tests/test_ca2_prompt.py`
- `scripts/demo_ca2_run_shell.py`
- 待办 / records / 启动清单

---

## 5. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 模型跑危险命令 | MVP 靠 prompt；硬闸留给 CA-6 |
| 挂死进程 | timeout |
| 输出撑爆上下文 | 截断 + CE-3 落盘 |

回滚：loader 去掉 `run_shell` 即可。

---

## 6. 验收清单

- [x] 工作区内可执行命令并拿到 exit_code  
- [ ] 越界 cwd / 空命令 → `error:`  
- [x] 超时有明确标记  
- [x] 工具已挂载；prompt 有路由  
- [x] Demo + 单测通过；文档归档  

---

## 7. 确认

用户已要求「执行 CA-2」→ 按本计划编码。
