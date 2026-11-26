"""CA-2：工作区内受控执行 shell 命令（纯函数 + Agent @tool）。

- ``run_shell_safe``：subprocess 捕获 stdout/stderr/exit；超时可中断
- cwd 经 ``resolve_safe``，默认工作区根
- 本阶段不做命令黑名单（HITL/硬闸见 CA-6）
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from langchain_core.tools import tool

from app.config import Settings, get_settings
from app.tools.path_sandbox import PathSandboxError, resolve_safe


def _timeout_sec(settings: Settings | None, override: float | None) -> float:
    if override is not None:
        return max(0.1, float(override))
    s = settings or get_settings()
    return max(0.1, float(getattr(s, "shell_timeout_sec", 60.0) or 60.0))


def _max_output_chars(settings: Settings | None, override: int | None) -> int:
    if override is not None:
        return max(256, int(override))
    s = settings or get_settings()
    return max(256, int(getattr(s, "shell_max_output_chars", 80_000) or 80_000))


def _clip(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n... truncated, max_chars={limit}", True


def run_shell_safe(
    command: str,
    *,
    working_directory: str = ".",
    root: Path | None = None,
    settings: Settings | None = None,
    timeout_sec: float | None = None,
    max_output_chars: int | None = None,
) -> str:
    """
    在沙箱 cwd 下执行 ``command``（``shell=True``）。

    返回多行文本：首行 ``ok`` 或 ``error:``，随后 exit_code / timed_out / 输出段。
    """
    cmd = (command or "").strip()
    if not cmd:
        return "error: command is empty"

    try:
        cwd = resolve_safe(working_directory or ".", root=root, settings=settings)
    except PathSandboxError as exc:
        return f"error: {exc}"

    if not cwd.exists():
        return f"error: working_directory does not exist: {working_directory}"
    if not cwd.is_dir():
        return f"error: working_directory is not a directory: {working_directory}"

    timeout = _timeout_sec(settings, timeout_sec)
    out_limit = _max_output_chars(settings, max_output_chars)
    timed_out = False
    exit_code = -1
    stdout = ""
    stderr = ""

    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        exit_code = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else (
            exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
        )
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else (
            exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        )
        stderr = (stderr + f"\n[timed out after {timeout}s]").strip()
    except OSError as exc:
        return f"error: cannot run command: {exc}"

    stdout, _ = _clip(stdout, out_limit)
    stderr, _ = _clip(stderr, out_limit)

    lines = [
        f"ok exit_code={exit_code} timed_out={str(timed_out).lower()} "
        f"cwd={working_directory} command={cmd!r}",
        "--- stdout ---",
        stdout if stdout else "(empty)",
        "--- stderr ---",
        stderr if stderr else "(empty)",
    ]
    return "\n".join(lines)


@tool
def run_shell(command: str, working_directory: str = ".") -> str:
    """Run a shell command inside the workspace (controlled: timeout + captured output).

    Args:
        command: Shell command string (e.g. ``python -m pytest tests/test_fs_write.py -q``).
        working_directory: Relative directory under workspace root (default ``.``).
    """
    return run_shell_safe(command, working_directory=working_directory)
