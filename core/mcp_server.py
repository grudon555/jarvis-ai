"""Jarvis MCP server — JSON-RPC 2.0 over stdio.

Compatible with Claude Desktop, VS Code Copilot, and any MCP-compliant client.
No external MCP SDK required (protocol implemented directly).

Protocol reference: https://spec.modelcontextprotocol.io/
"""
from __future__ import annotations

import json
import sys
from typing import Any, Optional


_PROTOCOL_VERSION = "2024-11-05"


class JarvisMCPServer:
    """Expose Jarvis tools as an MCP server over stdin/stdout."""

    def __init__(self, plugin_loader: Any, manager: Optional[Any] = None) -> None:
        self._loader = plugin_loader
        self._manager = manager

    # ── Public entry point ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Block and serve MCP requests until stdin closes."""
        try:
            for raw in sys.stdin:
                line = raw.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                response = self._dispatch(msg)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
        except (KeyboardInterrupt, EOFError, BrokenPipeError):
            pass

    # ── Dispatcher ─────────────────────────────────────────────────────────────

    def _dispatch(self, msg: dict) -> Optional[dict]:
        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params") or {}

        # Notifications — no response expected
        if msg_id is None and method.startswith("notifications/"):
            return None

        try:
            result = self._handle(method, params)
            if result is None and msg_id is None:
                return None
            return {"jsonrpc": "2.0", "id": msg_id, "result": result or {}}
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": str(e)},
            }

    def _handle(self, method: str, params: dict) -> Optional[dict]:
        if method == "initialize":
            return {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "jarvis-core", "version": "1.0.0"},
            }

        if method == "ping":
            return {}

        if method == "tools/list":
            return {"tools": self._build_tool_list()}

        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            text = self._call_tool(name, args)
            return {"content": [{"type": "text", "text": text}]}

        # Unknown method
        raise ValueError(f"Method not supported: {method}")

    # ── Tool helpers ───────────────────────────────────────────────────────────

    def _build_tool_list(self) -> list:
        tools = []

        for name, tool in self._loader.get_tools().items():
            props: dict = {}
            required: list = []
            for pname, pdef in tool.params.items():
                props[pname] = {
                    "type": pdef.get("type", "string"),
                    "description": pdef.get("description", ""),
                }
                if pdef.get("required"):
                    required.append(pname)
            tools.append({
                "name": name,
                "description": tool.description,
                "inputSchema": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            })

        # Universal ask_jarvis tool (available when Manager is wired in)
        if self._manager:
            tools.append({
                "name": "ask_jarvis",
                "description": (
                    "Send any natural-language query to the full Jarvis pipeline. "
                    "Supports multi-agent delegation, skill reuse, and automatic learning."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Your question or task in natural language",
                        }
                    },
                    "required": ["query"],
                },
            })

        return tools

    def _call_tool(self, name: str, arguments: dict) -> str:
        if name == "ask_jarvis":
            if not self._manager:
                raise ValueError("Manager not available")
            content, _, _ = self._manager.run(arguments.get("query", ""))
            return content

        tools = self._loader.get_tools()
        if name not in tools:
            raise ValueError(f"Unknown tool: {name!r}")

        result = tools[name].func(**arguments)
        return str(result)
