"""macOS clipboard read/write via pbpaste / pbcopy."""
import subprocess

from plugins import jarvis_tool


@jarvis_tool(
    name="read_clipboard",
    description="Read the current macOS clipboard content.",
    params={},
)
def read_clipboard() -> str:
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
        text = result.stdout
        if not text:
            return "Clipboard is empty."
        return f"Clipboard:\n{text}"
    except Exception as exc:
        return f"Could not read clipboard: {exc}"


@jarvis_tool(
    name="write_clipboard",
    description="Write text to the macOS clipboard (copy).",
    params={
        "text": {"type": "string", "description": "Text to write to clipboard", "required": True},
    },
)
def write_clipboard(text: str) -> str:
    try:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=5)
        preview = text[:120] + ("…" if len(text) > 120 else "")
        return f"Copied to clipboard: {preview}"
    except Exception as exc:
        return f"Could not write to clipboard: {exc}"
