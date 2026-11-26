"""LangGraph 共享状态：在 reason / tools / summarize 节点之间传递。"""

from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages


class ManusState(TypedDict):
    """一次 Manus 运行的图状态（对齐 Java BaseAgent 字段）。"""

    # 对话与工具消息；add_messages 表示节点返回的 messages 会追加而非整表覆盖
    messages: Annotated[list, add_messages]
    # 当前已执行的 reason 步数（从 1 递增）
    step: int
    # 最大步数，对应 Java maxStep
    max_steps: int
    # running：继续；其余为终态（见 app.graph.ending）
    # finished/error 为兼容旧值
    status: Literal[
        "running",
        "completed",
        "abandoned",
        "budget_exceeded",
        "cancelled",
        "finished",
        "error",
    ]
    # 人类可读轨迹（调试用），与面向用户的 final_answer 分离
    step_logs: list[str]
    # 总结器产出的最终用户答复
    final_answer: str
    # 结束原因（成功说明 / 放弃原因 / 超步说明等）
    end_reason: str
    # CA-3：规划（planning）；跳过时 plan 为空且 plan_skipped=True
    plan: list[str]
    plan_skipped: bool
    # 软进度提示（0-based）；MVP 不强制由代码自动推进，主要靠工具历史 + prompt
    plan_step_index: int
