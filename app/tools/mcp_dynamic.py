"""CE-4：MCP 名录静态 + schema/调用按需；含串行批调用 mcp_call_many。"""

from __future__ import annotations

import json
from typing import Any, Protocol

from langchain_core.tools import StructuredTool

from app.tools.mcp_client import McpToolInfo

_RESERVED = frozenset(
    {"terminate", "doTerminate", "list_dir", "read_file", "grep", "semantic_search"}
)


class SupportsMcpGateway(Protocol):
    def list_tools(self) -> list[McpToolInfo]: ...

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str: ...


def call_mcp_many_serial(
    client: SupportsMcpGateway,
    calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    串行执行多笔 MCP 调用（for 循环）。

    每项形如 ``{"name": "add", "arguments": {"a": 1, "b": 2}}``。
    网关并行化后可在此替换实现（见待办 MCP-PAR），调用方接口保持不变。
    """
    results: list[dict[str, Any]] = []
    for i, item in enumerate(calls):
        name = str((item or {}).get("name") or "")
        args = (item or {}).get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            results.append(
                {"index": i, "name": name, "ok": False, "error": "arguments must be object"}
            )
            continue
        if not name:
            results.append({"index": i, "name": name, "ok": False, "error": "missing name"})
            continue
        if name in _RESERVED:
            results.append(
                {"index": i, "name": name, "ok": False, "error": "reserved local tool name"}
            )
            continue
        try:
            text = client.call_tool(name, args)
            results.append({"index": i, "name": name, "ok": True, "result": text})
        except Exception as exc:  # noqa: BLE001
            results.append({"index": i, "name": name, "ok": False, "error": str(exc)})
    return results


def make_mcp_dynamic_tools(client: SupportsMcpGateway) -> list[StructuredTool]:
    """
    元工具：
    - mcp_list_tools / mcp_tool_schema / mcp_call
    - mcp_call_many：传入 JSON 列表，**当前 for 循环串行**（并行见 MCP-PAR）
    """
    cache: dict[str, McpToolInfo] = {}

    def _refresh() -> dict[str, McpToolInfo]:
        cache.clear()
        for info in client.list_tools():
            if info.name in _RESERVED:
                continue
            cache[info.name] = info
        return cache

    def mcp_list_tools() -> str:
        """List MCP gateway tools: names and short descriptions only (no parameter schemas)."""
        infos = _refresh()
        if not infos:
            return "MCP catalog: (empty)"
        lines = [f"- {name}: {info.description}" for name, info in sorted(infos.items())]
        return "MCP catalog (names only; use mcp_tool_schema before mcp_call):\n" + "\n".join(lines)

    def mcp_tool_schema(name: str) -> str:
        """Load full JSON parameter schema for one MCP tool. Call this before mcp_call if needed."""
        if not cache:
            _refresh()
        if name not in cache:
            _refresh()
        if name not in cache:
            return f"error: unknown MCP tool: {name}"
        info = cache[name]
        payload = {
            "name": info.name,
            "description": info.description,
            "input_schema": info.input_schema,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def mcp_call(name: str, arguments_json: str = "{}") -> str:
        """Call an MCP gateway tool. arguments_json must be a JSON object matching mcp_tool_schema."""
        try:
            args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return f"error: invalid arguments_json: {exc}"
        if not isinstance(args, dict):
            return "error: arguments_json must be a JSON object"
        if name in _RESERVED:
            return f"error: reserved local tool name: {name}"
        if not cache:
            _refresh()
        return client.call_tool(name, args)

    def mcp_call_many(calls_json: str) -> str:
        """Call multiple MCP tools from a JSON list, sequentially (for-loop). Parallel later (MCP-PAR).

        calls_json example:
        [{"name":"add","arguments":{"a":1,"b":2}},{"name":"echo","arguments":{"text":"hi"}}]
        """
        try:
            calls = json.loads(calls_json or "[]")
        except json.JSONDecodeError as exc:
            return f"error: invalid calls_json: {exc}"
        if not isinstance(calls, list):
            return "error: calls_json must be a JSON array"
        if not cache:
            _refresh()
        results = call_mcp_many_serial(client, calls)
        return json.dumps(
            {"mode": "serial", "count": len(results), "results": results},
            ensure_ascii=False,
            indent=2,
        )

    return [
        StructuredTool.from_function(
            func=mcp_list_tools,
            name="mcp_list_tools",
            description=mcp_list_tools.__doc__ or "List MCP tools",
        ),
        StructuredTool.from_function(
            func=mcp_tool_schema,
            name="mcp_tool_schema",
            description=mcp_tool_schema.__doc__ or "Get MCP tool schema",
        ),
        StructuredTool.from_function(
            func=mcp_call,
            name="mcp_call",
            description=mcp_call.__doc__ or "Call MCP tool",
        ),
        StructuredTool.from_function(
            func=mcp_call_many,
            name="mcp_call_many",
            description=mcp_call_many.__doc__ or "Call many MCP tools serially",
        ),
    ]
