# CE-6 / IDX-WS corpus（语料）

本目录放**待检索的文本语料**与自建教学小工程（保持体量可控，避免拖垮 embedding）。

## 内容

| 路径 | 说明 |
|------|------|
| `job_*.md` / `agent_tools_guide.md` 等 | CE-6 求职/工具短文语料 |
| **`sample_forge/`** | 仿 GitHub 小项目（自建），含噪声目录与超大文件 |

## 成熟 GitHub 演示仓（中文 README）

为避免把大型上游仓塞进 CE-6 corpus（每次 corpus 建索引都会 embed），浅克隆放在：

**`artifacts/workspace_demos/github_jieba/`** — [fxsjy/jieba](https://github.com/fxsjy/jieba)（结巴中文分词，README 中文）

```powershell
git clone --depth 1 --single-branch https://github.com/fxsjy/jieba.git artifacts/workspace_demos/github_jieba
```

IDX-WS 测试时设：`WORKSPACE_ROOT=artifacts/workspace_demos/github_jieba`，`SEARCH_MODE=workspace`。

## 约定

- CE-6 工具回归：`SEARCH_MODE=corpus`  
- 改语料后：`semantic_search(..., rebuild=true)` 或清缓存  
- `sample_forge` 重建：`python scripts/_gen_sample_forge.py`
