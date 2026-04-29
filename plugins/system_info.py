"""Built-in plugin: macOS system information."""
import os
import platform
import shutil

from plugins import jarvis_tool


@jarvis_tool(
    name="get_system_info",
    description="Return macOS system details: Python version, CPU arch, disk usage",
    params={},
)
def get_system_info() -> str:
    total, used, free = shutil.disk_usage("/")
    gb = 1024 ** 3
    return (
        f"Platform : {platform.platform()}\n"
        f"Python   : {platform.python_version()}\n"
        f"Machine  : {platform.machine()}\n"
        f"CPU count: {os.cpu_count()}\n"
        f"Disk     : {used // gb} GB used / {total // gb} GB total ({free // gb} GB free)"
    )


@jarvis_tool(
    name="get_env_variable",
    description="Read an environment variable by name",
    params={
        "key": {"type": "string", "description": "Environment variable name", "required": True}
    },
)
def get_env_variable(key: str) -> str:
    value = os.environ.get(key)
    if value is None:
        return f"Variable '{key}' is not set."
    return f"{key}={value}"
