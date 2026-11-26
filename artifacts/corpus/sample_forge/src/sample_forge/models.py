"""Dataclasses shared across modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FileRef:
    """A file kept after ignore + size gates."""

    path: str
    size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BuildManifest:
    """Parameters used to build an index snapshot."""

    workspace_root: str
    window: int
    overlap: int
    ignore_dirs: tuple[str, ...]
    globs: tuple[str, ...]
    max_file_bytes: int
    max_chunks: int
    file_count: int
    chunk_count: int

    def to_dict(self) -> dict:
        data = asdict(self)
        data["ignore_dirs"] = list(self.ignore_dirs)
        data["globs"] = list(self.globs)
        return data
