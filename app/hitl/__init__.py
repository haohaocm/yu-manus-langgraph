"""
CA-6 HITL（Human-in-the-Loop，人在回路）包。

学习路径（建议按文件读）：
1. ``policy.py`` —— 不依赖 LLM：先判定「自动 / 要批 / 硬拒」（S1）
2. ``diff_preview.py`` —— 算出 diff/preview；批准后 ``apply_approved_tool`` 才写盘（S2）
3. （S3）interrupt/resume —— 图停住等前端点批准
4. （S4）API + /stream 按钮
"""

from app.hitl.diff_preview import (
    HitlProposal,
    apply_approved_tool,
    build_hitl_proposal,
    build_unified_diff,
)
from app.hitl.gate import wrap_tool_with_hitl, wrap_tools_with_hitl
from app.hitl.policy import (
    HitlDecision,
    HitlVerdict,
    classify_tool_call,
)

__all__ = [
    "HitlDecision",
    "HitlVerdict",
    "HitlProposal",
    "classify_tool_call",
    "build_hitl_proposal",
    "build_unified_diff",
    "apply_approved_tool",
    "wrap_tool_with_hitl",
    "wrap_tools_with_hitl",
]
