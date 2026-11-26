"""IDX-WS S4 / CE-6：semantic_search 工具——hybrid 检索入口，供 Agent 调用。

说明（学习用）：
- 工具入参是「自然语言 query」，不是「文件夹路径」。
- 索引范围由配置决定：WORKSPACE_ROOT + SEARCH_MODE（workspace|corpus）。
- 平时查内存/已建索引；只有 rebuild=true 才重新扫描并向量化。
"""

from __future__ import annotations

from langchain_core.tools import tool

from app.config import Settings, get_settings
from app.search.embed import get_embedder
from app.search.hybrid import HybridIndex, build_hybrid_index, search_hybrid
from app.search.scope import normalize_search_mode

# 进程内懒缓存：避免每轮工具调用都重切块 / 重 embed
_cached: HybridIndex | None = None
_cached_key: tuple | None = None


def _cache_key(settings: Settings) -> tuple:
    """缓存键：任一影响「扫什么 / 怎么切 / 怎么嵌」的配置变了就失效。"""
    return (
        settings.workspace_root,
        normalize_search_mode(settings),
        settings.search_corpus_dir,
        settings.search_ignore_dirs,
        settings.search_globs,
        settings.search_max_file_bytes,
        settings.search_max_chunks,
        settings.search_chunk_lines,
        settings.search_chunk_overlap,
        settings.embedding_backend,
        settings.embedding_base_url,
        settings.embedding_model,
        settings.hybrid_alpha,
    )


def clear_search_index_cache() -> None:
    """测试或源码变更后清空进程内索引缓存。"""
    global _cached, _cached_key
    _cached = None
    _cached_key = None


def get_or_build_hybrid_index(
    *,
    settings: Settings | None = None,
    rebuild: bool = False,
) -> HybridIndex:
    """懒建 hybrid 索引；``rebuild=True`` 强制按当前配置重扫并重建。"""
    global _cached, _cached_key
    s = settings or get_settings()
    key = _cache_key(s)
    if rebuild or _cached is None or _cached_key != key:
        emb = get_embedder(s)
        _cached = build_hybrid_index(settings=s, embedder=emb)
        _cached_key = key
    return _cached


def semantic_search_text(
    query: str,
    top_k: int = 5,
    *,
    rebuild: bool = False,
    settings: Settings | None = None,
) -> str:
    """对当前配置的索引范围做 hybrid 检索，返回可读文本（score / path / 摘录）。

    空 query 或异常时返回友好说明，不抛 traceback 给模型。
    """
    s = settings or get_settings()
    q = (query or "").strip()
    if not q:
        return "semantic_search: error: empty query"
    if top_k < 1:
        return "semantic_search: error: top_k must be >= 1"

    mode = normalize_search_mode(s)
    try:
        index = get_or_build_hybrid_index(settings=s, rebuild=rebuild)
        emb = get_embedder(s)
        hits = search_hybrid(
            index,
            q,
            embedder=emb,
            settings=s,
            top_k=int(top_k),
        )
    except Exception as exc:  # noqa: BLE001 — 工具回喂模型，避免未捕获栈
        return f"semantic_search: error: {exc}"

    if not hits:
        return (
            f"semantic_search hits=0 query={q!r} mode={mode}\n"
            "no hits\n"
            "hint: try different keywords or rebuild=true"
        )

    lines = [
        f"semantic_search hits={len(hits)} query={q!r} mode={mode} "
        f"alpha={hits[0].alpha} chunks={index.size()}",
    ]
    for i, h in enumerate(hits, 1):
        lines.append(
            f"{i}. score={h.score:.4f} bm25={h.bm25_raw:.4f} emb={h.embedding_raw:.4f} "
            f"path={h.path}:{h.start_line}-{h.end_line}"
        )
        preview = h.excerpt.replace("\n", " ").strip()
        if len(preview) > 160:
            preview = preview[:157] + "..."
        lines.append(f"   preview: {preview}")
    lines.append("hint: use read_file on path for full content")
    return "\n".join(lines)


@tool
def semantic_search(query: str, top_k: int = 5, rebuild: bool = False) -> str:
    """Hybrid semantic search over the configured workspace index (not a path argument).

    Index scope comes from WORKSPACE_ROOT + SEARCH_MODE:
    - workspace: whole project tree (minus ignore dirs / size limits)
    - corpus: only SEARCH_CORPUS_DIR (legacy CE-6 demo)

    Use for meaning / topical questions. For exact symbols prefer grep.
    After hits, use read_file on the path. Set rebuild=true only when source files
    changed and the in-memory index may be stale.
    """
    return semantic_search_text(query, top_k=top_k, rebuild=rebuild)
