# 计划：EMB-1 真 embedding（bge）学习与接入

> 状态：🟢 S0～S6 已落地（2026-11-23）：**仅 bge，禁止 stub**；测 EMB 前必须开 `18001→8001`  
> 目标：系统学会 embedding，并把实验室 **bge** 接到检索链  
> 术语：embedding（向量嵌入）、cosine similarity（余弦相似度）、hybrid（混合检索）

---

## 1. 背景与目标

- 用真 embedding（bge-m3）替代教学用哈希 stub。  
- **政策（用户确认）：** 永不静默回退 stub；测 EMB 前必须开隧道；连不上就报错/测试失败。

### 非目标

- 向量数据库集群、IDX-WS 全仓、CA-1  

---

## 2. 现状（落地后）

| 模块 | 行为 |
|------|------|
| `app/search/embed.py` | 仅 `HttpOpenAIEmbedder`；`stub` → `EmbeddingError` |
| 默认配置 | `embedding_backend=http`，`:18001`，`bge-m3` |
| 单测 | `require_bge_embedder()` 探测隧道；失败则 fail |
| 试玩 | `/embed-compare` 仅 bge |

---

## 3. 步骤完成情况

| 步 | 状态 |
|----|------|
| S0 学习 | 对话已覆盖 |
| S1 探针 | ✅ |
| S2 stub vs bge 对照 | ✅（历史 records；现已弃用 stub） |
| S3 HTTP 加固 | ✅ |
| S4 测试策略 | ✅ 强制 bge + 禁 stub |
| S5 文档 | ✅ `.env.example` + records |
| S6 默认 http | ✅ |

---

## 4. 验收

- [x] 默认 http/bge  
- [x] `EMBEDDING_BACKEND=stub` 报错  
- [x] EMB 相关 pytest 依赖隧道  
- [x] records / `.env.example` 写明约定  

**测前：** 打开 Xshell 隧道 `18001→8001`，并确认实验室 bge 在跑。
