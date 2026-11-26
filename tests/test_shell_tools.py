"""CA-2：run_shell_safe / run_shell 单测。"""

from pathlib import Path

from app.config import Settings
from app.tools.loader import load_agent_tools
from app.tools.shell_tools import run_shell, run_shell_safe


def test_run_shell_echo_ok(tmp_path: Path):
    # Windows / Unix 都能跑的 python 一行
    out = run_shell_safe(
        'python -c "print(12345)"',
        working_directory=".",
        root=tmp_path,
        timeout_sec=30,
    )
    assert out.startswith("ok ")
    assert "exit_code=0" in out
    assert "timed_out=false" in out
    assert "12345" in out


def test_run_shell_rejects_empty_and_escape(tmp_path: Path):
    assert "empty" in run_shell_safe("", root=tmp_path)
    assert "escapes" in run_shell_safe("echo x", working_directory="../x", root=tmp_path)


def test_run_shell_missing_cwd(tmp_path: Path):
    assert "does not exist" in run_shell_safe("echo x", working_directory="nope", root=tmp_path)


def test_run_shell_timeout(tmp_path: Path):
    out = run_shell_safe(
        'python -c "import time; time.sleep(5)"',
        root=tmp_path,
        timeout_sec=0.5,
    )
    assert out.startswith("ok ")
    assert "timed_out=true" in out


def test_run_shell_nonzero_exit(tmp_path: Path):
    out = run_shell_safe(
        'python -c "raise SystemExit(7)"',
        root=tmp_path,
        timeout_sec=30,
    )
    assert "exit_code=7" in out


def test_tool_and_loader(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        out = run_shell.invoke(
            {"command": 'python -c "print(99)"', "working_directory": "."}
        )
        assert out.startswith("ok ")
        assert "99" in out
    finally:
        get_settings.cache_clear()

    names = {t.name for t in load_agent_tools(Settings(mcp_enabled=False))}
    assert "run_shell" in names
