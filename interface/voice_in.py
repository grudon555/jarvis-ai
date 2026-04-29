from __future__ import annotations

from typing import Optional

_IMPORT_ERROR: Optional[str] = None
try:
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel
except ImportError as e:
    _IMPORT_ERROR = str(e)


class VoiceInput:
    """Push-to-talk voice input using faster-whisper (fully local)."""

    def __init__(self, model_size: str = "base", language: str = "de") -> None:
        if _IMPORT_ERROR:
            raise RuntimeError(f"Voice input unavailable: {_IMPORT_ERROR}")
        self._samplerate = 16000
        self._language = language
        self._model: Optional[WhisperModel] = None
        self._model_size = model_size
        self._chunks: list = []
        self._recording = False
        self._stream: Optional[sd.InputStream] = None

    def _ensure_model(self) -> None:
        if self._model is None:
            self._model = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type="int8",
            )

    def start_recording(self) -> None:
        self._chunks = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self._samplerate,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop_and_transcribe(self) -> str:
        if not self._recording or self._stream is None:
            return ""
        self._recording = False
        self._stream.stop()
        self._stream.close()
        self._stream = None

        if not self._chunks:
            return ""

        self._ensure_model()
        audio = np.concatenate(self._chunks, axis=0).flatten()

        if len(audio) < self._samplerate * 0.5:  # less than 0.5s → skip
            return ""

        segments, _ = self._model.transcribe(  # type: ignore[union-attr]
            audio,
            beam_size=5,
            language=self._language,
            vad_filter=True,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def _callback(
        self,
        indata: "np.ndarray",
        frames: int,
        time: object,
        status: object,
    ) -> None:
        if self._recording:
            self._chunks.append(indata.copy())

    @staticmethod
    def is_available() -> bool:
        return _IMPORT_ERROR is None
