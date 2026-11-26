# records（运行与测试记录）

存放「做过什么、结果如何」类文档，便于回归与复盘。

建议命名：`YYYY-MM-DD-主题.md`，例如：

- `2026-11-17-E2E联调-Qwen与MCP.md`
- `2026-11-19-总结器与结束语义联调.md`（LG-4；脚本 `scripts/run_verification.py`）
- `2026-11-19-CE2本地读仓库工具.md`（list_dir/read_file/grep + 假模型串联）
- `2026-11-19-CE3长工具输出落盘.md`（阈值 1000；path 回喂）
- `2026-11-21-CE4-MCP动态名录.md`（三元工具按需 schema）
- `2026-11-23-CE6小仓库检索Demo.md`（切块/BM25/embedding/hybrid/`semantic_search`）
- `2026-11-23-EMB1-S4S5S6-仅bge.md`（禁 stub；测前 `18001`）
- `2026-11-24-IDX-WS-全仓索引.md`（workspace 扫描 / ignore / hybrid / reindex）
- `2026-11-24-IDX-WS-jieba手工验收.md`（对 github_jieba 逐步中间结果；脚本 `scripts/demo_idx_ws_jieba.py`）
- `artifacts/verification-latest.json`（最近一次验证机器摘要）
- `2026-11-18-环境启停记录.md`

启服务步骤见 [`../development/项目启动清单.md`](../development/项目启动清单.md)（**Qwen + bge**）。

可记录：命令、端口、通过/失败断言、日志摘要、结论与后续动作。
