"""CE-2.1：工作根目录 + 路径沙箱（内部库，不是给模型调用的 Agent 工具）。

后续 list_dir / read_file / grep 应只通过 resolve_safe 解析用户路径。
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings, get_settings


class PathSandboxError(ValueError):
    """路径越界、非法或无法解析时抛出。"""


def project_root() -> Path:
    """本仓库根目录（与 ``app/`` 同级）。"""
    # app/tools/path_sandbox.py → parents[2] = 仓库根
    return Path(__file__).resolve().parents[2]


def get_workspace_root(settings: Settings | None = None) -> Path:
    """
    解析配置中的 workspace_root 为绝对路径，并确保目录存在。

    - 空：回退 ``artifacts/agent_workspace``（相对仓库根）
    - ``.`` / ``./``：仓库根（显式指定时仍可用）
    - 其它相对路径：相对仓库根拼接
    - 绝对路径：直接使用
    """
    s = settings or get_settings()
    raw = (s.workspace_root or "").strip() or "artifacts/agent_workspace"
    p = Path(raw)
    if p.is_absolute():
        root = p.resolve()
    elif raw in {".", "./"}:
        root = project_root()
    else:
        root = (project_root() / p).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_safe(
    user_path: str,
    *,
    root: Path | None = None,
    settings: Settings | None = None,
) -> Path:
    """
    将用户/模型给出的路径解析到工作根内。

    允许：根内相对路径；已位于根下的绝对路径。
    拒绝：逃出根（含 ``..``）、根外绝对路径、空路径、含空字符。
    """
    base = (root if root is not None else get_workspace_root(settings)).resolve()

    text = (user_path or "").strip()
    if not text:
        raise PathSandboxError("path is empty")
    if "\x00" in text:
        raise PathSandboxError("path contains NUL")

    candidate = Path(text)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (base / candidate).resolve()

    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise PathSandboxError(
            f"path escapes workspace root: {text!r} (root={base})"
        ) from exc

    return resolved
