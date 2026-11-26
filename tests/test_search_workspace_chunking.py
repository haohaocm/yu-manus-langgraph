"""IDX-WS S2：chunk_workspace 扫描与切块。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.search.chunking import chunk_workspace, iter_scoped_files
from app.search.scope import SearchScopeError


def _mini_ws(tmp_path: Path) -> Path:
    """构造迷你工作区：含源码、应忽略的 .venv、超大文件。"""
    (tmp_path / "src").mkdir()
    # 内容保持较小，避免误触 search_max_file_bytes
    (tmp_path / "src" / "hello.py").write_text(
        "\n".join(f"L{i}" for i in range(1, 45)) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Mini\n\nignore and limits demo\n", encoding="utf-8")
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "noise.py").write_text("SECRET = 1\n", encoding="utf-8")
    big = tmp_path / "huge.txt"
    big.write_bytes(b"x" * 2000)
    return tmp_path


def test_s2_iter_skips_venv_and_large_file(tmp_path: Path) -> None:
    root = _mini_ws(tmp_path)
    settings = Settings(
        workspace_root=str(root),
        search_max_file_bytes=500,
        search_globs="*.py,*.md,*.txt",
    )
    files = iter_scoped_files(root, settings=settings)
    rels = {p.relative_to(root).as_posix() for p in files}
    assert "src/hello.py" in rels
    assert "README.md" in rels
    assert not any(".venv" in r for r in rels)
    assert "huge.txt" not in rels


def test_s2_chunk_workspace_relative_paths(tmp_path: Path) -> None:
    root = _mini_ws(tmp_path)
    settings = Settings(
        workspace_root=str(root),
        search_max_file_bytes=500,
        search_chunk_lines=40,
        search_chunk_overlap=10,
        search_globs="*.py,*.md,*.txt",
    )
    chunks = chunk_workspace(settings=settings, workspace=root)
    assert chunks
    assert all("/" not in c.path or not c.path.startswith("/") for c in chunks)
    assert any(c.path == "src/hello.py" for c in chunks)
    assert chunks[0].start_line >= 1
    assert chunks[0].text


def test_s2_chunk_budget_raises(tmp_path: Path) -> None:
    root = _mini_ws(tmp_path)
    settings = Settings(
        workspace_root=str(root),
        search_max_file_bytes=500,
        search_max_chunks=1,
        search_globs="*.py,*.md",
        search_chunk_lines=10,
        search_chunk_overlap=0,
    )
    with pytest.raises(SearchScopeError, match="search_max_chunks"):
        chunk_workspace(settings=settings, workspace=root)


def test_s2_sample_forge_smoke() -> None:
    """对 corpus 内 sample_forge 冒烟：有块，且不含 .venv / 超大 txt。"""
    forge = Path("artifacts/corpus/sample_forge").resolve()
    assert forge.is_dir()
    settings = Settings(
        workspace_root=str(forge),
        search_mode="workspace",
        search_max_file_bytes=512_000,
        search_max_chunks=8000,
    )
    chunks = chunk_workspace(settings=settings, workspace=forge)
    assert len(chunks) >= 5
    paths = {c.path for c in chunks}
    assert any(p.startswith("src/") for p in paths)
    assert not any(".venv" in p or "node_modules" in p for p in paths)
    assert "logs/oversized_notes.txt" not in paths
