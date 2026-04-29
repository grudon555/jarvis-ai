from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Optional

import ollama
import anthropic

from .config import settings


def _to_anthropic_tools(tools: list) -> tuple[list, dict]:
    """Convert JarvisTool list → (Anthropic tool defs, {name: func})."""
    defs, funcs = [], {}
    for t in tools:
        props: dict = {}
        required: list = []
        for pname, pinfo in (t.params or {}).items():
            props[pname] = {k: v for k, v in pinfo.items() if k in ("type", "description")}
            if not props[pname]:
                props[pname] = {"type": "string"}
            if pinfo.get("required"):
                required.append(pname)
        schema: dict = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        defs.append({
            "name": t.name,
            "description": t.description,
            "input_schema": schema,
        })
        funcs[t.name] = t.func
    return defs, funcs

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

    def chat_with_tools(
        self,
        messages: list,
        tools: list,
        system: Optional[str] = None,
        on_token: Optional[Callable[[str], None]] = None,
        max_iterations: int = 8,
    ) -> str:
        """Tool-use loop: Claude calls tools until it returns a final answer.

        Falls back to stream_chat if no tools are provided.
        The final text response is delivered character-by-character via on_token.
        """
        if not tools:
            return self.stream_chat(messages=messages, system=system, on_token=on_token)

        tool_defs, tool_funcs = _to_anthropic_tools(tools)
        msgs = list(messages)

        for _ in range(max_iterations):
            kwargs: dict = {
                "model": self._model,
                "max_tokens": 4096,
                "messages": msgs,
                "tools": tool_defs,
            }
            if system:
                kwargs["system"] = system

            resp = self._client.messages.create(**kwargs)

            if resp.stop_reason == "end_turn":
                text = "".join(
                    b.text for b in resp.content if hasattr(b, "text")
                )
                if on_token:
                    for ch in text:
                        on_token(ch)
                return text

            if resp.stop_reason == "tool_use":
                msgs.append({"role": "assistant", "content": resp.content})
                results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        fn = tool_funcs.get(block.name)
                        try:
                            result = fn(**block.input) if fn else f"Tool '{block.name}' not found."
                        except Exception as exc:
                            result = f"Tool error: {exc}"
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        })
                msgs.append({"role": "user", "content": results})
                continue

            break  # unexpected stop_reason

        return self.stream_chat(messages=messages, system=system, on_token=on_token)
