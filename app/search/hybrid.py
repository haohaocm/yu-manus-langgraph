"""hybrid retrieval（混合检索）= 归一化后的 BM25 + embedding 加权。

IDX-WS S3：用 ``chunk_sources``（按 search_mode 扫 workspace 或 corpus）建双路索引，并可落盘。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings
from app.search.chunking import TextChunk, chunk_sources
from app.search.embed import Embedder, cosine_similarity, get_embedder
from app.search.embed_index import (
    VECTORS_NAME,
    EmbeddingIndex,
    build_embedding_index,
)
from app.search.index import (
    CHUNKS_NAME,
    MANIFEST_NAME,
    Bm25Index,
    build_bm25_index,
    resolve_index_dir,
)
from app.search.manifest_meta import build_scope_manifest
from app.search.tokenize import tokenize


@dataclass
class HybridHit:
    """混合命中：综合分 + 两路原始/归一化分。"""

    chunk_id: str
    path: str
    start_line: int
    end_line: int
    score: float  # hybrid
    excerpt: str
    bm25_raw: float
    embedding_raw: float
    bm25_norm: float
    embedding_norm: float
    alpha: float  # embedding 权重

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": self.score,
            "bm25_raw": self.bm25_raw,
            "embedding_raw": self.embedding_raw,
            "bm25_norm": self.bm25_norm,
            "embedding_norm": self.embedding_norm,
            "alpha": self.alpha,
            "excerpt": self.excerpt,
        }


@dataclass
class HybridIndex:
    """同一批 chunks 上的双路索引（顺序对齐）。"""

    chunks: list[TextChunk]
    bm25: Bm25Index
    embedding: EmbeddingIndex

    def size(self) -> int:
        return len(self.chunks)


def _max_normalize(scores: list[float]) -> list[float]:
    """按本 query 的 max 做归一化到 [0,1]；全 0 则全 0。"""
    if not scores:
        return []
    peak = max(scores)
    if peak <= 0:
        return [0.0] * len(scores)
    return [s / peak for s in scores]


def build_hybrid_index(
    chunks: list[TextChunk] | None = None,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    corpus_dir=None,
    workspace=None,
) -> HybridIndex:
    """扫描或沿用 chunks，同时建 BM25 + embedding（共用同一列表）。

    ``chunks is None`` 时走 ``chunk_sources``：
    - search_mode=workspace → 全仓（IDX-WS）
    - search_mode=corpus → 仅语料目录（CE-6 兼容）

    注意：``corpus_dir`` 仅在调用方自己 ``chunk_corpus`` 时有意义；
    此处若已传 chunks 则忽略；未传 chunks 时由 settings.search_mode 决定范围。
    """
    s = settings or get_settings()
    if chunks is None:
        # IDX-WS：默认按 mode 切块（含 ignore / 上限）
        chunks = chunk_sources(settings=s, workspace=workspace)
        # 若调用方仍传了旧参数 corpus_dir 且 mode=corpus，chunk_sources 已用配置中的 corpus_dir
        _ = corpus_dir  # 保留签名兼容，避免旧调用方 TypeError
    chunks = list(chunks)
    bm25 = build_bm25_index(chunks, settings=s)
    emb = build_embedding_index(chunks, settings=s, embedder=embedder)
    return HybridIndex(chunks=chunks, bm25=bm25, embedding=emb)


def save_hybrid_index(
    index: HybridIndex,
    *,
    settings: Settings | None = None,
    index_dir: Path | str | None = None,
) -> Path:
    """落盘 hybrid 索引：chunks.json + vectors.json + manifest.json。

    BM25 不单独序列化词表，加载时可由 chunks 重建（与 CE-6 一致）。
    """
    s = settings or get_settings()
    out = resolve_index_dir(settings=s, index_dir=index_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / CHUNKS_NAME).write_text(
        json.dumps([c.to_dict() for c in index.chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / VECTORS_NAME).write_text(
        json.dumps(index.embedding.vectors, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest = build_scope_manifest(
        settings=s,
        backend="hybrid",
        chunk_count=index.size(),
        extra={
            "embedder": index.embedding.embedder_name,
            "dim": index.embedding.dim,
            "files": [CHUNKS_NAME, VECTORS_NAME, MANIFEST_NAME],
            "note": "BM25 在需要时可从 chunks 文本重建；向量见 vectors.json",
        },
    )
    (out / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def build_and_save_hybrid(
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    index_dir: Path | str | None = None,
    workspace=None,
) -> tuple[HybridIndex, Path]:
    """切块 → 建 hybrid → 落盘，返回索引与目录路径。"""
    index = build_hybrid_index(
        settings=settings,
        embedder=embedder,
        workspace=workspace,
    )
    path = save_hybrid_index(index, settings=settings, index_dir=index_dir)
    return index, path


def search_hybrid(
    index: HybridIndex,
    query: str,
    *,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
    top_k: int = 5,
    alpha: float | None = None,
    excerpt_chars: int = 200,
) -> list[HybridHit]:
    """
    hybrid_score = (1 - alpha) * bm25_norm + alpha * embedding_norm

    - alpha：embedding 权重，默认读配置 ``hybrid_alpha``（0.5）
    - 两路分数先各自按本次 query 的 max 归一化，再加权
    """
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    s = settings or get_settings()
    a = float(s.hybrid_alpha if alpha is None else alpha)
    if a < 0 or a > 1:
        raise ValueError("alpha must be in [0, 1]")

    q = (query or "").strip()
    if not q:
        return []

    n = index.size()
    if n == 0:
        return []
    if index.bm25.size() != n or index.embedding.size() != n:
        raise ValueError("hybrid index size mismatch")

    q_tokens = tokenize(q)
    bm25_raw = index.bm25.bm25.get_scores(q_tokens) if q_tokens else [0.0] * n

    emb = embedder or get_embedder(s)
    qv = emb.embed([q])[0]
    emb_raw = [cosine_similarity(qv, v) for v in index.embedding.vectors]

    bm25_norm = _max_normalize([float(x) for x in bm25_raw])
    emb_norm = _max_normalize([float(x) for x in emb_raw])

    ranked = sorted(
        range(n),
        key=lambda i: (1.0 - a) * bm25_norm[i] + a * emb_norm[i],
        reverse=True,
    )

    hits: list[HybridHit] = []
    for i in ranked:
        hybrid = (1.0 - a) * bm25_norm[i] + a * emb_norm[i]
        if hybrid <= 0 and bm25_raw[i] <= 0 and emb_raw[i] <= 0:
            continue
        chunk = index.chunks[i]
        excerpt = chunk.text if len(chunk.text) <= excerpt_chars else chunk.text[: excerpt_chars - 3] + "..."
        hits.append(
            HybridHit(
                chunk_id=chunk.chunk_id,
                path=chunk.path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                score=hybrid,
                excerpt=excerpt,
                bm25_raw=float(bm25_raw[i]),
                embedding_raw=float(emb_raw[i]),
                bm25_norm=bm25_norm[i],
                embedding_norm=emb_norm[i],
                alpha=a,
            )
        )
        if len(hits) >= top_k:
            break
    return hits
