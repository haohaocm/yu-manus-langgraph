"""CE-6 / EMB-1：embedding index + cosine retrieval（强制 bge，无 stub）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.search.chunking import TextChunk, chunk_corpus
from app.search.embed import EmbeddingError, cosine_similarity, get_embedder
from app.search.embed_index import (
    build_and_save_embedding,
    build_embedding_index,
    load_embedding_index,
    save_embedding_index,
    search_embedding,
)
from tests.conftest_embed import require_bge_embedder


def _fixture_chunks(tmp_path: Path) -> list[TextChunk]:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "sandbox_note.md").write_text(
        "Path sandbox rejects paths that escape the workspace root.\n"
        "Use resolve_safe to join root with user_path.\n",
        encoding="utf-8",
    )
    (corpus / "math_note.md").write_text(
        "BM25 is a lexical ranking function for retrieval.\n"
        "Cosine similarity belongs to embedding search.\n",
        encoding="utf-8",
    )
    return chunk_corpus(
        workspace=tmp_path,
        corpus_dir=corpus,
        window=40,
        overlap=10,
    )


def test_cosine_handmade_vectors() -> None:
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    c = [0.0, 1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(1.0)
    assert cosine_similarity(a, c) == pytest.approx(0.0)


def test_stub_backend_rejected() -> None:
    with pytest.raises(EmbeddingError, match="stub embedding is disabled"):
        get_embedder(Settings(embedding_backend="stub"))


def test_b_t1_build_persist_dim(tmp_path: Path) -> None:
    emb = require_bge_embedder()
    chunks = _fixture_chunks(tmp_path)
    index = build_embedding_index(chunks, embedder=emb, settings=Settings())
    assert index.size() == len(chunks)
    assert index.dim >= 8
    assert all(len(v) == index.dim for v in index.vectors)
    out = save_embedding_index(index, index_dir=tmp_path / "search_index")
    loaded = load_embedding_index(index_dir=out)
    assert loaded.size() == index.size()
    assert loaded.dim == index.dim


def test_b_t2_hit_and_print_scores(tmp_path: Path) -> None:
    emb = require_bge_embedder()
    index = build_embedding_index(_fixture_chunks(tmp_path), embedder=emb, settings=Settings())
    query = "path sandbox escape workspace"
    hits = search_embedding(index, query, embedder=emb, top_k=3)
    print(f"\n=== BGE embedding scores  query={query!r}  backend={emb.name} dim={emb.dim} ===")
    for i, h in enumerate(hits, 1):
        print(f"  {i}. score={h.score:.4f}  {h.path}:{h.start_line}-{h.end_line}")
        print(f"     excerpt: {h.excerpt[:100]!r}")
    assert hits
    assert any("sandbox_note.md" in h.path for h in hits)


def test_b_t3_top_k_sorted(tmp_path: Path) -> None:
    emb = require_bge_embedder()
    index = build_embedding_index(_fixture_chunks(tmp_path), embedder=emb, settings=Settings())
    hits = search_embedding(index, "retrieval BM25 lexical", embedder=emb, top_k=3)
    assert len(hits) <= 3
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_b_t4_empty_query(tmp_path: Path) -> None:
    emb = require_bge_embedder()
    index = build_embedding_index(_fixture_chunks(tmp_path), embedder=emb, settings=Settings())
    assert search_embedding(index, "", embedder=emb) == []
    assert search_embedding(index, "  ", embedder=emb) == []


def test_b1_repo_corpus_smoke_print() -> None:
    emb = require_bge_embedder()
    settings = Settings(workspace_root=".", embedding_backend="http")
    index, path = build_and_save_embedding(settings=settings, embedder=emb)
    assert path.is_dir()
    query = "path sandbox rejects escape"
    hits = search_embedding(index, query, embedder=emb, top_k=5)
    print(f"\n=== BGE repo smoke  query={query!r}  chunks={index.size()} dim={index.dim} ===")
    for i, h in enumerate(hits, 1):
        print(f"  {i}. score={h.score:.4f}  {h.path}:{h.start_line}-{h.end_line}")
    assert hits
    assert any(
        "job_" in h.path or "notes_on_retrieval.md" in h.path or "agent_tools_guide.md" in h.path
        for h in hits
    )


def test_top_k_invalid(tmp_path: Path) -> None:
    emb = require_bge_embedder()
    index = build_embedding_index(_fixture_chunks(tmp_path), embedder=emb, settings=Settings())
    with pytest.raises(ValueError):
        search_embedding(index, "x", embedder=emb, top_k=0)
