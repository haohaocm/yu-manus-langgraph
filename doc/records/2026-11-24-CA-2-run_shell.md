# 2026-11-24 CA-2 run_shell（受控终端）

## 范围

Agent 可在 `WORKSPACE_ROOT` 内执行 shell 命令，捕获 stdout/stderr/exit_code，支持超时。

## 关键路径

| 模块 | 路径 |
|------|------|
| 实现 | `app/tools/shell_tools.py`（`run_shell_safe` / `@tool run_shell`） |
| 装载 | `app/tools/loader.py` |
| 提示词 | `app/prompts.py`（何时用 `run_shell`） |
| 配置 | `SHELL_TIMEOUT_SEC`、`SHELL_MAX_OUTPUT_CHARS` |
| 计划 | `doc/development/plans/2026-11-24-CA-2-run_shell.md` |
| Demo | `scripts/demo_ca2_run_shell.py` |

## 回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_shell_tools.py tests/test_ca2_prompt.py -q
.\.venv\Scripts\python.exe scripts\demo_ca2_run_shell.py
```

**结果：** 相关单测通过；Demo 打印 `CA-2 DEMO OK`。

## 非目标（仍有效）

命令黑名单硬拦截、HITL（CA-6）、交互式 TTY。

## 下一主线

**CA-3** Plan 节点 — 方案见 `doc/development/plans/2026-11-24-CA-3-Plan节点执行方案.md`（待确认后编码）。
