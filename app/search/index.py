"""CE-6 B0：索引构建 / 落盘 / 加载（先 BM25；embedding 槽位留给 B1）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings
from app.search.bm25 import BM25Okapi
from app.search.chunking import TextChunk, chunk_sources
from app.search.manifest_meta import build_scope_manifest
from app.search.tokenize import tokenize
from app.tools.path_sandbox import get_workspace_root, resolve_safe

MANIFEST_NAME = "manifest.json"
CHUNKS_NAME = "chunks.json"


@dataclass
class SearchHit:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    score: float
    excerpt: str

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": self.score,
            "excerpt": self.excerpt,
        }


@dataclass
class Bm25Index:
    """内存中的 BM25 索引 + chunk 元数据。"""

    chunks: list[TextChunk]
    bm25: BM25Okapi
    backend: str = "bm25"
    corpus_dir: str = "artifacts/corpus"
    chunk_lines: int = 40
    chunk_overlap: int = 10

    def size(self) -> int:
        return len(self.chunks)


def build_bm25_index(
    chunks: list[TextChunk] | None = None,
    *,
    settings: Settings | None = None,
    corpus_dir: Path | str | None = None,
    workspace: Path | None = None,
) -> Bm25Index:
    """从 chunks 或按 search_mode 扫描后构建 BM25 索引。"""
    s = settings or get_settings()
    if chunks is None:
        # 兼容：若显式传了 corpus_dir，临时用 corpus 切块逻辑
        if corpus_dir is not None:
            from app.search.chunking import chunk_corpus

            chunks = chunk_corpus(
                settings=s,
                corpus_dir=corpus_dir,
                workspace=workspace,
            )
        else:
            chunks = chunk_sources(settings=s, workspace=workspace)
    tokenized = [tokenize(c.text) for c in chunks]
    return Bm25Index(
        chunks=list(chunks),
        bm25=BM25Okapi(tokenized),
        backend="bm25",
        corpus_dir=str(corpus_dir or s.search_corpus_dir),
        chunk_lines=int(s.search_chunk_lines),
        chunk_overlap=int(s.search_chunk_overlap),
    )


def resolve_index_dir(
    settings: Settings | None = None,
    index_dir: Path | str | None = None,
) -> Path:
    s = settings or get_settings()
    raw = index_dir if index_dir is not None else s.search_index_dir
    if isinstance(raw, Path):
        if raw.is_absolute():
            return raw.resolve()
        return (get_workspace_root(s) / raw).resolve()
    return resolve_safe(str(raw or "artifacts/search_index"), settings=s)


def save_bm25_index(
    index: Bm25Index,
    *,
    settings: Settings | None = None,
    index_dir: Path | str | None = None,
) -> Path:
    """
    落盘索引产物：

    - ``chunks.json``：chunk 元数据 + 文本
    - ``manifest.json``：backend、窗长、时间等
    """
    out = resolve_index_dir(settings=settings, index_dir=index_dir)
    out.mkdir(parents=True, exist_ok=True)
    chunks_payload = [c.to_dict() for c in index.chunks]
    (out / CHUNKS_NAME).write_text(
        json.dumps(chunks_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    s = settings or get_settings()
    manifest = build_scope_manifest(
        settings=s,
        backend=index.backend,
        chunk_count=index.size(),
        extra={
            "corpus_dir": index.corpus_dir,
            "files": [CHUNKS_NAME, MANIFEST_NAME],
            "note": "BM25 在 load 时从 chunks 文本重建，不单独序列化词表",
        },
    )
    (out / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def load_bm25_index(
    *,
    settings: Settings | None = None,
    index_dir: Path | str | None = None,
) -> Bm25Index:
    """从 ``chunks.json`` 重建 BM25。"""
    base = resolve_index_dir(settings=settings, index_dir=index_dir)
    chunks_path = base / CHUNKS_NAME
    if not chunks_path.is_file():
        raise FileNotFoundError(f"missing index file: {chunks_path}")
    raw = json.loads(chunks_path.read_text(encoding="utf-8"))
    chunks = [
        TextChunk(
            chunk_id=str(item["chunk_id"]),
            path=str(item["path"]),
            start_line=int(item["start_line"]),
            end_line=int(item["end_line"]),
            text=str(item["text"]),
        )
        for item in raw
    ]
    s = settings or get_settings()
    manifest: dict = {}
    man_path = base / MANIFEST_NAME
    if man_path.is_file():
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
    tokenized = [tokenize(c.text) for c in chunks]
    return Bm25Index(
        chunks=chunks,
        bm25=BM25Okapi(tokenized),
        backend=str(manifest.get("backend") or "bm25"),
        corpus_dir=str(manifest.get("corpus_dir") or s.search_corpus_dir),
        chunk_lines=int(manifest.get("chunk_lines") or s.search_chunk_lines),
        chunk_overlap=int(manifest.get("chunk_overlap") or s.search_chunk_overlap),
    )


def search_bm25(
    index: Bm25Index,
    query: str,
    *,
    top_k: int = 5,
    excerpt_chars: int = 200,
) -> list[SearchHit]:
    """对 query 做 BM25 检索，返回按 score 降序的 top-k。"""
    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    q = (query or "").strip()
    if not q:
        return []
    q_tokens = tokenize(q)
    if not q_tokens:
        return []
    scores = index.bm25.get_scores(q_tokens)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    hits: list[SearchHit] = []
    for i in ranked:
        score = float(scores[i])
        if score <= 0:
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


def build_and_save_bm25(
    *,
    settings: Settings | None = None,
    index_dir: Path | str | None = None,
) -> tuple[Bm25Index, Path]:
    """扫描配置语料 → 建 BM25 → 落盘。"""
    index = build_bm25_index(settings=settings)
    path = save_bm25_index(index, settings=settings, index_dir=index_dir)
    return index, path
