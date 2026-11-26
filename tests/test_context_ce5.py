"""CE-5：event log + 近窗投影；mcp_call_many 串行。"""

import json
import time
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.config import Settings
from app.context.events import (
    build_event_log_from_result,
    flush_event_log_sync,
    schedule_flush_events,
)
from app.context.project import project_messages
from app.manus import run_manus
from app.tools.loader import load_agent_tools
from app.tools.local_tools import get_phase1_tools
from app.tools.mcp_client import McpToolInfo
from app.tools.mcp_dynamic import call_mcp_many_serial
from tests.test_phase1_manus_graph import ScriptedChatModel


class FakeMcp:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self):
        return [
            McpToolInfo(
                name="add",
                description="add",
                input_schema={
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                },
            )
        ]

    def call_tool(self, name, arguments=None):
        self.calls.append((name, dict(arguments or {})))
        if name == "add":
            return str(float(arguments["a"]) + float(arguments["b"]))
        return "ok"


def test_project_keeps_first_user_and_last_turns():
    msgs = [HumanMessage(content="Q")]
    for i in range(8):
        msgs.append(AIMessage(content=f"t{i}", tool_calls=[]))
        msgs.append(ToolMessage(content=f"r{i}", tool_call_id=f"id{i}", name="echo"))
    # 上面 tool_calls=[] 仍算 AI 回合；简化：只用 AIMessage
    msgs = [HumanMessage(content="Q")] + [AIMessage(content=f"t{i}") for i in range(8)]
    out = project_messages(msgs, max_turns=5)
    assert isinstance(out[0], HumanMessage)
    assert out[0].content == "Q"
    assert len([m for m in out if isinstance(m, AIMessage)]) == 5
    assert out[-1].content == "t7"


def test_event_log_memory_and_sync_flush(tmp_path: Path):
    result = {
        "step_logs": ["step1 : hi", "summarize : bye"],
        "status": "completed",
        "end_reason": "ok",
        "step": 1,
        "final_answer": "bye",
    }
    log = build_event_log_from_result(user_prompt="hello", result=result)
    assert log.events[0]["type"] == "run_start"
    assert log.events[-1]["type"] == "run_end"
    path = flush_event_log_sync(log, directory=tmp_path)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "run_start" in text and "hello" in text


def test_schedule_flush_async(tmp_path: Path):
    log = build_event_log_from_result(
        user_prompt="x",
        result={"step_logs": [], "status": "completed", "step": 0, "final_answer": ""},
    )
    schedule_flush_events(log, directory=tmp_path)
    for _ in range(50):
        if list(tmp_path.glob("*.jsonl")):
            break
        time.sleep(0.05)
    assert list(tmp_path.glob("*.jsonl"))


def test_mcp_call_many_serial():
    fake = FakeMcp()
    out = call_mcp_many_serial(
        fake,
        [
            {"name": "add", "arguments": {"a": 1, "b": 2}},
            {"name": "add", "arguments": {"a": 3, "b": 4}},
        ],
    )
    assert out[0]["ok"] and out[0]["result"] == "3.0"
    assert out[1]["result"] == "7.0"
    assert len(fake.calls) == 2


def test_mcp_call_many_tool_exposed():
    tools = {
        t.name: t
        for t in load_agent_tools(
            Settings(mcp_enabled=True),
            mcp_client=FakeMcp(),  # type: ignore[arg-type]
            persist_long_results=False,
        )
    }
    assert "mcp_call_many" in tools
    raw = tools["mcp_call_many"].invoke(
        {
            "calls_json": json.dumps(
                [{"name": "add", "arguments": {"a": 2, "b": 3}}]
            )
        }
    )
    data = json.loads(raw)
    assert data["mode"] == "serial"
    assert data["results"][0]["result"] == "5.0"


def test_run_manus_returns_event_log():
    model = ScriptedChatModel(
        responses=[
            AIMessage(content="hi"),
            AIMessage(content="你好"),
        ]
    )
    out = run_manus(
        "ping",
        model=model,
        max_steps=2,
        tools=get_phase1_tools(),
        persist_event_log=False,
    )
    assert out["event_log"]
    assert out["run_id"]
    assert out["event_log"][0]["type"] == "run_start"
