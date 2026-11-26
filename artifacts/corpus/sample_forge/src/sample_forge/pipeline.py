"""End-to-end scan -> chunk -> manifest for demos."""

from __future__ import annotations

from pathlib import Path

from sample_forge.chunking import TextChunk, chunk_file, enforce_budget
from sample_forge.config import ForgeConfig
from sample_forge.models import BuildManifest
from sample_forge.scanner import iter_source_files


def build_chunks(root: Path, config: ForgeConfig | None = None) -> list[TextChunk]:
    cfg = config or ForgeConfig()
    root = root.resolve()
    chunks: list[TextChunk] = []
    files = iter_source_files(
        root,
        ignore_dirs=cfg.ignore_dirs,
        globs=cfg.globs,
        max_file_bytes=cfg.max_file_bytes,
    )
    for path in files:
        rel = path.relative_to(root).as_posix()
        chunks.extend(
            chunk_file(path, rel_path=rel, window=cfg.window, overlap=cfg.overlap)
        )
    enforce_budget(chunks, cfg.max_chunks)
    return chunks


def build_manifest(
    root: Path,
    chunks: list[TextChunk],
    config: ForgeConfig | None = None,
) -> BuildManifest:
    cfg = config or ForgeConfig()
    files = iter_source_files(
        root,
        ignore_dirs=cfg.ignore_dirs,
        globs=cfg.globs,
        max_file_bytes=cfg.max_file_bytes,
    )
    return BuildManifest(
        workspace_root=str(root.resolve()),
        window=cfg.window,
        overlap=cfg.overlap,
        ignore_dirs=tuple(sorted(cfg.ignore_dirs)),
        globs=cfg.globs,
        max_file_bytes=cfg.max_file_bytes,
        max_chunks=cfg.max_chunks,
        file_count=len(files),
        chunk_count=len(chunks),
    )
