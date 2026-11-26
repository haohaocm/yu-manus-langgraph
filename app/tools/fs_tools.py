"""CE-2：本地 list_dir / read_file / grep（经 path_sandbox；纯 Python，不调系统 grep）。"""

from __future__ import annotations

import re
from pathlib import Path

from langchain_core.tools import tool

from app.tools.path_sandbox import PathSandboxError, get_workspace_root, resolve_safe

# 防止一次列出/读入/命中过多撑爆上下文
_DEFAULT_MAX_ENTRIES = 200
_DEFAULT_MAX_CHARS = 80_000
_DEFAULT_MAX_MATCHES = 50
_SKIP_DIR_NAMES = frozenset(
    {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache"}
)


def list_dir_entries(
    path: str = ".",
    *,
    root: Path | None = None,
    max_entries: int = _DEFAULT_MAX_ENTRIES,
) -> str:
    """列出目录项；返回文本。越界/错误以 ``error:`` 前缀说明（便于回喂模型）。"""
    try:
        target = resolve_safe(path, root=root)
    except PathSandboxError as exc:
        return f"error: {exc}"

    if not target.exists():
        return f"error: path does not exist: {path}"
    if not target.is_dir():
        return f"error: not a directory: {path}"

    items: list[str] = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        return f"error: cannot list {path}: {exc}"

    for child in children:
        if len(items) >= max_entries:
            items.append(f"... truncated, max_entries={max_entries}")
            break
        kind = "dir" if child.is_dir() else "file"
        items.append(f"{kind}\t{child.name}")

    if not items:
        return f"(empty directory) {path}"
    header = f"listing path={path} count={min(len(children), max_entries)}"
    return header + "\n" + "\n".join(items)


def read_file_text(
    path: str,
    *,
    offset: int = 1,
    limit: int = 200,
    root: Path | None = None,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """
    按行读取文本文件。

    - offset: 起始行号（从 1 开始）
    - limit: 最多返回多少行
    """
    try:
        target = resolve_safe(path, root=root)
    except PathSandboxError as exc:
        return f"error: {exc}"

    if not target.exists():
        return f"error: path does not exist: {path}"
    if not target.is_file():
        return f"error: not a file: {path}"

    if offset < 1:
        return "error: offset must be >= 1"
    if limit < 1:
        return "error: limit must be >= 1"

    try:
        # 粗略拒绝明显二进制
        raw = target.read_bytes()
    except OSError as exc:
        return f"error: cannot read {path}: {exc}"

    if b"\x00" in raw[:8000]:
        return f"error: refuses binary file: {path}"

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    lines = text.splitlines()
    start = offset - 1
    chunk = lines[start : start + limit]
    body = "\n".join(chunk)
    if len(body) > max_chars:
        body = body[:max_chars] + f"\n... truncated, max_chars={max_chars}"

    end_line = start + len(chunk)
    meta = f"file={path} lines={offset}-{end_line} of {len(lines)}"
    return meta + "\n" + body


def grep_text(
    pattern: str,
    path: str = ".",
    *,
    glob: str = "*",
    root: Path | None = None,
    max_matches: int = _DEFAULT_MAX_MATCHES,
) -> str:
    """
    在工作区内按正则搜索文本行（跨平台纯 Python，不调用 Linux grep / Windows findstr）。

    - path: 文件或目录（相对工作根）
    - glob: 仅当 path 为目录时，用于匹配文件名（如 ``*.py``）
    """
    if not (pattern or "").strip():
        return "error: pattern is empty"

    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"error: invalid regex: {exc}"

    try:
        target = resolve_safe(path, root=root)
    except PathSandboxError as exc:
        return f"error: {exc}"

    if not target.exists():
        return f"error: path does not exist: {path}"

    base = (root if root is not None else get_workspace_root()).resolve()
    files: list[Path] = []
    if target.is_file():
        files = [target]
    elif target.is_dir():
        try:
            for child in target.rglob(glob or "*"):
                if not child.is_file():
                    continue
                if any(part in _SKIP_DIR_NAMES for part in child.parts):
                    continue
                try:
                    child.resolve().relative_to(base)
                except ValueError:
                    continue
                files.append(child)
        except OSError as exc:
            return f"error: cannot walk {path}: {exc}"
    else:
        return f"error: not a file or directory: {path}"

    hits: list[str] = []
    truncated = False
    for fp in sorted(files):
        try:
            raw = fp.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8000]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")

        try:
            rel = fp.resolve().relative_to(base).as_posix()
        except ValueError:
            rel = fp.name

        for i, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                hits.append(f"{rel}:{i}:{line}")
                if len(hits) >= max_matches:
                    truncated = True
                    break
        if truncated:
            break

    if not hits:
        return f"no matches for pattern={pattern!r} under path={path} glob={glob!r}"

    header = f"matches={len(hits)} pattern={pattern!r} path={path} glob={glob!r}"
    body = "\n".join(hits)
    if truncated:
        body += f"\n... truncated, max_matches={max_matches}"
    return header + "\n" + body


@tool
def list_dir(path: str = ".") -> str:
    """List files and subdirectories under a path inside the workspace root.

    Args:
        path: Relative path from workspace root (use "." for root).
    """
    return list_dir_entries(path)


@tool
def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
    """Read a text file inside the workspace root (line slice).

    Args:
        path: Relative path from workspace root.
        offset: 1-based start line (default 1).
        limit: Max number of lines to return (default 200).
    """
    return read_file_text(path, offset=offset, limit=limit)


@tool
def grep(pattern: str, path: str = ".", glob: str = "*") -> str:
    """Search file contents with a regular expression (cross-platform; not the OS grep binary).

    Args:
        pattern: Regular expression to search for.
        path: File or directory under workspace root (default ".").
        glob: Filename pattern when searching a directory (e.g. "*.py").
    """
    return grep_text(pattern, path, glob=glob)
