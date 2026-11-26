"""组装 Agent 可用工具列表：本地 terminate + FS +（可选）MCP 动态名录；CE-3 落盘包装。"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, create_model

from app.config import Settings, get_settings
from app.tools.fs_tools import grep, list_dir, read_file
from app.tools.fs_write import str_replace, write_file
from app.tools.local_tools import add, echo, terminate
from app.tools.shell_tools import run_shell
from app.tools.mcp_client import McpGatewayClient
from app.tools.mcp_dynamic import make_mcp_dynamic_tools
from app.tools.search_tools import semantic_search
from app.hitl.gate import wrap_tools_with_hitl
from app.tools.tool_result_store import maybe_persist_tool_result

_JSON_TYPE = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def load_agent_tools(
    settings: Settings | None = None,
    *,
    mcp_client: McpGatewayClient | None = None,
    include_phase1_helpers: bool = True,
    persist_long_results: bool = True,
) -> list:
    """
    Always include local ``terminate`` + FS 读/写 + ``semantic_search``。

    - mcp_enabled=True（CE-4）：只挂 ``mcp_list_tools`` / ``mcp_tool_schema`` / ``mcp_call``，
      不再把每个网关工具的完整 schema bind 给模型。
    - 否则：附加本地 add/echo。
    - CE-3：可选对返回值做长结果落盘包装。
    """
    s = settings or get_settings()
    tools: list = [
        terminate,
        list_dir,
        read_file,
        grep,
        write_file,
        str_replace,
        run_shell,
        semantic_search,
    ]

    if s.mcp_enabled:
        client = mcp_client or McpGatewayClient(s)
        tools.extend(make_mcp_dynamic_tools(client))
    elif include_phase1_helpers:
        tools.extend([add, echo])

    # CA-6：先套 HITL 闸（interrupt），再套长结果落盘，避免未批准就 persist
    if s.hitl_enabled:
        tools = wrap_tools_with_hitl(tools, settings=s)

    if persist_long_results:
        tools = [wrap_tool_with_persistence(t, settings=s) for t in tools]
    return tools


def wrap_tool_with_persistence(tool: BaseTool, *, settings: Settings | None = None) -> StructuredTool:
    """包装任意 LangChain Tool：调用后对返回字符串做 maybe_persist。"""
    s = settings or get_settings()
    tool_name = tool.name
    description = tool.description or tool_name
    args_schema = getattr(tool, "args_schema", None)

    def _run(**kwargs: Any) -> str:
        raw = tool.invoke(kwargs)
        return maybe_persist_tool_result(tool_name, raw, settings=s)

    kwargs: dict[str, Any] = {
        "func": _run,
        "name": tool_name,
        "description": description,
    }
    if args_schema is not None:
        kwargs["args_schema"] = args_schema
    return StructuredTool.from_function(**kwargs)


def _json_schema_to_args_model(tool_name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """保留给旧测试/调试用：把 JSON Schema 转成 Pydantic 模型。"""
    props = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])
    fields: dict[str, Any] = {}
    for key, prop in props.items():
        prop = prop or {}
        typ = _JSON_TYPE.get(prop.get("type", "string"), Any)
        desc = prop.get("description") or key
        if key in required:
            fields[key] = (typ, Field(description=desc))
        else:
            fields[key] = (Optional[typ], Field(default=None, description=desc))
    if not fields:
        return create_model(f"{tool_name}_Args")
    return create_model(f"{tool_name}_Args", **fields)
