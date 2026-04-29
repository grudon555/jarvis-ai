from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Optional

import ollama
import anthropic

from .config import settings

# Pricing per million tokens (claude-sonnet-4-6, 2025-04)
_ANTHROPIC_INPUT_COST_PER_MTOK = 3.0
_ANTHROPIC_OUTPUT_COST_PER_MTOK = 15.0


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        if self.provider != "anthropic":
            return 0.0
        return (
            self.input_tokens * _ANTHROPIC_INPUT_COST_PER_MTOK
            + self.output_tokens * _ANTHROPIC_OUTPUT_COST_PER_MTOK
        ) / 1_000_000


class LocalLLM:
    def __init__(self):
        self._client = ollama.Client(host=settings.ollama_host)

    def get_active_model(self) -> str:
        models = self._client.list()
        if not models.models:
            raise RuntimeError("No Ollama model loaded. Run: ollama pull <model>")
        return models.models[0].model

    def chat(self, messages: list, system: Optional[str] = None) -> LLMResponse:
        model = self.get_active_model()
        if system:
            messages = [{"role": "system", "content": system}] + messages
        resp = self._client.chat(model=model, messages=messages)
        return LLMResponse(
            content=resp.message.content,
            model=model,
            provider="ollama",
            input_tokens=resp.prompt_eval_count or 0,
            output_tokens=resp.eval_count or 0,
        )


class CloudLLM:
    def __init__(self):
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key or None
        )
        self._model = settings.cloud_model

    def chat(self, messages: list, system: Optional[str] = None) -> LLMResponse:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        resp = self._client.messages.create(**kwargs)
        return LLMResponse(
            content=resp.content[0].text,
            model=self._model,
            provider="anthropic",
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )

    def stream_chat(
        self,
        messages: list,
        system: Optional[str] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Stream response, calling on_token for each chunk. Returns full text."""
        kwargs: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        full_text = []
        with self._client.messages.stream(**kwargs) as stream:
            for chunk in stream.text_stream:
                full_text.append(chunk)
                if on_token:
                    on_token(chunk)
        return "".join(full_text)
