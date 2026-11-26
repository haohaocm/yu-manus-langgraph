"""CE-6 B1：embedding 索引构建 / 落盘 / cosine 检索。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings
from app.search.chunking import TextChunk, chunk_sources
from app.search.embed import Embedder, cosine_similarity, get_embedder
from app.search.index import (
    CHUNKS_NAME,
    MANIFEST_NAME,
    SearchHit,
    resolve_index_dir,
)
from app.search.manifest_meta import build_scope_manifest

VECTORS_NAME = "vectors.json"


@dataclass
class EmbeddingIndex:
    """chunk 元数据 + 等维向量。"""

    chunks: list[TextChunk]
    vectors: list[list[float]]
    embedder_name: str
    dim: int
    backend: str = "embedding"
    corpus_dir: str = "artifacts/corpus"
    chunk_lines: int = 40
    chunk_overlap: int = 10

    def size(self) -> int:
        return len(self.chunks)


def build_embedding_index(
    chunks: list[TextChunk] | None = None,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    corpus_dir: Path | str | None = None,
    workspace: Path | None = None,
) -> EmbeddingIndex:
    """切块（或沿用已有）→ embed → 内存索引。"""
    s = settings or get_settings()
    emb = embedder or get_embedder(s)
    if chunks is None:
        if corpus_dir is not None:
            from app.search.chunking import chunk_corpus

            chunks = chunk_corpus(
                settings=s,
                corpus_dir=corpus_dir,
                workspace=workspace,
            )
        else:
            chunks = chunk_sources(settings=s, workspace=workspace)
    texts = [c.text for c in chunks]
    vectors = emb.embed(texts) if texts else []
    if len(vectors) != len(chunks):
        raise RuntimeError("embedder returned mismatched vector count")
    dim = len(vectors[0]) if vectors else int(getattr(emb, "dim", 0) or 0)
    for v in vectors:
        if len(v) != dim:
            raise ValueError("inconsistent vector dimensions in corpus")
    return EmbeddingIndex(
        chunks=list(chunks),
        vectors=vectors,
        embedder_name=str(getattr(emb, "name", type(emb).__name__)),
        dim=dim,
        backend="embedding",
        corpus_dir=str(corpus_dir or s.search_corpus_dir),
        chunk_lines=int(s.search_chunk_lines),
        chunk_overlap=int(s.search_chunk_overlap),
    )


def save_embedding_index(
    index: EmbeddingIndex,
    *,
    settings: Settings | None = None,
    index_dir: Path | str | None = None,
) -> Path:
    """落盘 chunks.json + vectors.json + manifest.json。"""
    out = resolve_index_dir(settings=settings, index_dir=index_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / CHUNKS_NAME).write_text(
        json.dumps([c.to_dict() for c in index.chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / VECTORS_NAME).write_text(
        json.dumps(index.vectors, ensure_ascii=False),
        encoding="utf-8",
    )
    s = settings or get_settings()
    manifest = build_scope_manifest(
        settings=s,
        backend=index.backend,
        chunk_count=index.size(),
        extra={
            "embedder": index.embedder_name,
            "dim": index.dim,
            "corpus_dir": index.corpus_dir,
            "files": [CHUNKS_NAME, VECTORS_NAME, MANIFEST_NAME],
        },
    )
    (out / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def load_embedding_index(
    *,
    settings: Settings | None = None,
    index_dir: Path | str | None = None,
) -> EmbeddingIndex:
    base = resolve_index_dir(settings=settings, index_dir=index_dir)
    chunks_path = base / CHUNKS_NAME
    vectors_path = base / VECTORS_NAME
    if not chunks_path.is_file() or not vectors_path.is_file():
        raise FileNotFoundError(f"missing embedding index under {base}")
    raw_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    vectors = json.loads(vectors_path.read_text(encoding="utf-8"))
    chunks = [
        TextChunk(
            chunk_id=str(item["chunk_id"]),
            path=str(item["path"]),
            start_line=int(item["start_line"]),
            end_line=int(item["end_line"]),
            text=str(item["text"]),
        )
        for item in raw_chunks
    ]
    if len(chunks) != len(vectors):
        raise ValueError("chunks/vectors length mismatch")
    s = settings or get_settings()
    manifest: dict = {}
    man_path = base / MANIFEST_NAME
    if man_path.is_file():
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
    dim = int(manifest.get("dim") or (len(vectors[0]) if vectors else 0))
    return EmbeddingIndex(
        chunks=chunks,
        vectors=[list(map(float, v)) for v in vectors],
        embedder_name=str(manifest.get("embedder") or "unknown"),
        dim=dim,
        backend=str(manifest.get("backend") or "embedding"),
        corpus_dir=str(manifest.get("corpus_dir") or s.search_corpus_dir),
        chunk_lines=int(manifest.get("chunk_lines") or s.search_chunk_lines),
        chunk_overlap=int(manifest.get("chunk_overlap") or s.search_chunk_overlap),
    )


def search_embedding(
    index: EmbeddingIndex,
    query: str,
    *,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
    top_k: int = 5,
    excerpt_chars: int = 200,
    min_score: float = 0.0,
) -> list[SearchHit]:
    """embed(query) → cosine → top-k。"""
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    q = (query or "").strip()
    if not q:
        return []
    emb = embedder or get_embedder(settings)
    qv = emb.embed([q])[0]
    if index.dim and len(qv) != index.dim:
        raise ValueError(f"query dim {len(qv)} != index dim {index.dim}")
    scores = [cosine_similarity(qv, v) for v in index.vectors]
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    hits: list[SearchHit] = []
    for i in ranked:
        score = float(scores[i])
        if score < min_score:
            continue
        chunk = index.chunks[i]
        excerpt = chunk.text if len(chunk.text) <= excerpt_chars else chunk.text[: excerpt_chars - 3] + "..."
        hits.append(
            SearchHit(
                chunk_id=chunk.chunk_id,
                path=chunk.path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                score=score,
                excerpt=excerpt,
            )
        )
        if len(hits) >= top_k:
            break
    return hits


def build_and_save_embedding(
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    index_dir: Path | str | None = None,
) -> tuple[EmbeddingIndex, Path]:
    index = build_embedding_index(settings=settings, embedder=embedder)
    path = save_embedding_index(index, settings=settings, index_dir=index_dir)
    return index, path
