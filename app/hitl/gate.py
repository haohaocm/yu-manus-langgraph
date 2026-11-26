"""
CA-6 S3：给「危险工具」包一层闸门——执行前 interrupt，批准后才真正副作用。

==============================================================================
拒绝之后会发生什么？（回答你的核心问题）
------------------------------------------------------------------------------
1. 人点「拒绝」→ ``Command(resume={decision: reject})`` 回到本包装函数
2. 包装函数**不调用** ``apply_approved_tool``，而是返回字符串：
   ``error: user rejected ...``
3. 该字符串成为 ToolMessage 内容，回到图里的 messages
4. 路由仍是 tools → reason：模型**看到拒绝原因**，可换路径、改参数或向用户说明
5. 大厂同理：拒绝 ≠ 整会话死亡，而是「工具失败可恢复」，由模型继续 ReAct

对比：当前若还没接本闸门，程序根本没有「拒绝」分支，工具会直接执行。

``build_hitl_proposal`` 只负责**生成提案**（diff 等），**不包含**点击批准/拒绝；
点击与 resume 在 API/前端（S4）+ 本文件的 ``interrupt`` 返回值里。
==============================================================================
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt

from app.config import Settings, get_settings
from app.hitl.diff_preview import apply_approved_tool, build_hitl_proposal
from app.hitl.policy import HitlDecision

# 需要走 HITL 包装的工具名（与 S0 写/跑策略对齐）
_HITL_WRAP_NAMES = frozenset({"write_file", "str_replace", "run_shell"})


def _normalize_resume(decision: Any) -> tuple[bool, str]:
    """把 resume 载荷收成 (approved, note)。"""
    if decision is True or decision == "approve":
        return True, ""
    if decision is False or decision == "reject":
        return False, ""
    if isinstance(decision, dict):
        raw = str(decision.get("decision") or "").strip().lower()
        note = str(decision.get("note") or "")
        return raw in {"approve", "approved", "yes", "ok"}, note
    return False, ""


def wrap_tool_with_hitl(tool: BaseTool, *, settings: Settings | None = None) -> BaseTool:
    """
    包装单个工具：need_approve 时 ``interrupt(提案)``；approve 后才副作用。

    若 HITL 关闭或工具不在包装名单，原样返回。
    """
    s = settings or get_settings()
    name = tool.name
    if not s.hitl_enabled or name not in _HITL_WRAP_NAMES:
        return tool

    description = tool.description or name
    args_schema = getattr(tool, "args_schema", None)

    def _run(**kwargs: Any) -> str:
        """
        实际被 ToolNode 调用的函数。

        步骤：提案 →（硬拒直接返回）→ interrupt 等人 → 批准则 apply / 拒绝则 error 字符串。
        """
        proposal = build_hitl_proposal(name, kwargs, settings=s)
        verdict = proposal.verdict

        if verdict.decision == HitlDecision.HARD_DENY:
            return f"error: hard_deny: {proposal.error or verdict.reason}"

        if verdict.decision == HitlDecision.ALLOW_AUTO:
            # 理论上写/跑不会走到这里；防御性直通
            return str(tool.invoke(kwargs))

        # need_approve：把提案抛给前端；图在此挂起直到 resume
        resumed = interrupt(proposal.to_dict())
        approved, note = _normalize_resume(resumed)
        if not approved:
            return (
                f"error: user rejected tool {name}."
                + (f" note={note}." if note else "")
                + " Please choose another approach or ask the user."
            )
        return apply_approved_tool(name, kwargs, settings=s)

    meta: dict[str, Any] = {
        "func": _run,
        "name": name,
        "description": description,
    }
    if args_schema is not None:
        meta["args_schema"] = args_schema
    return StructuredTool.from_function(**meta)


def wrap_tools_with_hitl(tools: list, *, settings: Settings | None = None) -> list:
    """对工具列表批量套 HITL 闸（只包装写/跑类）。"""
    s = settings or get_settings()
    return [wrap_tool_with_hitl(t, settings=s) for t in tools]
