"""
NOUS MCP Bridge — Γέφυρα MCP
=============================
Connects NOUS souls to any MCP (Model Context Protocol) server.
Supports SSE transport (remote servers) and stdio transport (local servers).

Usage in .nous:
    soul Agent {
        senses: [mcp_discover, mcp_call]
        instinct {
            let tools = sense mcp_discover(server: "https://mcp.example.com/sse")
            let result = sense mcp_call(
                server: "https://mcp.example.com/sse",
                tool: "search_files",
                args: {"query": "quarterly report"}
            )
        }
    }

Architecture:
    MCP Server (SSE) ←→ MCPClient ←→ mcp_call sense ←→ NOUS Soul
"""
from __future__ import annotations

import asyncio
import json
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger("nous.mcp")


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class MCPResult:
    content: list[dict[str, Any]]
    is_error: bool = False

    @property
    def text(self) -> str:
        parts: list[str] = []
        for block in self.content:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "resource":
                parts.append(json.dumps(block.get("resource", {})))
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "text": self.text,
            "is_error": self.is_error,
        }


class MCPClient:
    """JSON-RPC 2.0 over SSE client for MCP servers."""

    def __init__(self, server_url: str, timeout: float = 30.0) -> None:
        self._server_url: str = server_url
        self._timeout: float = timeout
        self._endpoint_url: Optional[str] = None
        self._session_id: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized: bool = False
        self._tools_cache: Optional[list[MCPTool]] = None

    async def connect(self) -> None:
        if self._initialized:
            return

        self._client = httpx.AsyncClient(timeout=self._timeout)

        endpoint_url = await self._discover_endpoint()
        if endpoint_url is None:
            raise ConnectionError(f"Failed to discover MCP endpoint from {self._server_url}")

        self._endpoint_url = endpoint_url
        await self._initialize_session()
        self._initialized = True
        logger.info("MCP connected: %s → %s", self._server_url, self._endpoint_url)

    async def _discover_endpoint(self) -> Optional[str]:
        try:
            async with self._client.stream("GET", self._server_url, headers={"Accept": "text/event-stream"}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        try:
                            msg = json.loads(data)
                            if "endpoint" in msg:
                                return msg["endpoint"]
                        except json.JSONDecodeError:
                            if data.startswith("http"):
                                return data
                    if line.startswith("event:") and "endpoint" in line:
                        continue
                    break
        except Exception as e:
            logger.warning("SSE discovery failed, trying direct endpoint: %s", e)
            base = self._server_url.rsplit("/", 1)[0]
            return f"{base}/message"

        return None

    async def _initialize_session(self) -> None:
        result = await self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "nous-mcp-bridge",
                "version": "1.0.0",
            },
        })
        if result and "serverInfo" in result:
            logger.info("MCP server: %s v%s",
                        result["serverInfo"].get("name", "unknown"),
                        result["serverInfo"].get("version", "unknown"))

        await self._rpc_notify("notifications/initialized", {})

    async def list_tools(self) -> list[MCPTool]:
        if self._tools_cache is not None:
            return self._tools_cache

        if not self._initialized:
            await self.connect()

        result = await self._rpc("tools/list", {})
        tools: list[MCPTool] = []
        if result and "tools" in result:
            for t in result["tools"]:
                tools.append(MCPTool(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                ))
        self._tools_cache = tools
        logger.info("MCP tools discovered: %d", len(tools))
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> MCPResult:
        if not self._initialized:
            await self.connect()

        result = await self._rpc("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })

        if result is None:
            return MCPResult(content=[{"type": "text", "text": "No response from MCP server"}], is_error=True)

        return MCPResult(
            content=result.get("content", []),
            is_error=result.get("isError", False),
        )

    async def _rpc(self, method: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        if self._client is None or self._endpoint_url is None:
            raise ConnectionError("MCP client not connected")

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            resp = await self._client.post(
                self._endpoint_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            body = resp.json()

            if "error" in body:
                err = body["error"]
                logger.error("MCP RPC error [%s]: %s", err.get("code"), err.get("message"))
                return None

            return body.get("result")

        except httpx.HTTPStatusError as e:
            logger.error("MCP HTTP error: %s %s", e.response.status_code, e.response.text[:200])
            return None
        except Exception as e:
            logger.error("MCP RPC failed: %s", e)
            return None

    async def _rpc_notify(self, method: str, params: dict[str, Any]) -> None:
        if self._client is None or self._endpoint_url is None:
            return

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            await self._client.post(
                self._endpoint_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except Exception:
            pass

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        self._tools_cache = None


class MCPRegistry:
    """Manages connections to multiple MCP servers."""

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}

    async def get_client(self, server_url: str, timeout: float = 30.0) -> MCPClient:
        if server_url not in self._clients:
            client = MCPClient(server_url, timeout=timeout)
            await client.connect()
            self._clients[server_url] = client
        return self._clients[server_url]

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients.clear()

    @property
    def connected_servers(self) -> list[str]:
        return list(self._clients.keys())


_registry = MCPRegistry()


async def mcp_discover(server: str, timeout: float = 30.0) -> dict[str, Any]:
    """Discover tools from an MCP server. Used as NOUS sense."""
    client = await _registry.get_client(server, timeout=timeout)
    tools = await client.list_tools()
    return {
        "ok": True,
        "server": server,
        "tool_count": len(tools),
        "tools": [t.to_dict() for t in tools],
    }


async def mcp_call(
    server: str,
    tool: str,
    args: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Call a tool on an MCP server. Used as NOUS sense."""
    client = await _registry.get_client(server, timeout=timeout)
    result = await client.call_tool(tool, args)
    return {
        "ok": not result.is_error,
        "text": result.text,
        "content": result.content,
        "is_error": result.is_error,
    }


async def mcp_close_all() -> None:
    """Cleanup all MCP connections."""
    await _registry.close_all()
