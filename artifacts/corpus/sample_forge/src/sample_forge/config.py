"""Simple configuration object for demos."""

from __future__ import annotations

from dataclasses import dataclass

from sample_forge.ignore_rules import DEFAULT_IGNORE
from sample_forge.scanner import DEFAULT_GLOBS


@dataclass
class ForgeConfig:
    window: int = 40
    overlap: int = 10
    max_file_bytes: int = 512_000
    max_chunks: int = 8000
    ignore_dirs: frozenset[str] = DEFAULT_IGNORE
    globs: tuple[str, ...] = DEFAULT_GLOBS
    hybrid_alpha: float = 0.5
