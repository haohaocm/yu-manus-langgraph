"""CA-3：need_plan / 解析 / 图接线 / prompt（假模型）。"""

from langchain_core.messages import AIMessage

from app.graph.planning import need_plan, parse_plan_output
from app.manus import run_manus
from app.prompts import NEXT_STEP_PROMPT, PLAN_PROMPT
from app.tools.local_tools import get_phase1_tools
from tests.test_phase1_manus_graph import ScriptedChatModel


def test_s4_prompt_follows_plan_keywords():
    assert "Current task plan" in NEXT_STEP_PROMPT
    assert "plan step" in NEXT_STEP_PROMPT.lower() or "plan steps" in NEXT_STEP_PROMPT.lower()
    assert "terminate" in NEXT_STEP_PROMPT
    assert "steps" in PLAN_PROMPT
    assert "JSON" in PLAN_PROMPT


def test_need_plan_rules():
    assert need_plan("实现一个写文件功能并跑测试") is True
    assert need_plan("请重构这段代码") is True
    assert need_plan("1+2等于几？") is False
    assert need_plan("PathSandboxError 在哪个文件？") is False


def test_parse_plan_json_and_list():
    assert parse_plan_output('{"steps":["读文件","改代码","跑测试"]}') == [
        "读文件",
        "改代码",
        "跑测试",
    ]
    assert parse_plan_output("1. a\n2. b\n3. c") == ["a", "b", "c"]
    assert parse_plan_output('{"steps":[]}') == []


def test_graph_skips_plan_for_simple_add():
    """简单题不进 plan，脚本响应与改图前一致。"""
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="add",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 1, "b": 2},
                        "id": "a1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="done",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"outcome": "success", "reason": "ok"},
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="结果是 3。"),
        ]
    )
    out = run_manus(
        "请计算 1+2，然后结束",
        model=model,
        max_steps=5,
        tools=get_phase1_tools(),
    )
    assert out["status"] == "completed"
    assert out["plan_skipped"] is True
    assert out["plan"] == []
    assert "plan :" not in "\n".join(out["step_logs"])


def test_graph_runs_plan_then_reason_for_complex():
    model = ScriptedChatModel(
        responses=[
            # plan 节点
            AIMessage(content='{"steps":["读现有代码","实现写文件","跑 pytest"]}'),
            # reason → add（占位工具）
            AIMessage(
                content="follow plan step1",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 2, "b": 3},
                        "id": "a1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="done",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"outcome": "success", "reason": "planned"},
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="已按计划完成。"),
        ]
    )
    out = run_manus(
        "请实现写文件功能并修复相关测试",
        model=model,
        max_steps=6,
        tools=get_phase1_tools(),
    )
    assert out["status"] == "completed"
    assert out["plan_skipped"] is False
    assert out["plan"] == ["读现有代码", "实现写文件", "跑 pytest"]
    logs = "\n".join(out["step_logs"])
    assert "plan :" in logs
    assert "terminate" in logs
