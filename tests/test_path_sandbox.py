"""CE-2.1：路径沙箱单测（不依赖 LLM / MCP）。"""

from pathlib import Path

import pytest

from app.config import Settings
from app.tools.path_sandbox import (
    PathSandboxError,
    get_workspace_root,
    project_root,
    resolve_safe,
)


def test_project_root_is_repo_with_app_dir():
    root = project_root()
    assert (root / "app").is_dir()
    assert (root / "tests").is_dir()


def test_get_workspace_root_dot_is_project_root():
    """显式 ``.`` 仍表示仓库根。"""
    s = Settings(workspace_root=".")
    assert get_workspace_root(s) == project_root()


def test_get_workspace_root_default_agent_sandbox():
    """默认配置落在 artifacts/agent_workspace，且目录会被创建。"""
    s = Settings()
    root = get_workspace_root(s)
    assert root == (project_root() / "artifacts" / "agent_workspace").resolve()
    assert root.is_dir()


def test_get_workspace_root_absolute_override(tmp_path: Path):
    s = Settings(workspace_root=str(tmp_path))
    assert get_workspace_root(s) == tmp_path.resolve()


def test_resolve_safe_relative_inside(tmp_path: Path):
    (tmp_path / "doc").mkdir()
    (tmp_path / "doc" / "a.md").write_text("hi", encoding="utf-8")
    got = resolve_safe("doc/a.md", root=tmp_path)
    assert got == (tmp_path / "doc" / "a.md").resolve()
    assert got.read_text(encoding="utf-8") == "hi"


def test_resolve_safe_rejects_parent_escape(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    with pytest.raises(PathSandboxError, match="escapes"):
        resolve_safe("../outside.txt", root=tmp_path / "sub")


def test_resolve_safe_rejects_absolute_outside(tmp_path: Path):
    outside = (tmp_path.parent / "definitely_outside_ce21.txt").resolve()
    with pytest.raises(PathSandboxError, match="escapes"):
        resolve_safe(str(outside), root=tmp_path)


def test_resolve_safe_allows_absolute_inside(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_text("ok", encoding="utf-8")
    got = resolve_safe(str(f.resolve()), root=tmp_path)
    assert got == f.resolve()


def test_resolve_safe_rejects_empty_and_nul(tmp_path: Path):
    with pytest.raises(PathSandboxError, match="empty"):
        resolve_safe("  ", root=tmp_path)
    with pytest.raises(PathSandboxError, match="NUL"):
        resolve_safe("a\x00b", root=tmp_path)
