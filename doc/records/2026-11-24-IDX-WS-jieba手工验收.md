# IDX-WS 手工验收：github_jieba 全仓索引（逐步中间结果）

> 日期：2026-11-24  
> 目标工程：`artifacts/workspace_demos/github_jieba`（[fxsjy/jieba](https://github.com/fxsjy/jieba)，README 中文）  
> 可复跑脚本：`scripts/demo_idx_ws_jieba.py`

---

## 0. 前置

| 项 | 本次状态 |
|----|----------|
| jieba 目录存在 | ✅ |
| 实验室 bge `:8001` | ✅（此前 SSH 已确认在跑） |
| 本机隧道 `18001` | ❌ **未开** → 步骤 4/5 的 **真 embedding** 用假向量演示接线；开隧道后加 `--real-bge` |

开隧道后复跑真 bge：

```powershell
cd "C:\Users\hhcm\Desktop\123\开发\yu-manus-langgraph"
.\.venv\Scripts\python.exe scripts\demo_idx_ws_jieba.py --real-bge
```

仅离线（与下文一致）：

```powershell
.\.venv\Scripts\python.exe scripts\demo_idx_ws_jieba.py
```

---

## 步骤 0：配置（中间结果）

| 配置 | 值 |
|------|-----|
| `WORKSPACE_ROOT` | `.../artifacts/workspace_demos/github_jieba` |
| `SEARCH_MODE` | `workspace` |
| ignore（节选） | `.git`, `.venv`, `node_modules`, `__pycache__`, … |
| globs（节选） | `*.py`, `*.md`, `*.txt`, `*.json`, … |
| `max_file_bytes` | `512000` |
| `max_chunks` | `8000` |
| 落盘目录 | `artifacts/search_index/jieba_demo/` |

---

## 步骤 1：扫描文件（中间结果）

**`files_kept = 63`**

前若干保留文件（字节 + 相对路径）：

```text
  252619  jieba/posseg/prob_trans.py
   32667  README.md
   20428  jieba/__init__.py
    9962  jieba/posseg/__init__.py
    9290  test/jieba_test.py
    ...
```

**因过大被跳过（不切块、不算向量）`skipped_oversize = 5`：**

```text
  SKIP  6471088  jieba/analyse/idf.txt
  SKIP  5420898  jieba/dict.txt
  SKIP  4076462  jieba/posseg/prob_emit.py
  SKIP  1679102  jieba/posseg/char_state_tab.py
  SKIP  1356958  jieba/finalseg/prob_emit.py
```

解读：词典/发射概率表远超 512KB，上限生效；否则 chunk/embedding 会爆炸。

---

## 步骤 2：切块（中间结果）

**总 `chunks = 378`**

按 path 块数 Top：

```text
  177  jieba/posseg/prob_trans.py
   26  README.md
   21  jieba/__init__.py
   10  jieba/posseg/__init__.py
    9  jieba/posseg/prob_start.py
    ...
```

### 样例块全文（`README.md:1-40`）

```text
jieba
========
“结巴”中文分词：做最好的 Python 中文分词组件
...
特点
========
* 支持四种分词模式：
    * 精确模式，试图将句子最精确地切开，适合文本分析；
    * 全模式，...
    * 搜索引擎模式，...
    * paddle模式，...
```

（README 共切成 **26** 块；第 2 块从约第 31 行起讲算法/DAG/HMM。）

---

## 步骤 3：BM25 检索（真实词法分，无需 bge）

### Query A：`中文分词 精确模式 搜索引擎模式`

| # | score | path |
|---|-------|------|
| 1 | 51.1378 | `setup.py:1-40` |
| 2 | 45.5171 | `README.md:1-40` |
| 3 | 45.1071 | `README.md:61-100` |
| 4 | 38.0236 | `README.md:31-70` |
| 5 | 31.5212 | `test/demo.py:1-40` |

### Query B：`自定义词典 新词`

| # | score | path |
|---|-------|------|
| 1 | 27.6091 | `README.md:61-100` |
| 2 | 26.2930 | `README.md:91-130` |
| 3 | 22.9511 | `README.md:151-190` |
| 4 | 22.6702 | `README.md:121-160` |
| 5 | 19.8226 | `README.md:271-310` |

解读：中文说明集中在 README，BM25 能稳定命中；`setup.py` 因 LONGDOC 含相同文案也会靠前。

---

## 步骤 4：Hybrid 落盘（本次 = 假 embedding 演示接线）

因本机 `18001` 未开，embedding 使用 `fake:demo`（**分数不可当作真语义**）。

```text
saved = .../artifacts/search_index/jieba_demo
chunks = 378
manifest:
  backend: hybrid
  search_mode: workspace
  chunk_count: 378
  max_file_bytes: 512000
  max_chunks: 8000
  embedder: fake:demo
产物: chunks.json, vectors.json, manifest.json
```

开隧道后应看到 `embedder` 类似 `http:bge-m3`，且 `dim` 多为 1024。

---

## 步骤 5：Hybrid 查询（假向量；结构与真 bge 相同）

Query：`中文分词精确模式`

| # | score | bm25 | emb(假) | path |
|---|-------|------|---------|------|
| 1 | 0.9769 | 35.89 | 0.88 | `setup.py:1-40` |
| 2 | 0.9359 | 32.77 | 0.88 | `README.md:61-100` |
| 3 | 0.9322 | 33.00 | 0.87 | `README.md:1-40` |
| 4 | 0.8686 | 27.39 | 0.90 | `README.md:211-250` |
| 5 | 0.8472 | 26.28 | 0.89 | `README.md:31-70` |

---

## 你接下来怎么测「真 bge」

1. Xshell / SSH 打开：`18001 → 实验室 8001`（建议同时 `18000→8000`）。  
2. 探针：`Invoke-WebRequest http://127.0.0.1:18001/v1/models`  
3. 执行：`python scripts/demo_idx_ws_jieba.py --real-bge`  
4. 对比步骤 5 的 `emb=`：真 bge 应对同义改写更稳；BM25 仍偏字面重叠。

Agent 侧：`.env` 设 `WORKSPACE_ROOT=artifacts/workspace_demos/github_jieba`，`SEARCH_MODE=workspace`，再 `semantic_search("…")`（改文件后用 `rebuild=true` 或 `python -m app.search.reindex`）。

---

## 结论

| 能力 | jieba 上验证 |
|------|----------------|
| ignore + 大小上限 | ✅ 5 个超大词典/表被跳过 |
| 全仓切块 | ✅ 63 文件 → 378 chunks |
| BM25 中文检索 | ✅ README/说明命中合理 |
| Hybrid 落盘接线 | ✅（真语义需开 `18001`） |
