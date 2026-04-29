"""macOS integration: notifications, open URLs/apps, AppleScript."""
import subprocess

from plugins import jarvis_tool


@jarvis_tool(
    name="send_notification",
    description="Send a macOS system notification (appears in Notification Center).",
    params={
        "title": {"type": "string", "description": "Notification title", "required": True},
        "message": {"type": "string", "description": "Notification body", "required": True},
        "subtitle": {"type": "string", "description": "Optional subtitle line"},
    },
)
def send_notification(title: str, message: str, subtitle: str = "") -> str:
    t = title.replace('"', '\\"')
    m = message.replace('"', '\\"')
    sub = f' subtitle "{subtitle.replace(chr(34), chr(92)+chr(34))}"' if subtitle else ""
    script = f'display notification "{m}"{sub} with title "{t}"'
    try:
        subprocess.run(["osascript", "-e", script], timeout=5, check=True)
        return f"Notification sent: {title}"
    except Exception as exc:
        return f"Notification failed: {exc}"


@jarvis_tool(
    name="open_url",
    description="Open a URL in the default browser.",
    params={
        "url": {"type": "string", "description": "Full URL to open (https://...)", "required": True},
    },
)
def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        subprocess.run(["open", url], timeout=5)
        return f"Opened: {url}"
    except Exception as exc:
        return f"Failed to open URL: {exc}"


@jarvis_tool(
    name="open_application",
    description="Open a macOS application by name.",
    params={
        "name": {"type": "string", "description": "App name, e.g. 'Safari', 'Terminal', 'Finder', 'Notes'", "required": True},
    },
)
def open_application(name: str) -> str:
    try:
        subprocess.run(["open", "-a", name], timeout=5, check=True)
        return f"Opened: {name}"
    except Exception as exc:
        return f"Failed to open '{name}': {exc}"


@jarvis_tool(
    name="run_applescript",
    description="Execute an AppleScript snippet for advanced macOS automation (e.g. control apps, read data).",
    params={
        "script": {"type": "string", "description": "AppleScript code to run", "required": True},
    },
)
def run_applescript(script: str) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return f"AppleScript error: {result.stderr.strip()}"
        return result.stdout.strip() or "Script executed."
    except Exception as exc:
        return f"AppleScript failed: {exc}"


@jarvis_tool(
    name="set_volume",
    description="Set the macOS system output volume (0–100).",
    params={
        "level": {"type": "integer", "description": "Volume level 0–100", "required": True},
    },
)
def set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    script = f"set volume output volume {level}"
    try:
        subprocess.run(["osascript", "-e", script], timeout=5, check=True)
        return f"Volume set to {level}%."
    except Exception as exc:
        return f"Failed to set volume: {exc}"
