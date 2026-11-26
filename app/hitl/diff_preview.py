"""
CA-6 S2：批准前的「提案」——diff / preview（仍不写盘、不 interrupt）。

==============================================================================
和 S1 / S3 / S4 怎么分工？（对应你问的理解）
------------------------------------------------------------------------------
- S1 policy：这个工具「要不要批」（allow / approve / deny）
- **S2 本文件**：若要批，**先算出给人看的材料**（旧内容 vs 新内容、命令原文）
  以及「人点批准之后」真正落盘的函数。**这里还不挂前端、不暂停图。**
- S3：用 LangGraph ``interrupt`` 把提案抛给前端，等 approve/reject
- S4：/stream 画出 diff，按钮调 resume

所以：你说的「前端先展示再问要不要改」= S2 出材料 + S3/S4 做人机闸。
S2 单独可单测：给定 path/content，断言 diff 文本长什么样。
==============================================================================
"""

from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from app.config import Settings, get_settings
from app.hitl.policy import HitlDecision, HitlVerdict, classify_tool_call
from app.tools.fs_write import str_replace_safe, write_text_safe
from app.tools.path_sandbox import PathSandboxError, resolve_safe
from app.tools.shell_tools import run_shell_safe


@dataclass
class HitlProposal:
    """
    一次待审批动作的完整描述（之后会原样放进 interrupt / SSE）。

    字段说明（学习用）：
    - tool / args：模型原来想调什么（批准后按原样执行）
    - verdict：S1 策略结论（通常已是 need_approve；hard_deny 也可带上说明）
    - path / command：方便前端标题栏展示
    - before_text / after_text：写文件类的旧/新全文（可能截断）
    - diff_text：unified diff，给人扫一眼
    - preview_text：新文件或 shell 的短预览
    - error：提案阶段就失败（路径非法等）——此时不应进入「批准写盘」
    """

    tool: str
    args: dict[str, Any]
    verdict: HitlVerdict
    path: str = ""
    command: str = ""
    before_text: str = ""
    after_text: str = ""
    diff_text: str = ""
    preview_text: str = ""
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转成可 JSON 序列化的字典（SSE / interrupt payload）。"""
        d = asdict(self)
        # Enum → 字符串；HitlVerdict 已在 asdict 里拆开
        if isinstance(self.verdict, HitlVerdict):
            d["verdict"] = {
                "decision": self.verdict.decision.value,
                "reason": self.verdict.reason,
                "risk": self.verdict.risk,
            }
        return d


# 预览/diff 过长时截断，避免 SSE 爆炸（完整内容批准后仍按 args 写盘）
_MAX_TEXT_CHARS = 12_000
_MAX_DIFF_CHARS = 16_000


def _clip(text: str, limit: int = _MAX_TEXT_CHARS) -> str:
    """截断长文本并标注。"""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…(truncated)…"


def _read_text_if_exists(path: str, *, root: Path | None, settings: Settings | None) -> tuple[str, str]:
    """
    读工作区内已有文件文本。

    返回 (text, error)；文件不存在则 text=\"\" 且 error=\"\"（表示新建）。
    """
    try:
        target = resolve_safe(path, root=root, settings=settings)
    except PathSandboxError as exc:
        return "", f"error: {exc}"
    if not target.exists():
        return "", ""
    if target.is_dir():
        return "", f"error: path is a directory: {path}"
    try:
        return target.read_text(encoding="utf-8"), ""
    except UnicodeDecodeError:
        return "", f"error: not a UTF-8 text file: {path}"
    except OSError as exc:
        return "", f"error: read failed: {exc}"


def build_unified_diff(before: str, after: str, *, path: str = "file") -> str:
    """
    用标准库 difflib 生成 unified diff（带 - / + 行）。

    这就是「给人看旧→新」的核心；Cursor 也是先算 diff 再让你确认。
    """
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    # 若最后一行没有换行，splitlines(keepends=True) 仍可用；统一补换行便于 diff
    if before and not before.endswith("\n"):
        before_lines = before.splitlines(keepends=True) or [before]
    diff_iter = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    text = "\n".join(diff_iter)
    return _clip(text, _MAX_DIFF_CHARS)


def _simulate_str_replace(before: str, old: str, new: str, *, replace_all: bool) -> tuple[str, str]:
    """
    在内存里模拟 str_replace，不写盘。

    返回 (after_text, error)；error 非空表示参数不合法（与 str_replace_safe 语义对齐的简化版）。
    """
    if not old:
        return before, "error: old must be non-empty"
    count = before.count(old)
    if count == 0:
        return before, "error: old text not found"
    if not replace_all and count != 1:
        return before, f"error: old occurs {count} times (need replace_all=true or unique old)"
    if replace_all:
        return before.replace(old, new), ""
    return before.replace(old, new, 1), ""


def build_hitl_proposal(
    tool_name: str,
    args: Mapping[str, Any] | None = None,
    *,
    root: Path | None = None,
    settings: Settings | None = None,
    hitl_enabled: bool | None = None,
) -> HitlProposal:
    """
    根据 tool_name + args 生成审批提案（**不执行副作用**）。

    流程：
    1. 先跑 S1 ``classify_tool_call``
    2. 若是写文件：读旧文件 → 算 after → 生成 diff/preview
    3. 若是 shell：只附带命令原文预览
    4. hard_deny / 参数错误时填 error，供上层直接回喂模型
    """
    s = settings or get_settings()
    enabled = s.hitl_enabled if hitl_enabled is None else hitl_enabled
    name = (tool_name or "").strip()
    raw_args = dict(args or {})
    verdict = classify_tool_call(name, raw_args, hitl_enabled=enabled)

    proposal = HitlProposal(tool=name, args=raw_args, verdict=verdict)

    if verdict.decision == HitlDecision.HARD_DENY:
        proposal.error = verdict.reason
        proposal.preview_text = verdict.reason
        return proposal

    if name in {"write_file", "str_replace"}:
        path = str(raw_args.get("path") or "").strip()
        proposal.path = path
        if not path:
            proposal.error = "error: path is empty"
            return proposal

        before, read_err = _read_text_if_exists(path, root=root, settings=s)
        if read_err:
            proposal.error = read_err
            return proposal
        proposal.before_text = _clip(before)

        if name == "write_file":
            after = raw_args.get("content")
            if not isinstance(after, str):
                proposal.error = "error: content must be str"
                return proposal
            proposal.after_text = _clip(after)
            if before == "":
                # 新建文件：没有旧内容，用 preview 展示将写入的正文
                proposal.preview_text = _clip(after, 2000)
                proposal.diff_text = f"(new file) {path}\n--- /dev/null\n+++ b/{path}\n"
            else:
                proposal.diff_text = build_unified_diff(before, after, path=path)
                proposal.preview_text = proposal.diff_text[:2000]
            return proposal

        # str_replace
        old = raw_args.get("old")
        new = raw_args.get("new")
        replace_all = bool(raw_args.get("replace_all", False))
        if not isinstance(old, str) or not isinstance(new, str):
            proposal.error = "error: old/new must be str"
            return proposal
        if before == "":
            proposal.error = f"error: file not found for str_replace: {path}"
            return proposal
        after, sim_err = _simulate_str_replace(
            before, old, new, replace_all=replace_all
        )
        if sim_err:
            proposal.error = sim_err
            return proposal
        proposal.after_text = _clip(after)
        proposal.diff_text = build_unified_diff(before, after, path=path)
        proposal.preview_text = proposal.diff_text[:2000]
        return proposal

    if name == "run_shell":
        command = str(
            raw_args.get("command")
            or raw_args.get("cmd")
            or raw_args.get("shell")
            or ""
        ).strip()
        proposal.command = command
        proposal.preview_text = command
        proposal.meta["working_directory"] = raw_args.get("working_directory") or "."
        return proposal

    # 其它 need_approve（如 mcp_call）：只带 args 摘要
    proposal.preview_text = _clip(str(raw_args), 1500)
    return proposal


def apply_approved_tool(
    tool_name: str,
    args: Mapping[str, Any] | None = None,
    *,
    root: Path | None = None,
    settings: Settings | None = None,
) -> str:
    """
    人已经批准之后：真正执行写盘 / shell。

    学习点：S2 把「算提案」和「执行」分成两个函数——
    S3 在 interrupt 回来后只应调用本函数，避免没批准就写盘。
    """
    name = (tool_name or "").strip()
    raw = dict(args or {})
    if name == "write_file":
        return write_text_safe(
            str(raw.get("path") or ""),
            str(raw.get("content") or ""),
            root=root,
            settings=settings,
        )
    if name == "str_replace":
        return str_replace_safe(
            str(raw.get("path") or ""),
            str(raw.get("old") or ""),
            str(raw.get("new") or ""),
            replace_all=bool(raw.get("replace_all", False)),
            root=root,
            settings=settings,
        )
    if name == "run_shell":
        cmd = str(raw.get("command") or raw.get("cmd") or "")
        cwd = str(raw.get("working_directory") or ".")
        # 与 Agent 工具同一套安全执行；返回 ok/error 多行文本
        return run_shell_safe(cmd, working_directory=cwd, root=root, settings=settings)
    return f"error: apply_approved_tool does not support {name!r}"
