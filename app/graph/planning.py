"""CA-3：是否需要 plan 的规则分流 + 计划文本解析（无额外 LLM 分类器）。"""

from __future__ import annotations

import json
import re

# 命中任一则走 plan 节点（MVP 启发式；完备分类见待办 PLAN-CLF）
_COMPLEX_RE = re.compile(
    "|".join(
        [
            r"实现",
            r"重构",
            r"修复",
            r"多文件",
            r"编写",
            r"改代码",
            r"修改代码",
            r"创建文件",
            r"写入文件",
            r"添加功能",
            r"写一个",
            r"apply[_\s-]?patch",
            r"\bimplement\b",
            r"\brefactor\b",
            r"\bfix\b",
            r"write_file",
            r"str_replace",
            r"run_shell",
        ]
    ),
    re.IGNORECASE,
)


def need_plan(user_message: str) -> bool:
    """规则判断是否需要显式规划；True → 进入 plan 节点。"""
    text = (user_message or "").strip()
    # 中文短句也可能复杂（如「请重构代码」仅数字符），阈值宜低
    if len(text) < 4:
        return False
    return bool(_COMPLEX_RE.search(text))


def parse_plan_output(raw: str) -> list[str]:
    """
    从模型输出解析步骤列表。

    支持：JSON ``{\"steps\":[...]}`` / 编号列表 / 行首 ``- ``。
    """
    text = (raw or "").strip()
    if not text:
        return []

    # 尝试抽取 JSON 对象
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if isinstance(data, dict):
                steps = data.get("steps")
                if isinstance(steps, list):
                    out = [str(s).strip() for s in steps if str(s).strip()]
                    if out:
                        return out[:12]
        except json.JSONDecodeError:
            pass

    steps: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(?:\d+[\.\)、]|\-|\*)\s*(.+)$", line)
        if m:
            steps.append(m.group(1).strip())
    return steps[:12]


def format_plan_context(
    *,
    plan: list[str] | None,
    plan_skipped: bool,
    plan_step_index: int = 0,
) -> str:
    """注入 reason 的计划上下文；无计划时返回空串。"""
    if plan_skipped or not plan:
        return ""
    lines = [
        "Current task plan (follow in order; do not ignore):",
        f"Suggested focus index (1-based hint, soft): {max(1, int(plan_step_index) + 1)} of {len(plan)}",
        "Progress is primarily inferred from prior tool results in this run; advance through steps logically.",
    ]
    for i, step in enumerate(plan, start=1):
        mark = "→" if i == max(1, int(plan_step_index) + 1) else " "
        lines.append(f"{mark} {i}. {step}")
    return "\n".join(lines)


def first_user_text(messages: list) -> str:
    """从图 messages 取首条用户问题（跳过 NEXT_STEP 等系统向 HumanMessage）。"""
    from app.prompts import NEXT_STEP_PROMPT

    for msg in messages:
        content = getattr(msg, "content", None)
        if content is None:
            continue
        # duck-type HumanMessage
        type_name = type(msg).__name__
        if type_name != "HumanMessage" and not getattr(msg, "type", "") == "human":
            continue
        text = str(content).strip()
        if not text or text == NEXT_STEP_PROMPT or text.startswith("Current task plan"):
            continue
        return text
    return ""
