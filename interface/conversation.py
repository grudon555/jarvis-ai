"""Multi-turn conversation state per WhatsApp number."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import List


_SESSION_TIMEOUT = 30 * 60   # 30 min inactivity → new session
_MAX_TURNS = 12               # keep last N turns (each turn = user + assistant)


@dataclass
class Session:
    phone: str
    history: List[dict] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    message_count: int = 0


class ConversationManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def get(self, phone: str) -> Session:
        with self._lock:
            s = self._sessions.get(phone)
            if s is None or (time.time() - s.last_active > _SESSION_TIMEOUT):
                s = Session(phone=phone)
                self._sessions[phone] = s
            s.last_active = time.time()
            return s

    def add_turn(self, phone: str, user_msg: str, assistant_msg: str) -> None:
        with self._lock:
            s = self._sessions.get(phone)
            if s is None:
                return
            s.history.append({"role": "user",      "content": user_msg})
            s.history.append({"role": "assistant",  "content": assistant_msg})
            # Trim to max turns (keep last _MAX_TURNS * 2 messages)
            if len(s.history) > _MAX_TURNS * 2:
                s.history = s.history[-_MAX_TURNS * 2:]
            s.message_count += 1
            s.last_active = time.time()

    def reset(self, phone: str) -> None:
        with self._lock:
            self._sessions.pop(phone, None)

    def stats(self, phone: str) -> dict:
        with self._lock:
            s = self._sessions.get(phone)
            if not s:
                return {"turns": 0, "age_min": 0}
            age = int((time.time() - s.started) / 60)
            return {"turns": s.message_count, "age_min": age}

    def build_prompt(self, phone: str, current_message: str) -> str:
        """Prepend recent conversation history to the current message."""
        s = self._sessions.get(phone)
        if s is None or not s.history:
            return current_message

        lines = ["Bisheriges Gespräch (Kontext):"]
        for msg in s.history[-8:]:   # last 4 turns
            role = "Du" if msg["role"] == "user" else "Jarvis"
            lines.append(f"{role}: {msg['content'][:400]}")
        lines.append(f"\nAktuelle Nachricht: {current_message}")
        return "\n".join(lines)
