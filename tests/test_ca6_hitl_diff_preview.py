"""CA-6 S2：diff/preview 提案与批准后写盘。"""

from pathlib import Path

from app.config import get_settings
from app.hitl.diff_preview import apply_approved_tool, build_hitl_proposal, build_unified_diff
from app.hitl.policy import HitlDecision


def test_unified_diff_shows_minus_plus():
    """difflib 行应含删除/新增标记。"""
    text = build_unified_diff("a\nb\n", "a\nc\n", path="t.txt")
    assert "-b" in text or "-b\n" in text or "\n-b" in text
    assert "+c" in text


def test_write_file_new_preview(tmp_path: Path, monkeypatch):
    """新建文件：提案含 preview，且尚未落盘。"""
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    prop = build_hitl_proposal(
        "write_file",
        {"path": "outputs/hello.txt", "content": "hello hitl"},
        root=tmp_path,
        hitl_enabled=True,
    )
    assert prop.verdict.decision == HitlDecision.NEED_APPROVE
    assert prop.error == ""
    assert "hello hitl" in prop.preview_text
    assert "(new file)" in prop.diff_text
    assert not (tmp_path / "outputs" / "hello.txt").exists()


def test_str_replace_diff_then_apply(tmp_path: Path, monkeypatch):
    """已有文件：先出 diff，批准后再写。"""
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    target = tmp_path / "note.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")

    prop = build_hitl_proposal(
        "str_replace",
        {"path": "note.txt", "old": "beta", "new": "gamma"},
        root=tmp_path,
        hitl_enabled=True,
    )
    assert prop.verdict.decision == HitlDecision.NEED_APPROVE
    assert "-beta" in prop.diff_text
    assert "+gamma" in prop.diff_text
    # 提案阶段未改文件
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\n"

    out = apply_approved_tool(
        "str_replace",
        {"path": "note.txt", "old": "beta", "new": "gamma"},
        root=tmp_path,
    )
    assert out.startswith("ok")
    assert target.read_text(encoding="utf-8") == "alpha\ngamma\n"


def test_shell_blacklist_proposal_has_error(tmp_path: Path, monkeypatch):
    """黑名单命令：提案带 error，不应去执行。"""
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    prop = build_hitl_proposal(
        "run_shell",
        {"command": "rm -rf something"},
        root=tmp_path,
        hitl_enabled=True,
    )
    assert prop.verdict.decision == HitlDecision.HARD_DENY
    assert prop.error
