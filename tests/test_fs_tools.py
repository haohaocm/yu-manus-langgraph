"""CE-2：list_dir / read_file / grep 单测。"""

from pathlib import Path

from app.config import Settings
from app.tools.fs_tools import (
    grep,
    grep_text,
    list_dir,
    list_dir_entries,
    read_file,
    read_file_text,
)
from app.tools.loader import load_agent_tools


def test_list_dir_and_read_file_happy_path(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# hi", encoding="utf-8")

    listing = list_dir_entries(".", root=tmp_path)
    assert "dir\tsub" in listing
    assert "file\tb.md" in listing
    assert "error:" not in listing

    sub = list_dir_entries("sub", root=tmp_path)
    assert "file\ta.txt" in sub

    content = read_file_text("sub/a.txt", root=tmp_path, offset=2, limit=1)
    assert "lines=2-2 of 3" in content
    body = content.split("\n", 1)[1]
    assert body.strip() == "line2"


def test_list_dir_rejects_escape_and_missing(tmp_path: Path):
    out = list_dir_entries("../outside", root=tmp_path)
    assert out.startswith("error:")
    assert "escapes" in out

    missing = list_dir_entries("nope", root=tmp_path)
    assert "does not exist" in missing


def test_read_file_rejects_dir_and_escape(tmp_path: Path):
    (tmp_path / "d").mkdir()
    assert "not a file" in read_file_text("d", root=tmp_path)
    assert "escapes" in read_file_text("../x", root=tmp_path)


def test_read_file_truncates_by_limit(tmp_path: Path):
    lines = "\n".join(f"L{i}" for i in range(1, 21))
    (tmp_path / "big.txt").write_text(lines + "\n", encoding="utf-8")
    out = read_file_text("big.txt", root=tmp_path, offset=1, limit=5)
    assert "L1" in out and "L5" in out
    assert "L6" not in out


def test_grep_finds_lines_with_glob(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.txt").write_text("hello in txt\n", encoding="utf-8")
    (tmp_path / "pkg" / "c.py").write_text("x = 1\n", encoding="utf-8")

    out = grep_text("hello", "pkg", glob="*.py", root=tmp_path)
    assert "error:" not in out
    assert "pkg/a.py:1:" in out.replace("\\", "/")
    assert "hello in txt" not in out  # glob 排除 txt

    one = grep_text("return", "pkg/a.py", root=tmp_path)
    assert "pkg/a.py:2:" in one.replace("\\", "/")


def test_grep_no_match_and_bad_regex_and_escape(tmp_path: Path):
    (tmp_path / "f.txt").write_text("abc\n", encoding="utf-8")
    assert "no matches" in grep_text("zzz", ".", root=tmp_path)
    assert "invalid regex" in grep_text("[", ".", root=tmp_path)
    assert "escapes" in grep_text("a", "../x", root=tmp_path)


def test_tool_wrappers_three_tools_on_real_workspace():
    listing = list_dir.invoke({"path": "tests"})
    assert "error:" not in listing
    assert "test_fs_tools.py" in listing

    snippet = read_file.invoke({"path": "tests/test_fs_tools.py", "offset": 1, "limit": 8})
    assert "list_dir" in snippet or "CE-2" in snippet

    hits = grep.invoke({"pattern": "def test_grep_finds", "path": "tests", "glob": "*.py"})
    assert "error:" not in hits
    assert "test_fs_tools.py" in hits


def test_loader_includes_all_fs_tools():
    names = {t.name for t in load_agent_tools(Settings(mcp_enabled=False))}
    assert {
        "terminate",
        "list_dir",
        "read_file",
        "grep",
        "write_file",
        "str_replace",
        "run_shell",
        "add",
        "echo",
    } <= names
