"""CA-1：工作区内安全写文本。

- S1 纯函数：``write_text_safe``（整文件覆盖）、``str_replace_safe``（局部替换）
- S2 Agent 工具：``write_file`` / ``str_replace``（薄包装，走 Settings 默认备份/上限）
- 路径一律经 ``resolve_safe``；超大 / 含 NUL 拒绝
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from app.config import Settings, get_settings
from app.tools.path_sandbox import PathSandboxError, resolve_safe

_BAK_SUFFIX = ".ca1.bak"


def _max_write_bytes(settings: Settings | None, override: int | None) -> int:
    if override is not None:
        return max(1, int(override))
    s = settings or get_settings()
    return max(1, int(getattr(s, "max_write_bytes", 512_000) or 512_000))


def _backup_enabled(settings: Settings | None, override: bool | None) -> bool:
    if override is not None:
        return bool(override)
    s = settings or get_settings()
    return bool(getattr(s, "write_backup", True))


def _reject_content(content: str, *, max_bytes: int) -> str | None:
    """校验待写入字符串；不合格返回 error 文案，合格返回 None。"""
    if content is None:  # type: ignore[comparison-overlap]
        return "error: content is None"
    if not isinstance(content, str):
        return "error: content must be str"
    if "\x00" in content:
        return "error: refuses binary-like content (NUL byte)"
    try:
        raw = content.encode("utf-8")
    except UnicodeEncodeError as exc:
        return f"error: content is not UTF-8 encodable: {exc}"
    if len(raw) > max_bytes:
        return f"error: content exceeds max_write_bytes={max_bytes} (got {len(raw)} bytes)"
    return None


def _backup_path(target: Path) -> Path:
    return target.with_name(target.name + _BAK_SUFFIX)


def _maybe_backup(target: Path, *, enabled: bool) -> str:
    """若目标已存在且开启备份，写成 ``name.ca1.bak``；返回 backup= 字段值。"""
    if not enabled or not target.is_file():
        return "none"
    bak = _backup_path(target)
    try:
        bak.write_bytes(target.read_bytes())
    except OSError as exc:
        raise OSError(f"backup failed: {exc}") from exc
    return bak.name


def write_text_safe(
    path: str,
    content: str,
    *,
    root: Path | None = None,
    settings: Settings | None = None,
    backup: bool | None = None,
    max_write_bytes: int | None = None,
) -> str:
    """
    整文件写入：新建或覆盖。不接收「旧内容」——要局部替换请用 ``str_replace_safe``。

    返回 ``ok ...`` 或 ``error: ...``（与读工具风格一致）。
    """
    limit = _max_write_bytes(settings, max_write_bytes)
    bad = _reject_content(content, max_bytes=limit)
    if bad:
        return bad

    try:
        target = resolve_safe(path, root=root, settings=settings)
    except PathSandboxError as exc:
        return f"error: {exc}"

    if target.exists() and target.is_dir():
        return f"error: path is a directory: {path}"

    do_bak = _backup_enabled(settings, backup)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        bak_name = _maybe_backup(target, enabled=do_bak)
        raw = content.encode("utf-8")
        target.write_bytes(raw)
    except OSError as exc:
        return f"error: cannot write {path}: {exc}"

    return f"ok path={path} bytes={len(raw)} backup={bak_name}"


def str_replace_safe(
    path: str,
    old: str,
    new: str,
    *,
    replace_all: bool = False,
    root: Path | None = None,
    settings: Settings | None = None,
    backup: bool | None = None,
    max_write_bytes: int | None = None,
) -> str:
    """
    在已有文本文件中把 ``old`` 换成 ``new``。

    - ``replace_all=False``（默认）：``old`` 必须恰好出现一次，否则报错
    - ``replace_all=True``：替换全部出现；一次都没有则报错
    """
    if not isinstance(old, str) or not isinstance(new, str):
        return "error: old and new must be str"
    if old == "":
        return "error: old must be non-empty"
    if "\x00" in old or "\x00" in new:
        return "error: refuses binary-like content (NUL byte)"

    try:
        target = resolve_safe(path, root=root, settings=settings)
    except PathSandboxError as exc:
        return f"error: {exc}"

    if not target.exists():
        return f"error: path does not exist: {path}"
    if not target.is_file():
        return f"error: not a file: {path}"

    try:
        raw = target.read_bytes()
    except OSError as exc:
        return f"error: cannot read {path}: {exc}"

    if b"\x00" in raw[:8000]:
        return f"error: refuses binary file: {path}"

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return f"error: file is not valid UTF-8: {path}"

    count = text.count(old)
    if count == 0:
        return f"error: old text not found in {path}"
    if not replace_all and count > 1:
        return (
            f"error: old text found {count} times in {path}; "
            "pass replace_all=true to replace all, or make old unique"
        )

    updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    limit = _max_write_bytes(settings, max_write_bytes)
    bad = _reject_content(updated, max_bytes=limit)
    if bad:
        return bad

    do_bak = _backup_enabled(settings, backup)
    try:
        bak_name = _maybe_backup(target, enabled=do_bak)
        out = updated.encode("utf-8")
        target.write_bytes(out)
    except OSError as exc:
        return f"error: cannot write {path}: {exc}"

    return (
        f"ok path={path} bytes={len(out)} replacements={count if replace_all else 1} "
        f"backup={bak_name}"
    )


@tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a UTF-8 text file inside the workspace root (full-file write).

    Args:
        path: Relative path from workspace root.
        content: Full new file contents (UTF-8 text; no NUL bytes).
    """
    return write_text_safe(path, content)


@tool
def str_replace(path: str, old: str, new: str, replace_all: bool = False) -> str:
    """Replace text in an existing UTF-8 file inside the workspace root.

    Args:
        path: Relative path from workspace root.
        old: Exact substring to find (must be non-empty).
        new: Replacement substring.
        replace_all: If false (default), old must occur exactly once; if true, replace all.
    """
    return str_replace_safe(path, old, new, replace_all=replace_all)
