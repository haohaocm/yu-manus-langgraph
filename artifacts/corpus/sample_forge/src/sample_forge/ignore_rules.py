"""Directory ignore helpers (blacklist)."""

from __future__ import annotations

from pathlib import Path

DEFAULT_IGNORE: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "search_index",
        ".idea",
        ".vscode",
        "dist",
        "build",
    }
)


def parse_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def has_ignored_part(path: Path, ignore: frozenset[str] = DEFAULT_IGNORE) -> bool:
    return any(part in ignore for part in path.parts)


def should_skip_dir(path: Path, ignore: frozenset[str] = DEFAULT_IGNORE) -> bool:
    return path.name in ignore or has_ignored_part(path, ignore)
