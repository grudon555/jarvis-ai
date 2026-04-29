"""Connect to external MCP servers and import their tools into Jarvis."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional


_SERVERS_FILE = "mcp_servers.json"
_MSG_ID = 0


def _next_id() -> int:
    global _MSG_ID
    _MSG_ID += 1
    return _MSG_ID


class _MCPConnection:
    """Persistent subprocess-based connection to a single MCP server."""

    def __init__(self, command: str, args: list, env: Optional[dict] = None) -> None:
        merged_env = {**os.environ, **(env or {})}
        self._proc = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=merged_env,
            text=True,
        )
        self._send({"jsonrpc": "2.0", "id": _next_id(), "method": "initialize", "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "jarvis", "version": "1.0.0"},
        }})
        self._recv()  # discard initialize response
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def list_tools(self) -> list:
        self._send({"jsonrpc": "2.0", "id": _next_id(), "method": "tools/list", "params": {}})
        resp = self._recv()
        return (resp.get("result") or {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        self._send({
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        resp = self._recv()
        content = (resp.get("result") or {}).get("content", [])
        return content[0]["text"] if content else ""

    def close(self) -> None:
        try:
            self._proc.terminate()
        except Exception:
            pass

    def _send(self, msg: dict) -> None:
        assert self._proc.stdin
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

    def _recv(self) -> dict:
        assert self._proc.stdout
        line = self._proc.stdout.readline()
        if not line:
            return {}
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {}


class MCPClientManager:
    """Load and call tools from external MCP servers defined in mcp_servers.json."""

    def __init__(self) -> None:
        self._connections: dict[str, _MCPConnection] = {}
        self._tools: dict[str, dict] = {}   # tool_name → {description, schema, server}

    def load_from_config(self, config_path: str = _SERVERS_FILE) -> int:
        p = Path(config_path)
        if not p.exists():
            return 0
        try:
            servers: dict = json.loads(p.read_text())
        except Exception:
            return 0

        count = 0
        for server_name, cfg in servers.items():
            try:
                conn = _MCPConnection(
                    command=cfg["command"],
                    args=cfg.get("args", []),
                    env=cfg.get("env"),
                )
                tools = conn.list_tools()
                self._connections[server_name] = conn
                for tool in tools:
                    self._tools[tool["name"]] = {
                        "description": tool.get("description", ""),
                        "schema": tool.get("inputSchema", {}),
                        "server": server_name,
                    }
                count += len(tools)
            except Exception:
                pass
        return count

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        meta = self._tools.get(tool_name)
        if not meta:
            raise ValueError(f"External tool not found: {tool_name!r}")
        conn = self._connections[meta["server"]]
        return conn.call_tool(tool_name, arguments)

    def shutdown(self) -> None:
        for conn in self._connections.values():
            conn.close()

    @property
    def tools(self) -> dict:
        return dict(self._tools)

    @property
    def server_names(self) -> list:
        return list(self._connections.keys())
