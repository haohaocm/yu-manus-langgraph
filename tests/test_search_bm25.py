"""CE-6 阶段 B0：BM25 index + retrieval 单测。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.search.chunking import TextChunk, chunk_corpus
from app.search.index import (
    build_and_save_bm25,
    build_bm25_index,
    load_bm25_index,
    save_bm25_index,
    search_bm25,
)
from app.search.tokenize import tokenize


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


def test_tokenize_ascii_and_cjk() -> None:
    assert "workspace" in tokenize("Escape the Workspace root")
    assert "沙" in tokenize("路径沙箱")


def test_b_t1_build_and_persist(tmp_path: Path) -> None:
    """B-T1: 建索引，落盘后 size = chunk 数。"""
    chunks = _fixture_chunks(tmp_path)
    index = build_bm25_index(chunks, settings=Settings())
    assert index.size() == len(chunks)
    out = save_bm25_index(index, index_dir=tmp_path / "search_index")
    assert (out / "chunks.json").is_file()
    assert (out / "manifest.json").is_file()
    loaded = load_bm25_index(index_dir=out)
    assert loaded.size() == index.size()


def test_b_t2_lexical_hit(tmp_path: Path) -> None:
    """B-T2: query 贴近 sandbox 文案 → 命中对应 path；打印打分。"""
    index = build_bm25_index(_fixture_chunks(tmp_path), settings=Settings())
    query = "path sandbox escape workspace"
    hits = search_bm25(index, query, top_k=3)
    print(f"\n=== B0 BM25 scores  query={query!r} ===")
    for i, h in enumerate(hits, 1):
        print(f"  {i}. score={h.score:.4f}  {h.path}:{h.start_line}-{h.end_line}")
        print(f"     excerpt: {h.excerpt[:100]!r}")
    assert hits
    assert any("sandbox_note.md" in h.path for h in hits)


def test_b_t3_top_k_sorted(tmp_path: Path) -> None:
    """B-T3: top_k=3，至多 3 条且 score 降序。"""
    index = build_bm25_index(_fixture_chunks(tmp_path), settings=Settings())
    hits = search_bm25(index, "retrieval BM25 lexical", top_k=3)
    assert len(hits) <= 3
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_b_t4_empty_query(tmp_path: Path) -> None:
    """B-T4: 空 query → 空列表，不抛异常。"""
    index = build_bm25_index(_fixture_chunks(tmp_path), settings=Settings())
    assert search_bm25(index, "") == []
    assert search_bm25(index, "   ") == []


def test_b_t5_repo_corpus_query_smoke() -> None:
    """仓库语料：英文 query 能打出命中 path。"""
    index, path = build_and_save_bm25(
        settings=Settings(workspace_root=".", search_mode="corpus"),
    )
    assert path.is_dir()
    hits = search_bm25(index, "path sandbox rejects escape", top_k=5)
    assert hits
    print("B0 smoke hits:")
    for h in hits:
        print(f"  score={h.score:.4f} {h.path}:{h.start_line}-{h.end_line}")
    assert any(
        "job_" in h.path or "notes_on_retrieval.md" in h.path or "agent_tools_guide.md" in h.path
        for h in hits
    )


def test_top_k_invalid(tmp_path: Path) -> None:
    index = build_bm25_index(_fixture_chunks(tmp_path), settings=Settings())
    with pytest.raises(ValueError):
        search_bm25(index, "x", top_k=0)
