"""IDX-WS 手工验收：对 artifacts/workspace_demos/github_jieba 逐步打印中间结果。

用法（项目根）：
  # 仅扫描+切块+BM25（无需 bge）
  .\\.venv\\Scripts\\python.exe scripts\\demo_idx_ws_jieba.py

  # 真 bge hybrid（需本机隧道 18001→8001）
  .\\.venv\\Scripts\\python.exe scripts\\demo_idx_ws_jieba.py --real-bge
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from app.config import Settings, get_settings
from app.search.chunking import chunk_workspace, iter_scoped_files
from app.search.hybrid import build_and_save_hybrid, search_hybrid
from app.search.index import build_bm25_index, search_bm25
from app.search.scope import (
    ignore_dir_names,
    is_file_within_size_limit,
    normalize_search_mode,
    search_glob_patterns,
)


class _FakeEmbedder:
    name = "fake:demo"
    dim = 16

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            v = [0.0] * self.dim
            for i, b in enumerate(t.encode("utf-8", errors="ignore")[:128]):
                v[i % self.dim] += (b % 17) / 17.0
            out.append(v)
        return out


def _banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--real-bge",
        action="store_true",
        help="使用实验室 bge（需 18001）；默认用假 embedder 演示落盘",
    )
    parser.add_argument(
        "--workspace",
        default="artifacts/workspace_demos/github_jieba",
        help="要索引的工程根（默认 jieba 浅克隆）",
    )
    args = parser.parse_args()

    get_settings.cache_clear()
    root = Path(args.workspace).resolve()
    if not root.is_dir():
        print(f"workspace 不存在: {root}")
        return 1

    index_dir = Path("artifacts/search_index/jieba_demo").resolve()
    settings = Settings(
        workspace_root=str(root),
        search_mode="workspace",
        search_index_dir=str(index_dir),
        search_max_file_bytes=512_000,
        search_max_chunks=8000,
        embedding_backend="http",
        hybrid_alpha=0.5,
    )

    _banner("步骤 0：环境与配置")
    print(f"workspace = {root}")
    print(f"search_mode = {normalize_search_mode(settings)}")
    print(f"ignore_dirs = {sorted(ignore_dir_names(settings))}")
    print(f"globs = {search_glob_patterns(settings)}")
    print(f"max_file_bytes = {settings.search_max_file_bytes}")
    print(f"max_chunks = {settings.search_max_chunks}")
    print(f"index_dir = {index_dir}")
    print(f"embedder = {'bge(http:18001)' if args.real_bge else 'fake:demo（离线演示）'}")

    _banner("步骤 1：扫描文件（iter_scoped_files）")
    files = iter_scoped_files(root, settings=settings)
    print(f"保留文件数 files_kept = {len(files)}")
    print("前 12 个相对路径：")
    for p in files[:12]:
        rel = p.relative_to(root).as_posix()
        print(f"  {p.stat().st_size:8d}  {rel}")

    # 展示被大小上限跳过的候选（同扩展名）
    skipped: list[tuple[int, str]] = []
    for pattern in search_glob_patterns(settings):
        for p in root.rglob(pattern):
            if p.is_file() and not is_file_within_size_limit(p, settings):
                skipped.append((p.stat().st_size, p.relative_to(root).as_posix()))
    skipped = sorted(set(skipped), reverse=True)
    print(f"因 max_file_bytes 跳过 = {len(skipped)}（展示最大几项）")
    for sz, rel in skipped[:8]:
        print(f"  SKIP {sz:8d}  {rel}")

    _banner("步骤 2：切块（chunk_workspace）")
    chunks = chunk_workspace(settings=settings, workspace=root)
    print(f"总 chunk 数 = {len(chunks)}")
    by_path = Counter(c.path for c in chunks)
    print("按 path 块数 Top 8：")
    for path, n in by_path.most_common(8):
        print(f"  {n:4d}  {path}")

    readme = [c for c in chunks if c.path == "README.md"]
    print(f"\nREADME.md 切成 {len(readme)} 块；打印第 1 块全文：")
    if readme:
        c0 = readme[0]
        print(f"--- {c0.chunk_id} ---")
        print(c0.text)
        print("--- end ---")

    _banner("步骤 3：BM25 索引 + 查询（无需 bge）")
    bm25 = build_bm25_index(chunks, settings=settings)
    for q in ("中文分词 精确模式 搜索引擎模式", "自定义词典 新词"):
        hits = search_bm25(bm25, q, top_k=5)
        print(f"\nquery = {q!r}")
        for i, h in enumerate(hits, 1):
            prev = h.excerpt.replace("\n", " ")[:100]
            print(f"  {i}. score={h.score:.4f}  {h.path}:{h.start_line}-{h.end_line}")
            print(f"     preview: {prev}")

    _banner("步骤 4：Hybrid 建索引并落盘")
    if args.real_bge:
        from tests.conftest_embed import require_bge_embedder

        emb = require_bge_embedder()
    else:
        emb = _FakeEmbedder()
        print("（未开 --real-bge：embedding 分为假向量，只验证接线与落盘）")

    index, saved = build_and_save_hybrid(
        settings=settings,
        embedder=emb,
        index_dir=index_dir,
        workspace=root,
    )
    print(f"saved = {saved}")
    print(f"hybrid.chunks = {index.size()}")
    man = json.loads((saved / "manifest.json").read_text(encoding="utf-8"))
    print("manifest 摘要：")
    for k in (
        "backend",
        "search_mode",
        "workspace_root",
        "chunk_count",
        "max_file_bytes",
        "max_chunks",
        "embedder",
        "dim",
        "created_at",
    ):
        if k in man:
            print(f"  {k}: {man[k]}")
    print(f"  产物: {[p.name for p in saved.iterdir()]}")

    _banner("步骤 5：Hybrid 检索")
    q = "中文分词精确模式"
    hits = search_hybrid(index, q, embedder=emb, settings=settings, top_k=5)
    print(f"query = {q!r}")
    for i, h in enumerate(hits, 1):
        print(
            f"  {i}. score={h.score:.4f} bm25={h.bm25_raw:.4f} emb={h.embedding_raw:.4f} "
            f"path={h.path}:{h.start_line}-{h.end_line}"
        )
        print(f"     preview: {h.excerpt.replace(chr(10), ' ')[:100]}")

    _banner("完成")
    print("真 bge 复测：先开 18001 隧道，再加 --real-bge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
