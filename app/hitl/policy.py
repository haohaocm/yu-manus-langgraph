"""
CA-6 S1：HITL 策略引擎（纯规则，不调用大模型）。

==============================================================================
为什么先有 policy，而不是一上来写 interrupt？
------------------------------------------------------------------------------
HITL 编程可以想成两段：

1) **判定（本文件）**：这个 tool_call 危险吗？要不要停下来问人？
2) **闸门（S3）**：若要问人，就用 LangGraph ``interrupt`` 把图挂起；
   人点批准后再真正执行写盘/shell。

先把 (1) 做成可单测的纯函数，后面接 (2) 时不会把「什么算危险」
和「怎么暂停图」缠在一起——这也是 Cursor / 大厂 Agent 常见拆法：
规则闸 + 人机确认 UI，而不是让模型自己说「我危险吗」。

三种结论（``HitlDecision``）：
- ``allow_auto``：直接执行（只读工具等）
- ``need_approve``：必须人工确认后才执行（写文件、普通 shell）
- ``hard_deny``：连审批页都不给，直接拒绝（毁灭性命令）

S0 拍板（摘要）：写文件一律要批；shell 黑名单硬拒、其余要批；只读自动。
==============================================================================
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class HitlDecision(str, Enum):
    """单次 tool_call 的策略结论（字符串枚举，便于 JSON/SSE 序列化）。"""

    ALLOW_AUTO = "allow_auto"
    NEED_APPROVE = "need_approve"
    HARD_DENY = "hard_deny"


@dataclass(frozen=True)
class HitlVerdict:
    """
    策略引擎的完整输出。

    - decision：三选一结论
    - reason：给人/给日志看的短说明（拒绝时也应回喂模型）
    - risk：粗分风险标签，方便前端着色（write / shell / blocked / none）
    """

    decision: HitlDecision
    reason: str
    risk: str = "none"


# ---------------------------------------------------------------------------
# 工具名集合：按「意图」分组，而不是按实现文件
# ---------------------------------------------------------------------------

# 只读：不改磁盘、不跑任意命令 → 自动放行
_READONLY_TOOLS = frozenset(
    {
        "read_file",
        "list_dir",
        "grep",
        "semantic_search",
        "mcp_list_tools",
        "mcp_tool_schema",
    }
)

# 写盘：一律人工确认（S0）
_WRITE_TOOLS = frozenset({"write_file", "str_replace"})

# 终端：默认要批；命中黑名单则硬拒
_SHELL_TOOLS = frozenset({"run_shell"})

# 本地小工具 / 结束：不涉及用户工程破坏 → 自动
_CONTROL_TOOLS = frozenset({"terminate", "add", "echo"})

# MCP 动态调用：MVP 一律要批（远程副作用未知；比误放行更安全）
_MCP_MUTATING_TOOLS = frozenset({"mcp_call", "mcp_call_many"})


# ---------------------------------------------------------------------------
# shell 黑名单：子串/正则命中即 hard_deny
# 说明：这是「故意简化」的启发式，防不住所有绕过；目标是挡住常见误操作。
# ---------------------------------------------------------------------------

# 不区分大小写的子串（命令行里出现即拒）
_SHELL_DENY_SUBSTRINGS: tuple[str, ...] = (
    "rm -rf",
    "rm -fr",
    "mkfs",
    "shutdown",
    "reboot",
    "poweroff",
    "dd if=",
    ":(){",  # fork bomb 开头
    "format ",
    "format.com",
    "del /f /s /q",
    "rd /s /q",
    "rmdir /s",
    "remove-item -recurse",
    "ri -recurse",
    "curl | sh",
    "curl|sh",
    "wget | sh",
    "wget|sh",
    "invoke-expression",
    "iex(",
)

# 额外正则（例如重定向写敏感路径）
_SHELL_DENY_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r">\s*/etc/", re.I),
    re.compile(r">\s*/boot/", re.I),
    re.compile(r"chmod\s+-R\s+777\s+/", re.I),
)


def _shell_command_text(args: Mapping[str, Any] | None) -> str:
    """从 run_shell 参数里取出命令字符串（兼容 command / cmd 字段名）。"""
    if not args:
        return ""
    for key in ("command", "cmd", "shell"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _match_shell_blacklist(command: str) -> str | None:
    """
    若命令命中黑名单，返回命中说明；否则 None。

    学习点：硬拒绝放在「人审批」之前——有些命令不应出现在「点一下就执行」的选项里。
    """
    if not command:
        return None
    lowered = command.lower()
    for frag in _SHELL_DENY_SUBSTRINGS:
        if frag.lower() in lowered:
            return f"shell blacklist hit: contains {frag!r}"
    for pat in _SHELL_DENY_REGEXES:
        if pat.search(command):
            return f"shell blacklist hit: pattern {pat.pattern!r}"
    return None


def classify_tool_call(
    tool_name: str,
    args: Mapping[str, Any] | None = None,
    *,
    hitl_enabled: bool = True,
) -> HitlVerdict:
    """
    判定一次工具调用是否自动执行、需要人工批准、或硬拒绝。

    参数：
        tool_name: 模型要调用的工具名（如 ``write_file``）
        args: 工具参数字典（shell 需要读 ``command``；写文件 S1 只需名字）
        hitl_enabled: 总开关；False 时全部视为 ``allow_auto``（方便单测/回滚）

    返回：
        HitlVerdict（decision + reason + risk）

    副作用：无（纯函数）。真正的 interrupt / 写盘在后续 S2/S3。
    """
    name = (tool_name or "").strip()
    args = args or {}

    # 总开关关闭：整条 HITL 旁路，行为回到 CA-5 前「直接执行」
    if not hitl_enabled:
        return HitlVerdict(
            decision=HitlDecision.ALLOW_AUTO,
            reason="HITL disabled (HITL_ENABLED=false)",
            risk="none",
        )

    if not name:
        return HitlVerdict(
            decision=HitlDecision.HARD_DENY,
            reason="empty tool name",
            risk="blocked",
        )

    # --- 只读 / 控制类：自动 ---
    if name in _READONLY_TOOLS or name in _CONTROL_TOOLS:
        return HitlVerdict(
            decision=HitlDecision.ALLOW_AUTO,
            reason=f"{name} is read-only or control; auto-run",
            risk="none",
        )

    # --- 写文件：一律要批 ---
    if name in _WRITE_TOOLS:
        path = str(args.get("path") or "")
        return HitlVerdict(
            decision=HitlDecision.NEED_APPROVE,
            reason=f"write tool {name} requires approval"
            + (f" (path={path})" if path else ""),
            risk="write",
        )

    # --- shell：先黑名单，再默认要批 ---
    if name in _SHELL_TOOLS:
        command = _shell_command_text(args)
        hit = _match_shell_blacklist(command)
        if hit:
            return HitlVerdict(
                decision=HitlDecision.HARD_DENY,
                reason=hit,
                risk="blocked",
            )
        return HitlVerdict(
            decision=HitlDecision.NEED_APPROVE,
            reason="run_shell requires approval"
            + (f": {command[:120]}" if command else ""),
            risk="shell",
        )

    # --- MCP 有副作用调用：MVP 要批 ---
    if name in _MCP_MUTATING_TOOLS:
        return HitlVerdict(
            decision=HitlDecision.NEED_APPROVE,
            reason=f"{name} may have remote side effects; requires approval",
            risk="shell",
        )

    # --- 未知工具：宁可要批，也不默默自动跑 ---
    return HitlVerdict(
        decision=HitlDecision.NEED_APPROVE,
        reason=f"unknown tool {name!r}; default to approval",
        risk="shell",
    )
