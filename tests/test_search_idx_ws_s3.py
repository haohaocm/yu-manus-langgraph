"""IDX-WS S3：workspace 切块 → hybrid 建索引 → 落盘 manifest。"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.search.chunking import chunk_workspace
from app.search.hybrid import build_and_save_hybrid, build_hybrid_index, search_hybrid
from app.search.index import MANIFEST_NAME
from tests.conftest_embed import require_bge_embedder


class _FakeEmbedder:
    """离线假 embedder：用字符哈希凑固定维向量，仅测 S3 落盘/检索接线。"""

    name = "fake:s3"
    dim = 8

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            v = [0.0] * self.dim
            for i, ch in enumerate(t.encode("utf-8", errors="ignore")[:64]):
                v[i % self.dim] += (ch % 13) / 13.0
            out.append(v)
        return out


def test_s3_offline_save_manifest_with_fake_embedder(tmp_path: Path) -> None:
    """不依赖 bge：对 sample_forge 建 hybrid 并检查 manifest 字段。"""
    forge = Path("artifacts/corpus/sample_forge").resolve()
    index_dir = tmp_path / "forge_index_offline"
    settings = Settings(
        workspace_root=str(forge),
        search_mode="workspace",
        search_index_dir=str(index_dir),
        search_max_file_bytes=512_000,
        search_max_chunks=8000,
        embedding_backend="http",
        hybrid_alpha=0.5,
    )
    emb = _FakeEmbedder()
    index, out = build_and_save_hybrid(
        settings=settings,
        embedder=emb,
        index_dir=index_dir,
        workspace=forge,
    )
    man = json.loads((Path(out) / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert man["backend"] == "hybrid"
    assert man["search_mode"] == "workspace"
    assert man["chunk_count"] == index.size() >= 5
    assert ".venv" in man["ignore_dirs"]
    assert (Path(out) / "chunks.json").is_file()
    assert (Path(out) / "vectors.json").is_file()
    hits = search_hybrid(index, "ignore_dirs skip venv", embedder=emb, settings=settings, top_k=3)
    assert hits
    print("\n=== S3 offline hybrid hits ===")
    for i, h in enumerate(hits, 1):
        print(f"{i}. score={h.score:.4f} path={h.path}:{h.start_line}-{h.end_line}")


def test_s3_sample_forge_hybrid_save_and_search(tmp_path: Path) -> None:
    """对 sample_forge 建 hybrid，落盘，检索「忽略目录 / ignore」应命中相关 path。"""
    emb = require_bge_embedder()
    forge = Path("artifacts/corpus/sample_forge").resolve()
    assert forge.is_dir()

    index_dir = tmp_path / "forge_index"
    settings = Settings(
        workspace_root=str(forge),
        search_mode="workspace",
        search_index_dir=str(index_dir),
        search_max_file_bytes=512_000,
        search_max_chunks=8000,
        embedding_backend="http",
        hybrid_alpha=0.5,
    )

    chunks = chunk_workspace(settings=settings, workspace=forge)
    assert len(chunks) >= 5

    index, out = build_and_save_hybrid(
        settings=settings,
        embedder=emb,
        index_dir=index_dir,
        workspace=forge,
    )
    assert out == index_dir.resolve() or out.exists()
    man = json.loads((Path(out) / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert man["backend"] == "hybrid"
    assert man["search_mode"] == "workspace"
    assert man["chunk_count"] == index.size()
    assert "ignore_dirs" in man and ".venv" in man["ignore_dirs"]
    assert (Path(out) / "chunks.json").is_file()
    assert (Path(out) / "vectors.json").is_file()

    query = "目录忽略规则 ignore_dirs 跳过 venv"
    hits = search_hybrid(index, query, embedder=emb, settings=settings, top_k=5)
    print("\n=== S3 hybrid hits ===")
    for i, h in enumerate(hits, 1):
        print(
            f"{i}. score={h.score:.4f} bm25={h.bm25_raw:.4f} emb={h.embedding_raw:.4f} "
            f"path={h.path}:{h.start_line}-{h.end_line}"
        )
        print(f"   preview: {h.excerpt[:120].replace(chr(10), ' ')}")
    assert hits
    paths = " ".join(h.path for h in hits)
    assert (
        "ignore" in paths
        or "architecture" in paths
        or "scanner" in paths
        or "README" in paths
        or "faq" in paths
    )
