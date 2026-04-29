from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from rich import box
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text


class JarvisDisplay:
    """Thread-safe state container + Rich layout renderer."""

    _MAX_CONV = 40
    _MAX_LOG = 30

    def __init__(self, model: str = "sonnet-4.6") -> None:
        self._lock = threading.Lock()
        self._model = model
        self._conversation: list[tuple[str, str]] = []
        self._streaming: Optional[str] = None  # text being streamed right now
        self._log: list[str] = []
        self._status: dict[str, str] = {
            "ollama": "checking…",
            "skills": "0 skills",
            "tools": "0 tools",
            "analyst": "ready",
            "voice": "disabled",
        }
        self._recording = False

    # ── Setters (thread-safe) ──────────────────────────────────────────────────

    def add_message(self, role: str, text: str) -> None:
        with self._lock:
            self._conversation.append((role, text))
            if len(self._conversation) > self._MAX_CONV:
                self._conversation.pop(0)
            self._streaming = None

    def set_streaming(self, text: Optional[str]) -> None:
        with self._lock:
            self._streaming = text

    def log(self, entry: str) -> None:
        with self._lock:
            ts = datetime.now().strftime("%H:%M")
            self._log.append(f"[dim]{ts}[/dim] {entry}")
            if len(self._log) > self._MAX_LOG:
                self._log.pop(0)

    def set_status(self, key: str, value: str) -> None:
        with self._lock:
            self._status[key] = value

    def set_recording(self, recording: bool) -> None:
        with self._lock:
            self._recording = recording

    # ── Layout renderer ────────────────────────────────────────────────────────

    def get_layout(self) -> Layout:
        with self._lock:
            return self._build()

    def _build(self) -> Layout:
        root = Layout(name="root")
        root.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        root["body"].split_row(
            Layout(name="conv", ratio=3),
            Layout(name="side", ratio=2),
        )
        root["side"].split_column(
            Layout(name="status", ratio=2),
            Layout(name="agentlog", ratio=3),
        )

        root["header"].update(self._header())
        root["conv"].update(self._conversation_panel())
        root["status"].update(self._status_panel())
        root["agentlog"].update(self._log_panel())
        root["footer"].update(self._footer())
        return root

    def _header(self) -> Panel:
        t = Text(justify="center")
        t.append("J A R V I S", style="bold cyan")
        t.append("   ·   ", style="dim")
        t.append(self._model, style="cyan dim")
        t.append("   ·   ", style="dim")
        skills_val = self._status.get("skills", "0 loaded")
        t.append(skills_val, style="green" if "0" not in skills_val else "dim")
        t.append("   ·   ", style="dim")
        ollama_ok = "online" in self._status.get("ollama", "")
        t.append("Ollama ", style="dim")
        t.append("✓" if ollama_ok else "✗", style="green bold" if ollama_ok else "red bold")
        voice_ok = "ready" in self._status.get("voice", "")
        t.append("   Voice ", style="dim")
        t.append("✓" if voice_ok else "—", style="green bold" if voice_ok else "dim")
        return Panel(t, box=box.HEAVY_HEAD, style="cyan")

    def _conversation_panel(self) -> Panel:
        body = Text(overflow="fold")
        msgs = self._conversation[-20:]
        for role, text in msgs:
            if role == "you":
                body.append("You", style="bold cyan")
                body.append("  ", style="")
                body.append(text + "\n\n", style="white")
            else:
                body.append("Jarvis", style="bold")
                body.append("  ", style="")
                body.append(text + "\n\n", style="dim white")

        if self._streaming is not None:
            body.append("Jarvis", style="bold")
            body.append("  ", style="")
            body.append(self._streaming, style="dim white")
            body.append("▋", style="blink cyan")

        if not msgs and self._streaming is None:
            body.append("No messages yet.", style="dim italic")

        return Panel(body, title="[bold]CONVERSATION[/bold]", border_style="cyan dim")

    def _status_panel(self) -> Panel:
        t = Text()
        rows = [
            ("Ollama",   self._status.get("ollama", "?")),
            ("Skills",   self._status.get("skills", "?")),
            ("Tools",    self._status.get("tools", "?")),
            ("Analyst",  self._status.get("analyst", "?")),
            ("Voice",    self._status.get("voice", "?")),
        ]
        for key, val in rows:
            ok = any(w in val for w in ("online", "ready", "loaded", "active"))
            t.append(f"  {key:<10}", style="dim")
            t.append(val + "\n", style="green" if ok else "yellow")
        return Panel(t, title="[bold]STATUS[/bold]", border_style="dim")

    def _log_panel(self) -> Panel:
        t = Text(overflow="fold")
        if self._log:
            for entry in self._log[-15:]:
                t.append_text(Text.from_markup(entry + "\n"))
        else:
            t.append("Waiting for activity…", style="dim italic")
        return Panel(t, title="[bold]AGENT LOG[/bold]", border_style="dim")

    def _footer(self) -> Panel:
        t = Text()
        if self._recording:
            t.append("● REC  ", style="bold red blink")
            t.append("Listening… press [Enter] to stop", style="dim")
        else:
            t.append("⌨  ", style="cyan")
            t.append("Type a message  · ", style="dim")
            t.append("/voice", style="cyan")
            t.append(" to speak  · ", style="dim")
            t.append("/skills", style="cyan")
            t.append(" to list  · ", style="dim")
            t.append("/exit", style="cyan")
        return Panel(t, box=box.SIMPLE, style="dim")
