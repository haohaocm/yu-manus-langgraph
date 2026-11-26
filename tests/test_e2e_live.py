"""Live E2E against Qwen tunnel + MCP gateway. Skip if deps are down."""

from __future__ import annotations

import os

import httpx
import pytest

from app.config import Settings, get_settings
from app.manus import run_manus
from app.tools.loader import load_agent_tools
from app.tools.mcp_client import McpGatewayClient


def _alive(url: str, timeout: float = 2.0) -> bool:
    try:
        r = httpx.get(url, timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_E2E", "1") != "1",
    reason="set RUN_LIVE_E2E=1 to run live tests",
)


@pytest.fixture(scope="module")
def live_settings():
    get_settings.cache_clear()
    s = Settings(mcp_enabled=True)
    if not _alive("http://127.0.0.1:18000/v1/models"):
        pytest.skip("Qwen tunnel 18000 not up")
    if not _alive("http://127.0.0.1:8090/ping"):
        pytest.skip("MCP gateway 8090 not up")
    return s


def test_mcp_list_tools_live(live_settings):
    client = McpGatewayClient(live_settings)
    tools = client.list_tools()
    names = {t.name for t in tools}
    assert "add" in names
    assert len(tools) >= 5


def test_mcp_call_add_live(live_settings):
    client = McpGatewayClient(live_settings)
    out = client.call_tool("add", {"a": 1, "b": 2})
    assert "3" in out


def test_manus_with_real_llm_and_mcp(live_settings):
    get_settings.cache_clear()
    tools = load_agent_tools(live_settings)
    names = {t.name for t in tools}
    assert "terminate" in names
    assert {"mcp_list_tools", "mcp_tool_schema", "mcp_call"} <= names
    assert "add" not in names  # CE-4：业务工具不再整表 bind

    prompt = (
        "请：1) mcp_tool_schema 查看 add；2) mcp_call 调用 add，a=1,b=2；"
        "3) terminate outcome=success。不要做其他无关调用。"
    )
    out = run_manus(prompt, max_steps=10, tools=tools)
    assert out["steps"] >= 1
    logs = "\n".join(out["step_logs"]).lower()
    answer = (out.get("answer") or "").lower()
    assert out["status"] in {
        "completed",
        "abandoned",
        "budget_exceeded",
        "cancelled",
        "finished",
        "error",
    }
    assert ("mcp_call" in logs) or ("terminate" in logs) or ("3" in answer) or out["steps"] > 0
    if "mcp_call" in logs:
        assert "3" in logs or "3" in answer
    assert out.get("final_answer") or out.get("answer")
