from __future__ import annotations

import queue
import re
import threading
from typing import Callable, Iterator, Optional

_IMPORT_ERROR: Optional[str] = None
try:
    import numpy as np
    import sounddevice as sd
    from elevenlabs.client import ElevenLabs
except ImportError as e:
    _IMPORT_ERROR = str(e)

# Regex for sentence boundaries (handles German punctuation too)
_SENTENCE_END = re.compile(r"(?<=[.!?:»])\s+|(?<=\n\n)")
_MIN_SENTENCE = 8  # skip very short fragments


class VoiceOutput:
    """ElevenLabs TTS with sentence-level streaming to minimize latency."""

    def __init__(self, api_key: str, voice_id: str, model_id: str) -> None:
        if _IMPORT_ERROR:
            raise RuntimeError(f"Voice output unavailable: {_IMPORT_ERROR}")
        self._client = ElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._model_id = model_id

    def speak(self, text: str) -> None:
        """Synthesize and play a single text string (blocking)."""
        self._play_text(text)

    def stream_speak(self, on_token: Callable) -> Callable[[str], None]:
        """Returns an on_token callback that streams TTS in parallel.

        Usage:
            tts_callback = voice_out.stream_speak(original_on_token)
            manager.run(prompt, on_token=tts_callback)
            voice_out.flush()   # wait for TTS to finish
        """
        sentence_q: queue.Queue = queue.Queue()
        self._tts_queue = sentence_q
        self._tts_thread = threading.Thread(
            target=self._tts_worker, args=(sentence_q,), daemon=True
        )
        self._tts_thread.start()
        self._buffer = ""

        def combined_callback(chunk: str) -> None:
            self._buffer += chunk
            on_token(chunk)
            # Flush complete sentences to TTS queue
            parts = _SENTENCE_END.split(self._buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    s = sentence.strip()
                    if len(s) >= _MIN_SENTENCE:
                        sentence_q.put(s)
                self._buffer = parts[-1]

        return combined_callback

    def flush(self) -> None:
        """Wait for all queued TTS to finish playing."""
        if not hasattr(self, "_tts_queue") or not hasattr(self, "_buffer"):
            return
        # Send remaining buffer
        tail = self._buffer.strip()
        if len(tail) >= _MIN_SENTENCE:
            self._tts_queue.put(tail)
        self._tts_queue.put(None)  # sentinel
        if hasattr(self, "_tts_thread"):
            self._tts_thread.join(timeout=30)

    def _tts_worker(self, q: queue.Queue) -> None:
        while True:
            sentence = q.get()
            if sentence is None:
                break
            try:
                self._play_text(sentence)
            except Exception:
                pass  # Never crash the TTS thread

    def _play_text(self, text: str) -> None:
        audio_iter = self._client.text_to_speech.convert(
            voice_id=self._voice_id,
            text=text,
            model_id=self._model_id,
            output_format="pcm_22050",
        )
        audio_bytes = b"".join(audio_iter)
        if not audio_bytes:
            return
        audio_array = (
            np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        )
        sd.play(audio_array, samplerate=22050)
        sd.wait()

    @staticmethod
    def is_available() -> bool:
        return _IMPORT_ERROR is None
