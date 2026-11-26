"""CA-1 S4：工具调用验收（tmp 沙箱；与 scripts/demo_ca1_s4_write.py 同路径）。"""

from pathlib import Path

from app.config import get_settings
from app.tools.fs_tools import read_file
from app.tools.fs_write import str_replace, write_file


def test_s4_tool_invoke_write_replace_read_escape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        rel = "demo/hello.txt"
        w = write_file.invoke({"path": rel, "content": "alpha\nbeta\n"})
        assert w.startswith("ok ")

        r = str_replace.invoke(
            {"path": rel, "old": "alpha", "new": "ALPHA", "replace_all": False}
        )
        assert r.startswith("ok ")

        shown = read_file.invoke({"path": rel, "offset": 1, "limit": 10})
        assert "ALPHA" in shown
        assert "beta" in shown
        assert (tmp_path / rel).read_text(encoding="utf-8") == "ALPHA\nbeta\n"

        bad = write_file.invoke({"path": "../x.txt", "content": "x"})
        assert bad.startswith("error:")
        assert "escapes" in bad
    finally:
        get_settings.cache_clear()
