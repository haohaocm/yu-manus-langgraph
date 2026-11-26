# EMB-1 S2：stub vs bge 对照（2026-11-23）

- 语料：`artifacts/corpus/`，11 chunks；hybrid α=0.5  
- stub dim=64；bge-m3 dim=1024（经 `127.0.0.1:18001`）

| query | stub top1 | bge top1 | 观察 |
|-------|-----------|----------|------|
| 简历量化/可验证 | job_resume_tips emb≈0.57 | 同文件 emb≈0.82 | 字面强时 top1 可相同；**bge 的 emb 分更贴语义** |
| Offer 谈薪/签字费 | job_offer_negotiation | 同 | 同上 |
| path escape（英） | agent_tools_guide | 同 | bge emb 0.35→0.66 |
| spaghetti… | kitchen_decoy | 同 | 干扰项两边都能靠 BM25 钉住 |

结论：本 Demo 语料小、query 词重叠大时 top1 常一致；差异主要在 **embedding_raw** 与次优排序。真语义价值在改写/同义 query 与更大语料上更明显。
