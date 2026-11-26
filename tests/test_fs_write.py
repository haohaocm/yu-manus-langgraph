"""CA-1 S1：write_text_safe / str_replace_safe 单测（不挂 Agent 工具）。"""

from pathlib import Path

from app.config import Settings
from app.tools.fs_write import str_replace, str_replace_safe, write_file, write_text_safe
from app.tools.loader import load_agent_tools


def test_write_creates_and_overwrites_with_backup(tmp_path: Path):
    out = write_text_safe("notes/a.txt", "hello\n", root=tmp_path)
    assert out.startswith("ok ")
    assert "backup=none" in out
    assert (tmp_path / "notes" / "a.txt").read_text(encoding="utf-8") == "hello\n"

    out2 = write_text_safe("notes/a.txt", "world\n", root=tmp_path)
    assert out2.startswith("ok ")
    assert "backup=a.txt.ca1.bak" in out2
    assert (tmp_path / "notes" / "a.txt").read_text(encoding="utf-8") == "world\n"
    assert (tmp_path / "notes" / "a.txt.ca1.bak").read_text(encoding="utf-8") == "hello\n"


def test_write_rejects_escape_nul_and_too_large(tmp_path: Path):
    assert "escapes" in write_text_safe("../x.txt", "a", root=tmp_path)
    assert "NUL" in write_text_safe("b.txt", "a\x00b", root=tmp_path)
    big = "x" * 100
    assert "max_write_bytes" in write_text_safe(
        "c.txt", big, root=tmp_path, max_write_bytes=10
    )


def test_write_rejects_directory(tmp_path: Path):
    (tmp_path / "d").mkdir()
    assert "directory" in write_text_safe("d", "x", root=tmp_path)


def test_str_replace_once_and_all(tmp_path: Path):
    (tmp_path / "t.py").write_text("aa bb aa\n", encoding="utf-8")
    # 多处且未 replace_all → 拒绝
    bad = str_replace_safe("t.py", "aa", "XX", root=tmp_path)
    assert "found 2 times" in bad

    ok = str_replace_safe("t.py", "aa", "XX", root=tmp_path, replace_all=True)
    assert ok.startswith("ok ")
    assert "replacements=2" in ok
    assert (tmp_path / "t.py").read_text(encoding="utf-8") == "XX bb XX\n"
    assert (tmp_path / "t.py.ca1.bak").read_text(encoding="utf-8") == "aa bb aa\n"

    once = str_replace_safe("t.py", "bb", "CC", root=tmp_path)
    assert once.startswith("ok ")
    assert "replacements=1" in once
    assert "CC" in (tmp_path / "t.py").read_text(encoding="utf-8")


def test_str_replace_not_found_and_escape(tmp_path: Path):
    (tmp_path / "t.txt").write_text("only\n", encoding="utf-8")
    assert "not found" in str_replace_safe("t.txt", "nope", "x", root=tmp_path)
    assert "escapes" in str_replace_safe("../t.txt", "a", "b", root=tmp_path)
    assert "does not exist" in str_replace_safe("missing.txt", "a", "b", root=tmp_path)


def test_backup_can_be_disabled(tmp_path: Path):
    (tmp_path / "f.txt").write_text("old", encoding="utf-8")
    out = write_text_safe("f.txt", "new", root=tmp_path, backup=False)
    assert "backup=none" in out
    assert not (tmp_path / "f.txt.ca1.bak").exists()


def test_agent_tools_invoke_and_loader_names(tmp_path: Path, monkeypatch):
    """S2：@tool 可 invoke；loader 含 write_file / str_replace。"""
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        out = write_file.invoke({"path": "w.txt", "content": "one\n"})
        assert out.startswith("ok ")
        assert (tmp_path / "w.txt").read_text(encoding="utf-8") == "one\n"

        out2 = str_replace.invoke(
            {"path": "w.txt", "old": "one", "new": "two", "replace_all": False}
        )
        assert out2.startswith("ok ")
        assert (tmp_path / "w.txt").read_text(encoding="utf-8") == "two\n"
    finally:
        get_settings.cache_clear()

    names = {t.name for t in load_agent_tools(Settings(mcp_enabled=False))}
    assert {"write_file", "str_replace"} <= names
