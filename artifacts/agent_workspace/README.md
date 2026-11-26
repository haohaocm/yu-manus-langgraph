# Agent 默认可写工作区

本目录是 `WORKSPACE_ROOT` 的默认值（`artifacts/agent_workspace`）。

- Agent 的 `write_file` / `str_replace` / `run_shell` cwd 默认落在这里，**不会**写到仓库源码根。  
- 建议交付物放在 `outputs/` 下。  
- 要让 Agent 改某个真实工程：在 `.env` 设 `WORKSPACE_ROOT=该工程路径`（或绝对路径）。
