from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Optional

from core.bus import AgentBus, AgentMessage, AgentRole
from core.llm import CloudLLM
from .base import BaseAgent

_SYSTEM = """\
You are the Coder Agent for Jarvis running on macOS. You specialize in:
- Writing, editing, and explaining Python code
- File system operations and project scaffolding
- Terminal commands and shell scripting (macOS/zsh)
- Debugging and refactoring

Be concise and provide complete, runnable code. Show file paths for any files you create or modify.\
"""

# Read-safe commands that cannot cause irreversible damage
_ALLOWED = {
    "ls", "cat", "head", "tail", "find", "pwd", "echo", "tree",
    "python", "python3", "pip", "pip3",
    "git", "grep", "wc", "du", "df", "which", "brew",
    "mkdir", "touch", "cp", "mv",
}


class CoderAgent(BaseAgent):
    role = AgentRole.CODER

    def __init__(self, bus: AgentBus, llm: CloudLLM, cwd: str = ".") -> None:
        super().__init__(bus)
        self._llm = llm
        self._cwd = str(Path(cwd).resolve())

    def run_command(self, cmd: str, timeout: int = 30) -> str:
        try:
            parts = shlex.split(cmd)
        except ValueError as e:
            return f"Parse error: {e}"
        if not parts or parts[0] not in _ALLOWED:
            return f"'{parts[0] if parts else cmd}' not in allowlist."
        try:
            result = subprocess.run(
                parts, capture_output=True, text=True,
                timeout=timeout, cwd=self._cwd,
            )
            return (result.stdout + result.stderr).strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out."
        except Exception as e:
            return f"Error: {e}"

    def read_file(self, path: str) -> str:
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError as e:
            return f"Cannot read: {e}"

    def write_file(self, path: str, content: str) -> str:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Written: {path}"
        except OSError as e:
            return f"Cannot write: {e}"

    def handle(self, message: AgentMessage) -> AgentMessage:
        prompt = message.content
        context: Optional[str] = message.metadata.get("research_context")
        if context:
            prompt = f"Relevant project context:\n{context}\n\nTask: {prompt}"

        response = self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system=_SYSTEM,
        )
        return AgentMessage(
            sender=AgentRole.CODER,
            recipient=AgentRole.MANAGER,
            content=response.content,
            task_id=message.task_id,
            metadata={
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_usd": response.estimated_cost_usd,
            },
        )
