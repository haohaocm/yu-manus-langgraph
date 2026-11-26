"""Line-window chunking with overlap."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from sample_forge.errors import ChunkBudgetError, ValidationError


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def split_line_windows(
    lines: list[str],
    *,
    path: str,
    window: int = 40,
    overlap: int = 10,
) -> list[TextChunk]:
    if window < 1:
        raise ValidationError("window must be >= 1")
    if overlap < 0 or overlap >= window:
        raise ValidationError("overlap must satisfy 0 <= overlap < window")
    n = len(lines)
    if n == 0:
        return []
    step = window - overlap
    out: list[TextChunk] = []
    start0 = 0
    while start0 < n:
        end0 = min(start0 + window, n)
        start_line = start0 + 1
        end_line = end0
        text = "\n".join(lines[start0:end0])
        out.append(
            TextChunk(
                chunk_id=f"{path}:{start_line}-{end_line}",
                path=path,
                start_line=start_line,
                end_line=end_line,
                text=text,
            )
        )
        if end0 >= n:
            break
        start0 += step
    return out


def chunk_file(
    path: Path,
    *,
    rel_path: str,
    window: int = 40,
    overlap: int = 10,
) -> list[TextChunk]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if b"\x00" in raw[:8000]:
        return []
    text = raw.decode("utf-8", errors="replace")
    return split_line_windows(
        text.splitlines(),
        path=rel_path.replace("\\", "/"),
        window=window,
        overlap=overlap,
    )


def enforce_budget(chunks: list[TextChunk], max_chunks: int) -> None:
    if max_chunks > 0 and len(chunks) > max_chunks:
        raise ChunkBudgetError(
            f"chunk count {len(chunks)} exceeds max_chunks={max_chunks}"
        )
