"""离线/演示用本地工具；MCP 关闭时与 terminate 一起交给图使用。"""

from langchain_core.tools import tool


@tool
def terminate(reason: str = "task completed", outcome: str = "success") -> str:
    """End the agent loop when the task is finished or should stop.

    Args:
        reason: Why the agent is stopping (success summary or abandon explanation).
        outcome: "success" when the task is done; "abandon" when it cannot be completed.
    """
    normalized = (outcome or "success").strip().lower() or "success"
    text = (reason or "task completed").strip() or "task completed"
    return f"terminated:outcome={normalized}:reason={text}"


@tool
def add(a: float, b: float) -> str:
    """Add two numbers and return the sum as text.

    Args:
        a: First number.
        b: Second number.
    """
    return str(a + b)


@tool
def echo(text: str) -> str:
    """Echo the input text back.

    Args:
        text: Text to echo.
    """
    return text


def get_phase1_tools() -> list:
    """阶段 1 默认工具集（含 terminate）。"""
    return [terminate, add, echo]
