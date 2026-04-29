"""Persistent notes — save/retrieve/list/delete."""
import json
from datetime import datetime
from pathlib import Path

from plugins import jarvis_tool

_NOTES_FILE = Path.home() / ".jarvis" / "notes.json"


def _load() -> dict:
    if not _NOTES_FILE.exists():
        return {}
    try:
        return json.loads(_NOTES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _persist(notes: dict) -> None:
    _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


@jarvis_tool(
    name="save_note",
    description="Save or update a persistent note. Notes survive across sessions.",
    params={
        "title": {"type": "string", "description": "Note title (used as key)", "required": True},
        "content": {"type": "string", "description": "Note body text", "required": True},
    },
)
def save_note(title: str, content: str) -> str:
    notes = _load()
    notes[title] = {"content": content, "updated": datetime.now().isoformat()}
    _persist(notes)
    return f"Note '{title}' saved."


@jarvis_tool(
    name="get_note",
    description="Retrieve a saved note by its title.",
    params={
        "title": {"type": "string", "description": "Note title", "required": True},
    },
)
def get_note(title: str) -> str:
    notes = _load()
    if title not in notes:
        return f"No note found: '{title}'."
    n = notes[title]
    return f"**{title}** (updated {n['updated'][:10]}):\n{n['content']}"


@jarvis_tool(
    name="list_notes",
    description="List all saved note titles and their last-updated date.",
    params={},
)
def list_notes() -> str:
    notes = _load()
    if not notes:
        return "No notes saved yet."
    lines = [f"- {t}  ({notes[t]['updated'][:10]})" for t in sorted(notes)]
    return "Saved notes:\n" + "\n".join(lines)


@jarvis_tool(
    name="delete_note",
    description="Permanently delete a saved note by title.",
    params={
        "title": {"type": "string", "description": "Note title", "required": True},
    },
)
def delete_note(title: str) -> str:
    notes = _load()
    if title not in notes:
        return f"No note found: '{title}'."
    del notes[title]
    _persist(notes)
    return f"Note '{title}' deleted."
