"""CE-3：长工具结果本机落盘，短结果原样返回（不分片、不自动删）。"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path

from app.config import Settings, get_settings
from app.tools.path_sandbox import PathSandboxError, get_workspace_root

_SAFE_TOOL_NAME = re.compile(r"[^a-zA-Z0-9_-]+")


def maybe_persist_tool_result(
    tool_name: str,
    content: str | None,
    *,
    settings: Settings | None = None,
    root: Path | None = None,
    preview_chars: int = 500,
) -> str:
    """
    若 ``len(content) >= threshold``：写入 workspace 下 tool_output_dir，返回预览文案。
    否则原样返回。产物可手动删除；本模块不做自动 GC。
    """
    text = "" if content is None else str(content)
    s = settings or get_settings()
    threshold = int(s.tool_result_file_threshold)
    if len(text) < threshold:
        return text

    workspace = (root if root is not None else get_workspace_root(s)).resolve()
    rel_dir = (s.tool_output_dir or "artifacts/tool_outputs").strip().replace("\\", "/")
    out_dir = (workspace / rel_dir).resolve()
    try:
        out_dir.relative_to(workspace)
    except ValueError as exc:
        raise PathSandboxError(f"tool_output_dir escapes workspace: {rel_dir}") from exc

    out_dir.mkdir(parents=True, exist_ok=True)

    safe_tool = _SAFE_TOOL_NAME.sub("_", (tool_name or "tool")).strip("_")[:40] or "tool"
    short_id = uuid.uuid4().hex[:4]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{stamp}_{safe_tool}_{short_id}.txt"
    file_path = out_dir / filename
    file_path.write_text(text, encoding="utf-8")

    rel_path = file_path.relative_to(workspace).as_posix()
    preview = text[: max(0, int(preview_chars))]
    return (
        "[tool_result_persisted]\n"
        f"tool={tool_name}\n"
        f"chars={len(text)}\n"
        f"path={rel_path}\n"
        "preview:\n"
        f"{preview}\n"
        "hint: use read_file on path for full content"
    )
