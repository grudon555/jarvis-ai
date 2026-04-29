from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

_REGISTRY: Dict[str, "JarvisTool"] = {}


@dataclass
class JarvisTool:
    name: str
    description: str
    params: Dict[str, Any]
    func: Callable
    source: str = "plugin"   # "plugin" | "skill" | "mcp_external"


def jarvis_tool(
    name: str,
    description: str,
    params: Optional[Dict[str, Any]] = None,
):
    """Decorator — register a function as a discoverable Jarvis tool.

    Example
    -------
    @jarvis_tool(
        name="get_weather",
        description="Get current weather for a city",
        params={
            "city": {"type": "string", "description": "City name", "required": True}
        },
    )
    def get_weather(city: str) -> str:
        ...
    """
    def decorator(func: Callable) -> Callable:
        tool = JarvisTool(
            name=name,
            description=description,
            params=params or {},
            func=func,
        )
        _REGISTRY[name] = tool
        func._jarvis_tool = tool  # type: ignore[attr-defined]
        return func
    return decorator


def all_tools() -> Dict[str, JarvisTool]:
    """Return a snapshot of the global tool registry."""
    return dict(_REGISTRY)
