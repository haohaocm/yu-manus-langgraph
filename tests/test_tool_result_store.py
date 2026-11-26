"""CE-3：长工具结果落盘单测。"""

import re
from pathlib import Path

from app.config import Settings
from app.prompts import NEXT_STEP_PROMPT
from app.tools.loader import load_agent_tools
from app.tools.tool_result_store import maybe_persist_tool_result


def test_settings_ce3_defaults():
    assert Settings.model_fields["tool_result_file_threshold"].default == 1000
    assert Settings.model_fields["tool_output_dir"].default == "artifacts/tool_outputs"


def test_short_result_not_persisted(tmp_path: Path):
    s = Settings(
        workspace_root=str(tmp_path),
        tool_result_file_threshold=1000,
        tool_output_dir="artifacts/tool_outputs",
    )
    out = maybe_persist_tool_result("echo", "short", settings=s, root=tmp_path)
    assert out == "short"
    out_dir = tmp_path / "artifacts" / "tool_outputs"
    assert not out_dir.exists() or list(out_dir.glob("*.txt")) == []


def test_long_result_persisted_with_naming(tmp_path: Path):
    s = Settings(
        workspace_root=str(tmp_path),
        tool_result_file_threshold=1000,
        tool_output_dir="artifacts/tool_outputs",
    )
    body = "X" * 1000
    out = maybe_persist_tool_result("searchWeb", body, settings=s, root=tmp_path)
    assert out.startswith("[tool_result_persisted]")
    assert "tool=searchWeb" in out
    assert "chars=1000" in out
    assert "path=artifacts/tool_outputs/" in out
    assert "hint: use read_file" in out

    m = re.search(r"path=(artifacts/tool_outputs/\S+\.txt)", out)
    assert m
    rel = m.group(1)
    assert re.search(r"\d{8}_\d{6}_searchWeb_[0-9a-f]{4}\.txt$", rel.split("/")[-1])
    full = tmp_path / rel
    assert full.is_file()
    assert full.read_text(encoding="utf-8") == body


def test_echo_tool_via_loader_persists(tmp_path: Path):
    s = Settings(
        workspace_root=str(tmp_path),
        tool_result_file_threshold=1000,
        tool_output_dir="artifacts/tool_outputs",
        mcp_enabled=False,
    )
    # get_workspace_root 读 settings.workspace_root；wrap 使用同一 Settings
    tools = {t.name: t for t in load_agent_tools(s, persist_long_results=True)}
    assert "echo" in tools
    long_text = "Y" * 1200
    # wrap 内 get_workspace_root(s) 依赖 workspace_root 配置
    result = tools["echo"].invoke({"text": long_text})
    assert "[tool_result_persisted]" in result
    assert "path=artifacts/tool_outputs/" in result
    files = list((tmp_path / "artifacts" / "tool_outputs").glob("*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == long_text


def test_prompt_mentions_persisted_hint():
    assert "[tool_result_persisted]" in NEXT_STEP_PROMPT
    assert "read_file" in NEXT_STEP_PROMPT
