"""CE-6：hybrid（混合）打分——强制 bge。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.search.chunking import chunk_corpus
from app.search.hybrid import build_hybrid_index, search_hybrid
from tests.conftest_embed import require_bge_embedder


def _demo_corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "sandbox.md").write_text(
        "Path sandbox blocks escape from workspace root using resolve_safe.\n",
        encoding="utf-8",
    )
    (corpus / "food.md").write_text(
        "Spaghetti recipes with garlic olive oil and cheese.\n",
        encoding="utf-8",
    )
    (corpus / "hybrid.md").write_text(
        "Hybrid ranking mixes BM25 lexical score with embedding cosine similarity.\n",
        encoding="utf-8",
    )
    return corpus


def test_hybrid_prefers_relevant_and_prints(tmp_path: Path) -> None:
    emb = require_bge_embedder()
    corpus = _demo_corpus(tmp_path)
    settings = Settings(hybrid_alpha=0.5)
    chunks = chunk_corpus(workspace=tmp_path, corpus_dir=corpus, window=40, overlap=10)
    index = build_hybrid_index(chunks, settings=settings, embedder=emb)
    query = "path sandbox escape workspace"
    hits = search_hybrid(index, query, embedder=emb, settings=settings, top_k=5)
    print(f"\n=== HYBRID(bge) scores  query={query!r}  alpha=0.5 ===")
    for i, h in enumerate(hits, 1):
        print(
            f"  {i}. hybrid={h.score:.4f}  bm25_raw={h.bm25_raw:.4f} emb_raw={h.embedding_raw:.4f}"
            f"  bm25_n={h.bm25_norm:.4f} emb_n={h.embedding_norm:.4f}"
        )
        print(f"     {h.path}:{h.start_line}-{h.end_line}")
    assert hits
    assert hits[0].path.endswith("sandbox.md")


def test_hybrid_empty_query(tmp_path: Path) -> None:
    emb = require_bge_embedder()
    corpus = _demo_corpus(tmp_path)
    chunks = chunk_corpus(workspace=tmp_path, corpus_dir=corpus, window=40, overlap=10)
    index = build_hybrid_index(chunks, embedder=emb, settings=Settings())
    assert search_hybrid(index, "", embedder=emb) == []


def test_hybrid_alpha_bounds(tmp_path: Path) -> None:
    emb = require_bge_embedder()
    corpus = _demo_corpus(tmp_path)
    chunks = chunk_corpus(workspace=tmp_path, corpus_dir=corpus, window=40, overlap=10)
    index = build_hybrid_index(chunks, embedder=emb, settings=Settings())
    with pytest.raises(ValueError):
        search_hybrid(index, "x", embedder=emb, alpha=1.5)


def test_repo_hybrid_demo_print_chunk_and_scores() -> None:
    emb = require_bge_embedder()
    settings = Settings(
        workspace_root=".",
        embedding_backend="http",
        hybrid_alpha=0.5,
        search_chunk_lines=40,
        search_chunk_overlap=10,
    )
    chunks = chunk_corpus(settings=settings, window=40, overlap=10)
    print(f"\n=== CHUNKING summary  total_chunks={len(chunks)} ===")
    index = build_hybrid_index(chunks, settings=settings, embedder=emb)
    query = "how to stop path escape from workspace"
    hits = search_hybrid(index, query, embedder=emb, settings=settings, top_k=5)
    print(f"\n=== HYBRID(bge)  query={query!r} ===")
    for i, h in enumerate(hits, 1):
        print(
            f"  {i}. hybrid={h.score:.4f}"
            f" | bm25_raw={h.bm25_raw:.4f} emb_raw={h.embedding_raw:.4f}"
        )
        print(f"     {h.path}:{h.start_line}-{h.end_line}")
    assert hits
    assert "kitchen_decoy" not in hits[0].path
    assert hits[0].path.endswith(".md")
