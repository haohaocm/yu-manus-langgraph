"""
MCP 网关客户端（Streamable HTTP）。

职责对齐 Java yu-ai-agent 的 McpGatewayClient：
list_tools / call_tool；调用方标识走 X-Caller-Id。
对外提供同步 API，内部用 asyncio（必要时丢到线程池，避免与 FastAPI 事件循环冲突）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.config import Settings, get_settings


@dataclass
class McpToolInfo:
    """网关工具元数据，供 loader 转成 LangChain StructuredTool。"""

    name: str
    description: str
    input_schema: dict[str, Any]


class McpGatewayClient:
    """连接 mcp-gateway，列出并调用远程工具。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def list_tools(self) -> list[McpToolInfo]:
        return self._run(self._list_tools_async())

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        return self._run(self._call_tool_async(name, arguments or {}))

    def _run(self, coro):
        """在无运行中 loop 时直接 asyncio.run；已有 loop（如 uvicorn）则放到线程里跑。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    async def _with_session(self, fn):
        headers = {"X-Caller-Id": self.settings.mcp_caller_id}
        async with httpx2.AsyncClient(headers=headers, timeout=60.0) as http:
            async with streamable_http_client(
                self.settings.mcp_gateway_url,
                http_client=http,
            ) as streams:
                # TransportStreams = (read_stream, write_stream)
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session)

    async def _list_tools_async(self) -> list[McpToolInfo]:
        async def _inner(session: ClientSession):
            result = await session.list_tools()
            tools = []
            for t in result.tools:
                schema = t.inputSchema if hasattr(t, "inputSchema") else getattr(t, "input_schema", None)
                if schema is None:
                    schema = {"type": "object", "properties": {}}
                elif hasattr(schema, "model_dump"):
                    schema = schema.model_dump(by_alias=True, exclude_none=True)
                elif not isinstance(schema, dict):
                    schema = {"type": "object", "properties": {}}
                tools.append(
                    McpToolInfo(
                        name=t.name,
                        description=t.description or t.name,
                        input_schema=schema,
                    )
                )
            return tools

        return await self._with_session(_inner)

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> str:
        async def _inner(session: ClientSession):
            result = await session.call_tool(name, arguments)
            texts: list[str] = []
            content = getattr(result, "content", None) or []
            for block in content:
                text = getattr(block, "text", None)
                if text:
                    texts.append(text)
                else:
                    texts.append(str(block))
            joined = "\n".join(texts).strip()
            is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
            if is_error:
                return f"Error calling tool {name}: {joined or '(unknown)'}"
            return joined or "(empty tool result)"

        return await self._with_session(_inner)
