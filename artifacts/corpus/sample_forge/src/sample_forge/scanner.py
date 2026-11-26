"""Walk a workspace and yield source-like files."""

from __future__ import annotations

from pathlib import Path

from sample_forge.ignore_rules import DEFAULT_IGNORE, has_ignored_part
from sample_forge.models import FileRef

DEFAULT_GLOBS: tuple[str, ...] = (
    "*.py",
    "*.md",
    "*.txt",
    "*.toml",
    "*.yml",
    "*.yaml",
    "*.json",
)


def iter_source_files(
    root: Path,
    *,
    ignore_dirs: frozenset[str] = DEFAULT_IGNORE,
    globs: tuple[str, ...] = DEFAULT_GLOBS,
    max_file_bytes: int = 512_000,
) -> list[Path]:
    """Return sorted files under root that pass ignore / glob / size gates."""
    root = root.resolve()
    found: set[Path] = set()
    for pattern in globs:
        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            if has_ignored_part(path, ignore_dirs):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if max_file_bytes > 0 and size > max_file_bytes:
                continue
            found.add(path.resolve())
    return sorted(found, key=lambda p: p.as_posix().lower())


def list_file_refs(
    root: Path,
    *,
    ignore_dirs: frozenset[str] = DEFAULT_IGNORE,
    globs: tuple[str, ...] = DEFAULT_GLOBS,
    max_file_bytes: int = 512_000,
) -> list[FileRef]:
    refs: list[FileRef] = []
    root = root.resolve()
    for path in iter_source_files(
        root,
        ignore_dirs=ignore_dirs,
        globs=globs,
        max_file_bytes=max_file_bytes,
    ):
        rel = path.relative_to(root).as_posix()
        refs.append(FileRef(path=rel, size_bytes=path.stat().st_size))
    return refs
