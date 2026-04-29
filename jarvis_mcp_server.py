#!/usr/bin/env python
"""Run Jarvis as a standalone MCP server.

Usage
-----
Direct:
    python jarvis_mcp_server.py

Claude Desktop (add to ~/Library/Application Support/Claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "jarvis": {
          "command": "/path/to/Jarvis/.venv/bin/python",
          "args": ["/path/to/Jarvis/jarvis_mcp_server.py"],
          "env": {"ANTHROPIC_API_KEY": "sk-ant-..."}
        }
      }
    }
"""
import sys
from pathlib import Path

# Ensure the Jarvis root is on sys.path when invoked directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.bus import AgentBus
from core.llm import CloudLLM, LocalLLM
from core.plugin_loader import PluginLoader
from core.mcp_server import JarvisMCPServer
from core.mcp_client import MCPClientManager
from agents import CoderAgent, ResearchAgent
from agents.manager import ManagerAgent
from agents.analyst import AnalystAgent
from skills.registry import SkillRegistry


def main() -> None:
    # ── Core setup ────────────────────────────────────────────────────────────
    bus = AgentBus()
    cloud_llm = CloudLLM()
    local_llm = LocalLLM()
    registry = SkillRegistry(skills_dir="skills", db_dir=".jarvis_db")
    analyst = AnalystAgent(llm=cloud_llm, registry=registry)

    ResearchAgent(bus, project_root=".")
    CoderAgent(bus, llm=cloud_llm, cwd=".")
    manager = ManagerAgent(
        bus, cloud_llm=cloud_llm, local_llm=local_llm,
        registry=registry, analyst=analyst,
    )

    # ── Plugins ───────────────────────────────────────────────────────────────
    loader = PluginLoader(plugins_dir="plugins")
    n_plugins = loader.load_all()

    # ── External MCP servers ──────────────────────────────────────────────────
    mcp_client = MCPClientManager()
    n_external = mcp_client.load_from_config("mcp_servers.json")

    # Register external tools as plugins so the server can expose them
    for ext_name, ext_meta in mcp_client.tools.items():
        from plugins import _REGISTRY, JarvisTool
        _REGISTRY[ext_name] = JarvisTool(
            name=ext_name,
            description=f"[{ext_meta['server']}] {ext_meta['description']}",
            params=_schema_to_params(ext_meta.get("schema", {})),
            func=lambda __n=ext_name, **kw: mcp_client.call_tool(__n, kw),
            source="mcp_external",
        )

    # ── Start server ──────────────────────────────────────────────────────────
    server = JarvisMCPServer(plugin_loader=loader, manager=manager)
    server.start()

    mcp_client.shutdown()


def _schema_to_params(schema: dict) -> dict:
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    return {
        k: {
            "type": v.get("type", "string"),
            "description": v.get("description", ""),
            "required": k in required,
        }
        for k, v in props.items()
    }


if __name__ == "__main__":
    main()
