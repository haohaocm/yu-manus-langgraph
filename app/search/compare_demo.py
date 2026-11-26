"""检索试玩：按指定 workspace 建 hybrid（bge），供 /embed-compare 使用。"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings, get_settings
from app.search.embed import EmbeddingError, get_embedder
from app.search.hybrid import HybridIndex, build_hybrid_index, search_hybrid

# key -> (HybridIndex, embedder)
_cache: dict[str, tuple[HybridIndex, object]] = {}


def clear_compare_cache() -> None:
    """清空试玩页进程内索引缓存。"""
    _cache.clear()


def _pair_key(workspace: str, mode: str, settings: Settings) -> str:
    return "|".join(
        [
            str(Path(workspace).resolve()),
            mode,
            settings.search_ignore_dirs,
            settings.search_globs,
            str(settings.search_max_file_bytes),
            str(settings.search_max_chunks),
            str(settings.search_chunk_lines),
            str(settings.search_chunk_overlap),
            settings.embedding_model,
            str(settings.hybrid_alpha),
        ]
    )


def _get_or_build(
    *,
    workspace_root: str,
    search_mode: str = "workspace",
    rebuild: bool = False,
) -> tuple[HybridIndex, object, Settings]:
    base = get_settings()
    root = Path(workspace_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"workspace 不是目录: {root}")

    settings = Settings(
        workspace_root=str(root),
        search_mode=search_mode,
        search_ignore_dirs=base.search_ignore_dirs,
        search_globs=base.search_globs,
        search_max_file_bytes=base.search_max_file_bytes,
        search_max_chunks=base.search_max_chunks,
        search_chunk_lines=base.search_chunk_lines,
        search_chunk_overlap=base.search_chunk_overlap,
        embedding_backend=base.embedding_backend,
        embedding_base_url=base.embedding_base_url,
        embedding_api_key=base.embedding_api_key,
        embedding_model=base.embedding_model,
        embedding_timeout=base.embedding_timeout,
        embedding_max_batch=base.embedding_max_batch,
        embedding_max_chars=base.embedding_max_chars,
        hybrid_alpha=base.hybrid_alpha,
    )
    key = _pair_key(str(root), search_mode, settings)
    if rebuild:
        _cache.pop(key, None)
    if key in _cache:
        idx, emb = _cache[key]
        return idx, emb, settings

    emb = get_embedder(settings)
    ping = emb.ping() if hasattr(emb, "ping") else {"ok": True}
    if not ping.get("ok"):
        raise EmbeddingError(
            f"bge unavailable (open tunnel 18001->8001): {ping.get('detail')}"
        )
    idx = build_hybrid_index(settings=settings, embedder=emb, workspace=root)
    _cache[key] = (idx, emb)
    return idx, emb, settings


def compare_bge_search(
    query: str,
    *,
    top_k: int = 5,
    workspace_root: str | None = None,
    search_mode: str = "workspace",
    rebuild: bool = False,
) -> dict:
    """对指定工作区做 bge hybrid top-k（含 bm25/emb 分）。"""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query"}
    if top_k < 1 or top_k > 20:
        return {"ok": False, "error": "top_k must be 1..20"}

    mode = (search_mode or "workspace").strip().lower()
    if mode not in {"workspace", "corpus"}:
        return {"ok": False, "error": "search_mode must be workspace or corpus"}

    base = get_settings()
    ws = (workspace_root or base.workspace_root or ".").strip() or "."

    try:
        idx, bge, settings = _get_or_build(
            workspace_root=ws,
            search_mode=mode,
            rebuild=rebuild,
        )
        hits = search_hybrid(idx, q, embedder=bge, settings=settings, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    packed = [
        {
            "rank": i,
            "hybrid": round(h.score, 4),
            "bm25_raw": round(h.bm25_raw, 4),
            "emb_raw": round(h.embedding_raw, 4),
            "path": f"{h.path}:{h.start_line}-{h.end_line}",
            "excerpt": h.excerpt[:160].replace("\n", " "),
        }
        for i, h in enumerate(hits, 1)
    ]
    return {
        "ok": True,
        "query": q,
        "workspace_root": str(Path(ws).expanduser().resolve()),
        "search_mode": mode,
        "rebuild": rebuild,
        "alpha": float(settings.hybrid_alpha),
        "chunk_count": idx.size(),
        "bge": {"backend": bge.name, "dim": getattr(bge, "dim", None), "hits": packed},
    }


def compare_stub_vs_bge(query: str, *, top_k: int = 5) -> dict:
    return compare_bge_search(query, top_k=top_k)
