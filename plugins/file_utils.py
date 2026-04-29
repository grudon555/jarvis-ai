"""Built-in plugin: file-system utilities."""
from pathlib import Path

from plugins import jarvis_tool


@jarvis_tool(
    name="list_directory",
    description="List files and folders in a directory",
    params={
        "path": {"type": "string", "description": "Directory path (default: current dir)"}
    },
)
def list_directory(path: str = ".") -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Path not found: {path}"
    if not p.is_dir():
        return f"Not a directory: {path}"
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    rows = [f"{'📁' if i.is_dir() else '📄'}  {i.name}" for i in items]
    header = f"📂 {p}  ({len(rows)} items)"
    return header + "\n" + "\n".join(rows)


@jarvis_tool(
    name="read_file_excerpt",
    description="Read the first N lines of a text file",
    params={
        "path": {"type": "string", "description": "File path", "required": True},
        "lines": {"type": "integer", "description": "Number of lines to read (default 40)"},
    },
)
def read_file_excerpt(path: str, lines: int = 40) -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"File not found: {path}"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        text_lines = content.splitlines()[:lines]
        suffix = f"\n… ({len(content.splitlines()) - lines} more lines)" if len(content.splitlines()) > lines else ""
        return "\n".join(text_lines) + suffix
    except OSError as e:
        return f"Cannot read: {e}"
