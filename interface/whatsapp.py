"""Twilio WhatsApp client + message formatting utilities."""
from __future__ import annotations

import os
import re
import tempfile
import time
from typing import Optional

_IMPORT_ERROR: Optional[str] = None
try:
    import requests
    from twilio.rest import Client as TwilioClient
except ImportError as e:
    _IMPORT_ERROR = str(e)


# ── Text formatting ────────────────────────────────────────────────────────────

def md_to_wa(text: str) -> str:
    """Convert Markdown to WhatsApp-flavoured markup."""
    # Code blocks — preserve as-is (WhatsApp supports ``` blocks)
    # Bold: **text** → *text*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text, flags=re.DOTALL)
    # Italic: *text* (single) → _text_, but only if not already bold
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"_\1_", text)
    # Headers: # / ## / ### → *Header*
    text = re.sub(r"^#{1,3}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
    # Unordered list items
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)
    # Numbered lists: keep as-is
    # Horizontal rules → blank line
    text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)
    # Strip leading/trailing whitespace per line
    lines = [l.rstrip() for l in text.splitlines()]
    # Collapse 3+ blank lines into 2
    result, blanks = [], 0
    for line in lines:
        if line.strip() == "":
            blanks += 1
            if blanks <= 2:
                result.append(line)
        else:
            blanks = 0
            result.append(line)
    return "\n".join(result).strip()


def split_message(text: str, max_len: int = 1500) -> list:
    """Split long text at paragraph boundaries respecting WhatsApp's limit."""
    if len(text) <= max_len:
        return [text]

    chunks, buf = [], ""
    for para in re.split(r"\n{2,}", text):
        if len(buf) + len(para) + 2 <= max_len:
            buf = buf + "\n\n" + para if buf else para
        else:
            if buf:
                chunks.append(buf.strip())
            # Para itself longer than limit → split at sentence level
            if len(para) > max_len:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                buf = ""
                for s in sentences:
                    if len(buf) + len(s) + 1 <= max_len:
                        buf = buf + " " + s if buf else s
                    else:
                        if buf:
                            chunks.append(buf.strip())
                        buf = s
            else:
                buf = para
    if buf.strip():
        chunks.append(buf.strip())
    return chunks or [text]


# ── Rate limiter ───────────────────────────────────────────────────────────────

class RateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self._max = max_per_minute
        self._windows: dict[str, list] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        w = self._windows.setdefault(key, [])
        w[:] = [t for t in w if now - t < 60]
        if len(w) >= self._max:
            return False
        w.append(now)
        return True


# ── WhatsApp client ────────────────────────────────────────────────────────────

class WhatsAppClient:
    def __init__(self, account_sid: str, auth_token: str, from_number: str) -> None:
        if _IMPORT_ERROR:
            raise RuntimeError(f"WhatsApp unavailable: {_IMPORT_ERROR}")
        self._twilio = TwilioClient(account_sid, auth_token)
        self._sid = account_sid
        self._token = auth_token
        self._from = f"whatsapp:{from_number}"

    def send(self, to: str, body: str) -> None:
        for i, chunk in enumerate(split_message(body)):
            if i > 0:
                time.sleep(0.3)
            self._twilio.messages.create(
                from_=self._from,
                to=f"whatsapp:{to}",
                body=chunk,
            )

    def download_media(self, url: str) -> bytes:
        """Download Twilio-hosted media (requires Basic auth)."""
        resp = requests.get(url, auth=(self._sid, self._token), timeout=30)
        resp.raise_for_status()
        return resp.content

    def transcribe_voice(self, media_url: str, whisper_model: str = "base", language: str = "de") -> Optional[str]:
        """Download a WhatsApp voice note and return transcription."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return None

        audio_bytes = self.download_media(media_url)
        suffix = ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        try:
            model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(path, language=language, vad_filter=True)
            return " ".join(s.text.strip() for s in segments).strip()
        finally:
            os.unlink(path)

    @staticmethod
    def is_available() -> bool:
        return _IMPORT_ERROR is None
