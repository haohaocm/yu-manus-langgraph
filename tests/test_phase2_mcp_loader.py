"""Phase 2 / CE-4: MCP dynamic catalog tools (fake client; no live gateway)."""

import json

from langchain_core.messages import AIMessage

from app.config import Settings
from app.manus import run_manus
from app.prompts import NEXT_STEP_PROMPT
from app.tools.loader import load_agent_tools
from app.tools.mcp_client import McpToolInfo
from tests.test_phase1_manus_graph import ScriptedChatModel


class FakeMcpClient:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.list_calls = 0

    def list_tools(self):
        self.list_calls += 1
        return [
            McpToolInfo(
                name="searchWeb",
                description="Search the web",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            )
        ]

    def call_tool(self, name: str, arguments: dict | None = None) -> str:
        self.calls.append((name, dict(arguments or {})))
        if name == "searchWeb":
            return "result: shanghai parks"
        return f"ok:{name}"


def test_load_tools_mcp_disabled_includes_helpers():
    s = Settings(mcp_enabled=False)
    names = {t.name for t in load_agent_tools(s)}
    assert "terminate" in names
    assert "add" in names
    assert "echo" in names
    assert "mcp_list_tools" not in names


def test_load_tools_mcp_enabled_uses_dynamic_meta_tools_only():
    s = Settings(mcp_enabled=True)
    fake = FakeMcpClient()
    tools = load_agent_tools(s, mcp_client=fake)  # type: ignore[arg-type]
    names = {t.name for t in tools}
    assert "terminate" in names
    assert {"mcp_list_tools", "mcp_tool_schema", "mcp_call", "mcp_call_many"} <= names
    # CE-4：不再把网关业务工具整表 bind
    assert "searchWeb" not in names
    assert "add" not in names


def test_mcp_list_schema_call_flow():
    s = Settings(mcp_enabled=True)
    fake = FakeMcpClient()
    tools = {t.name: t for t in load_agent_tools(s, mcp_client=fake)}  # type: ignore[arg-type]

    catalog = tools["mcp_list_tools"].invoke({})
    assert "searchWeb" in catalog
    assert "input_schema" not in catalog  # 名录不含完整 schema 字段名亦可；至少不该是整份 JSON schema 堆
    assert "query" not in catalog or "Search the web" in catalog

    schema_text = tools["mcp_tool_schema"].invoke({"name": "searchWeb"})
    schema = json.loads(schema_text)
    assert schema["name"] == "searchWeb"
    assert "query" in schema["input_schema"]["properties"]

    out = tools["mcp_call"].invoke(
        {"name": "searchWeb", "arguments_json": json.dumps({"query": "shanghai"})}
    )
    assert "shanghai parks" in out
    assert fake.calls[0] == ("searchWeb", {"query": "shanghai"})


def test_prompt_mentions_mcp_dynamic_flow():
    assert "mcp_list_tools" in NEXT_STEP_PROMPT
    assert "mcp_tool_schema" in NEXT_STEP_PROMPT
    assert "mcp_call" in NEXT_STEP_PROMPT


def test_manus_with_fake_mcp_dynamic_tools():
    s = Settings(mcp_enabled=True, max_steps=8)
    fake = FakeMcpClient()
    tools = load_agent_tools(s, mcp_client=fake)  # type: ignore[arg-type]
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="list mcp",
                tool_calls=[
                    {"name": "mcp_list_tools", "args": {}, "id": "c0", "type": "tool_call"}
                ],
            ),
            AIMessage(
                content="get schema",
                tool_calls=[
                    {
                        "name": "mcp_tool_schema",
                        "args": {"name": "searchWeb"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="call",
                tool_calls=[
                    {
                        "name": "mcp_call",
                        "args": {
                            "name": "searchWeb",
                            "arguments_json": '{"query":"shanghai"}',
                        },
                        "id": "c2",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="done",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {"reason": "ok", "outcome": "success"},
                        "id": "c3",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="检索结果：shanghai parks。"),
        ]
    )
    out = run_manus("找上海公园", model=model, max_steps=8, tools=tools)
    assert out["status"] == "completed"
    assert "shanghai parks" in out["answer"]
    logs = "\n".join(out["step_logs"])
    assert "mcp_list_tools" in logs
    assert "mcp_tool_schema" in logs
    assert "mcp_call" in logs
    assert "terminate" in logs
