"""切块（chunking）：固定行窗 + overlap + 行号元数据。

- CE-6：``chunk_corpus`` 只扫 ``artifacts/corpus``（旧行为保留）
- IDX-WS S2：``chunk_workspace`` 按 S1 的 ignore / glob / 大小上限扫工作区
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import Settings, get_settings
from app.search.scope import (
    SearchScopeError,
    ensure_chunk_budget,
    ignore_dir_names,
    is_file_within_size_limit,
    path_has_ignored_dir,
    search_glob_patterns,
)
from app.tools.path_sandbox import PathSandboxError, get_workspace_root, resolve_safe

# CE-6 旧默认（corpus 模式仍可用）
_DEFAULT_GLOBS = ("*.py", "*.md", "*.txt")
_SKIP_DIR_NAMES = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "search_index"}
)


@dataclass(frozen=True)
class TextChunk:
    """一块带定位信息的文本。"""

    chunk_id: str
    path: str  # 相对 workspace 的 POSIX 路径
    start_line: int  # 1-based inclusive
    end_line: int  # 1-based inclusive
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
    """
    对已按行拆好的文本做滑动窗口切块。

    - window: 窗长（行数）
    - overlap: 相邻块重叠行数（须 < window）
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if overlap < 0 or overlap >= window:
        raise ValueError("overlap must satisfy 0 <= overlap < window")

    n = len(lines)
    if n == 0:
        return []

    step = window - overlap
    chunks: list[TextChunk] = []
    start0 = 0  # 0-based
    while start0 < n:
        end0 = min(start0 + window, n)  # exclusive
        start_line = start0 + 1
        end_line = end0
        piece = lines[start0:end0]
        text = "\n".join(piece)
        chunk_id = f"{path}:{start_line}-{end_line}"
        chunks.append(
            TextChunk(
                chunk_id=chunk_id,
                path=path,
                start_line=start_line,
                end_line=end_line,
                text=text,
            )
        )
        if end0 >= n:
            break
        start0 += step
    return chunks


def chunk_file(
    file_path: Path,
    *,
    rel_path: str,
    window: int = 40,
    overlap: int = 10,
) -> list[TextChunk]:
    """读取单个文本文件并切块；二进制或无法读取则返回空列表。"""
    try:
        raw = file_path.read_bytes()
    except OSError:
        return []
    if b"\x00" in raw[:8000]:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return split_line_windows(
        lines,
        path=rel_path.replace("\\", "/"),
        window=window,
        overlap=overlap,
    )


def iter_corpus_files(corpus_root: Path, globs: tuple[str, ...] = _DEFAULT_GLOBS) -> list[Path]:
    """列出语料目录下待切块文件（跳过常见无关目录）。"""
    if not corpus_root.is_dir():
        return []
    found: list[Path] = []
    for pattern in globs:
        for p in corpus_root.rglob(pattern):
            if not p.is_file():
                continue
            if any(part in _SKIP_DIR_NAMES for part in p.parts):
                continue
            found.append(p)
    return sorted(set(found), key=lambda x: str(x).lower())


def chunk_corpus(
    *,
    settings: Settings | None = None,
    corpus_dir: Path | str | None = None,
    workspace: Path | None = None,
    window: int | None = None,
    overlap: int | None = None,
) -> list[TextChunk]:
    """
    扫描 corpus 目录并切块。

    路径均相对 workspace；corpus 默认 ``artifacts/corpus``。
    """
    s = settings or get_settings()
    base = (workspace if workspace is not None else get_workspace_root(s)).resolve()
    rel_corpus = (corpus_dir if corpus_dir is not None else s.search_corpus_dir) or "artifacts/corpus"
    if isinstance(rel_corpus, Path):
        corpus_path = rel_corpus if rel_corpus.is_absolute() else (base / rel_corpus)
    else:
        corpus_path = Path(rel_corpus)
        if not corpus_path.is_absolute():
            corpus_path = base / corpus_path
    corpus_path = corpus_path.resolve()

    try:
        corpus_path.relative_to(base)
    except ValueError as exc:
        raise PathSandboxError(f"corpus escapes workspace: {corpus_path}") from exc

    win = int(window if window is not None else s.search_chunk_lines)
    ov = int(overlap if overlap is not None else s.search_chunk_overlap)

    out: list[TextChunk] = []
    for fp in iter_corpus_files(corpus_path):
        rel = fp.resolve().relative_to(base).as_posix()
        out.extend(chunk_file(fp, rel_path=rel, window=win, overlap=ov))
    return out


