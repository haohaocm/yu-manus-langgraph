"""IDX-WS S3：索引 manifest（清单）公共字段。

把 search_mode / ignore / 上限等写进 manifest，便于判断索引是否过期、如何重建。
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.search.scope import (
    ignore_dir_names,
    normalize_search_mode,
    search_glob_patterns,
)
from app.tools.path_sandbox import get_workspace_root


def build_scope_manifest(
    *,
    settings: Settings | None = None,
    backend: str,
    chunk_count: int,
    extra: dict | None = None,
) -> dict:
    """组装落盘用的 manifest 字典（含 IDX-WS 范围元数据）。"""
    s = settings or get_settings()
    root = get_workspace_root(s)
    payload: dict = {
        "backend": backend,
        "chunk_count": int(chunk_count),
        "search_mode": normalize_search_mode(s),
        "workspace_root": str(root),
        "corpus_dir": s.search_corpus_dir,
        "ignore_dirs": sorted(ignore_dir_names(s)),
        "globs": list(search_glob_patterns(s)),
        "max_file_bytes": int(s.search_max_file_bytes),
        "max_chunks": int(s.search_max_chunks),
        "chunk_lines": int(s.search_chunk_lines),
        "chunk_overlap": int(s.search_chunk_overlap),
        "hybrid_alpha": float(s.hybrid_alpha),
        "embedding_backend": s.embedding_backend,
        "embedding_model": s.embedding_model,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload
