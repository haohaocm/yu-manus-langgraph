"""EMB-1 S3：HttpOpenAIEmbedder 输入限制与错误信息。"""

from __future__ import annotations

import pytest

from app.search.embed import EmbeddingError, HttpOpenAIEmbedder


def _emb() -> HttpOpenAIEmbedder:
    return HttpOpenAIEmbedder(
        base_url="http://127.0.0.1:18001/v1",
        model="bge-m3",
        timeout=5.0,
        max_batch=2,
        max_chars_per_text=20,
    )


def test_s3_reject_empty_list() -> None:
    with pytest.raises(EmbeddingError, match="empty"):
        _emb().embed([])


def test_s3_reject_blank_string() -> None:
    with pytest.raises(EmbeddingError, match="blank"):
        _emb().embed(["  "])


def test_s3_truncates_too_long(monkeypatch) -> None:
    """超长文本截断后再发（不再直接拒绝），便于全仓索引。"""
    emb = _emb()
    calls: list[list[str]] = []

    def _fake_batch(batch: list[str]) -> list[list[float]]:
        calls.append(list(batch))
        return [[0.1, 0.2] for _ in batch]

    monkeypatch.setattr(emb, "_embed_one_batch", _fake_batch)
    vecs = emb.embed(["x" * 21])
    assert len(vecs) == 1
    assert calls and len(calls[0][0]) == 20  # max_chars_per_text=20


def test_s3_auto_batches_when_over_max_batch() -> None:
    """超过 max_batch 时应自动分批，而不是整批报错（IDX-WS 全仓必需）。"""
    from tests.conftest_embed import require_bge_embedder

    require_bge_embedder()  # 需 18001
    emb = HttpOpenAIEmbedder(
        base_url="http://127.0.0.1:18001/v1",
        model="bge-m3",
        timeout=60.0,
        max_batch=2,
        max_chars_per_text=8000,
    )
    vecs = emb.embed(["分词", "精确模式", "搜索引擎"])
    assert len(vecs) == 3
    assert len(vecs[0]) == len(vecs[1]) == len(vecs[2]) > 0


def test_s3_bad_host_message() -> None:
    emb = HttpOpenAIEmbedder(
        base_url="http://127.0.0.1:19999/v1",
        model="bge-m3",
        timeout=2.0,
    )
    with pytest.raises(EmbeddingError, match="connection failed|timeout|tunnel"):
        emb.embed(["hello"])
