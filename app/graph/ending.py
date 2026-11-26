"""结束策略纯函数：事件点写入 status / end_reason；路由只问 should_end。

终态：
- completed：成功结束
- abandoned：正常放弃
- budget_exceeded：资源耗尽（步数/日后 token）
- cancelled：用户取消（预留，本阶段无生产触发）
"""

from __future__ import annotations

from typing import Any, Literal

TerminalStatus = Literal[
    "completed",
    "abandoned",
    "budget_exceeded",
    "cancelled",
]

# 含运行中与兼容旧值
Status = Literal[
    "running",
    "completed",
    "abandoned",
    "budget_exceeded",
    "cancelled",
    "finished",  # legacy ≈ completed
    "error",  # legacy ≈ budget_exceeded / fault
]

TERMINAL: frozenset[str] = frozenset(
    {
        "completed",
        "abandoned",
        "budget_exceeded",
        "cancelled",
        "finished",
        "error",
    }
)


def should_end(state: dict[str, Any]) -> bool:
    """路由用：是否应进入 summarize。"""
    return str(state.get("status") or "") in TERMINAL


def on_terminate(*, outcome: str = "success", reason: str = "task completed") -> dict[str, str]:
    """tools 见到 terminate 时调用。"""
    normalized = (outcome or "success").strip().lower()
    text = (reason or "").strip() or "task completed"
    if normalized in {"abandon", "abandoned", "give_up", "failed_task"}:
        return {
            "status": "abandoned",
            "end_reason": text,
        }
    return {
        "status": "completed",
        "end_reason": text,
    }


def on_text_only_finish(*, thought: str = "") -> dict[str, str]:
    """reason 无 tool_calls：视为成功给出文本答复。"""
    snippet = (thought or "").strip()
    return {
        "status": "completed",
        "end_reason": snippet[:200] if snippet else "text reply without tools",
    }


def on_budget_exceeded(*, step: int, max_steps: int) -> dict[str, str]:
    """步数（或日后 token）打满。"""
    return {
        "status": "budget_exceeded",
        "end_reason": f"exceeded max_steps={max_steps} (step={step})",
    }


def on_cancelled(*, reason: str = "user cancelled") -> dict[str, str]:
    """预留：用户主动停止。本阶段无图内触发。"""
    return {
        "status": "cancelled",
        "end_reason": (reason or "user cancelled").strip(),
    }


def parse_terminate_from_tool_content(content: str) -> tuple[str, str] | None:
    """解析 terminate 工具返回：terminated:outcome=...:reason=..."""
    text = str(content or "")
    if not text.startswith("terminated:"):
        return None
    rest = text[len("terminated:") :]
    outcome = "success"
    reason = rest
    if rest.startswith("outcome="):
        # outcome=success:reason=foo
        body = rest[len("outcome=") :]
        if ":reason=" in body:
            outcome, reason = body.split(":reason=", 1)
        else:
            outcome, reason = body, "task completed"
    return outcome.strip() or "success", reason.strip() or "task completed"