def resolve_corpus_dir(settings: Settings | None = None) -> Path:
    """解析配置中的语料目录绝对路径（须在 workspace 内）。"""
    s = settings or get_settings()
    return resolve_safe(s.search_corpus_dir or "artifacts/corpus", settings=s)


def iter_scoped_files(
    scan_root: Path,
    *,
    settings: Settings | None = None,
) -> list[Path]:
    """在 scan_root 下按 S1 规则列出待切块文件。

    规则顺序：glob 白名单 → ignore 目录黑名单 → 单文件大小上限。
    不删除任何磁盘文件，只决定「进不进索引」。
    """
    s = settings or get_settings()
    root = scan_root.resolve()
    if not root.is_dir():
        return []

    ignore = ignore_dir_names(s)
    globs = search_glob_patterns(s)
    found: set[Path] = set()
    for pattern in globs:
        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            # 路径任一层落在黑名单（如 .venv）则跳过
            if path_has_ignored_dir(path, ignore):
                continue
            # 单文件过大：跳过，不算向量
            if not is_file_within_size_limit(path, s):
                continue
            found.add(path.resolve())
    return sorted(found, key=lambda p: p.as_posix().lower())


def chunk_workspace(
    *,
    settings: Settings | None = None,
    workspace: Path | None = None,
    window: int | None = None,
    overlap: int | None = None,
    enforce_budget: bool = True,
) -> list[TextChunk]:
    """IDX-WS S2：扫描整个 workspace 根并切块。

    - 路径字段均为相对 workspace 的 POSIX 路径
    - ``enforce_budget=True`` 时，块数超过 ``search_max_chunks`` 抛 ``SearchScopeError``
    """
    s = settings or get_settings()
    base = (workspace if workspace is not None else get_workspace_root(s)).resolve()
    if not base.is_dir():
        raise PathSandboxError(f"workspace is not a directory: {base}")

    win = int(window if window is not None else s.search_chunk_lines)
    ov = int(overlap if overlap is not None else s.search_chunk_overlap)

    out: list[TextChunk] = []
    for fp in iter_scoped_files(base, settings=s):
        try:
            rel = fp.resolve().relative_to(base).as_posix()
        except ValueError as exc:
            # 理论上不应发生；防御性跳过逃逸路径
            raise PathSandboxError(f"file escapes workspace: {fp}") from exc
        out.extend(chunk_file(fp, rel_path=rel, window=win, overlap=ov))

    if enforce_budget:
        ensure_chunk_budget(len(out), s)
    return out


def chunk_sources(
    *,
    settings: Settings | None = None,
    workspace: Path | None = None,
    window: int | None = None,
    overlap: int | None = None,
) -> list[TextChunk]:
    """按 ``search_mode`` 选择切块入口（给 S3 建索引用）。

    - workspace → ``chunk_workspace``
    - corpus → ``chunk_corpus``（CE-6 兼容）
    """
    from app.search.scope import normalize_search_mode

    s = settings or get_settings()
    mode = normalize_search_mode(s)
    if mode == "corpus":
        return chunk_corpus(
            settings=s,
            workspace=workspace,
            window=window,
            overlap=overlap,
        )
    return chunk_workspace(
        settings=s,
        workspace=workspace,
        window=window,
        overlap=overlap,
        enforce_budget=True,
    )


# 再导出，方便测试引用
__all__ = [
    "TextChunk",
    "split_line_windows",
    "chunk_file",
    "iter_corpus_files",
    "chunk_corpus",
    "resolve_corpus_dir",
    "iter_scoped_files",
    "chunk_workspace",
    "chunk_sources",
    "SearchScopeError",
]
