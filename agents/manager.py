from __future__ import annotations

from typing import Callable, Optional

from core.bus import AgentBus, AgentMessage, AgentRole
from core.llm import CloudLLM, LocalLLM
from core.router import SmartRouter, RouteTarget
from skills.registry import SkillRegistry, SkillMatch
from .base import BaseAgent

_CLASSIFY_PROMPT = """\
Classify the user request into one or more of these categories.

RESEARCH — find, search, or look up content in existing project files
CODER    — write code, create/edit files, run terminal commands, implement features
DIRECT   — general questions, explanations, analysis, conversation

Reply with ONLY category names, comma-separated. No explanation.
Examples: "DIRECT" | "CODER" | "RESEARCH,CODER"

Request: {prompt}\
"""

_SYNTHESIS_PROMPT = """\
You are Jarvis. Synthesize the agent results into one clear, direct response.
Do not repeat raw results verbatim — integrate them into a coherent answer.
Be concise and well-structured.

User request: {prompt}

Agent results:
{results}\
"""

_DIRECT_SYSTEM = (
    "You are Jarvis, a precise and helpful AI assistant. "
    "Be concise unless detail is explicitly requested."
)


class ManagerAgent(BaseAgent):
    role = AgentRole.MANAGER

    def __init__(
        self,
        bus: AgentBus,
        cloud_llm: CloudLLM,
        local_llm: LocalLLM,
        registry: Optional[SkillRegistry] = None,
        analyst: Optional[object] = None,
    ) -> None:
        super().__init__(bus)
        self._cloud = cloud_llm
        self._local = local_llm
        self._router = SmartRouter()
        self._registry = registry
        self._analyst = analyst

    def _classify(self, prompt: str) -> list:
        resp = self._cloud.chat(
            messages=[{"role": "user", "content": _CLASSIFY_PROMPT.format(prompt=prompt)}]
        )
        valid = {"RESEARCH", "CODER", "DIRECT"}
        categories = [c.strip() for c in resp.content.strip().upper().split(",")]
        return [c for c in categories if c in valid] or ["DIRECT"]

    def _skill_lookup(self, prompt: str) -> tuple:
        """Returns (matches, system_context_str). Empty list if registry disabled."""
        if not self._registry:
            return [], ""
        matches = self._registry.search(prompt)
        if not matches:
            return [], ""
        parts = ["## Skills already learned — reuse these instead of re-solving:\n"]
        for m in matches:
            parts.append(f"### {m.name}  (similarity {m.similarity:.0%})\n{m.code}")
        return matches, "\n\n".join(parts)

    def run(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> tuple:
        """Returns (content, agent_log, meta).

        on_token — called for each streamed text chunk on the final cloud response.
        meta keys: skill_hits, skill_saved, analyst_reason
        """
        meta: dict = {"skill_hits": [], "skill_saved": None, "analyst_reason": None}

        # ── 1. Skill registry check — zero cloud cost ──────────────────────────
        matches, skill_ctx = self._skill_lookup(prompt)
        if matches:
            meta["skill_hits"] = [m.name for m in matches]
            resp = self._local.chat(
                messages=[{"role": "user", "content": prompt}],
                system=f"{_DIRECT_SYSTEM}\n\n{skill_ctx}",
            )
            if on_token:
                for ch in resp.content:
                    on_token(ch)
            return resp.content, [], meta

        # ── 2. SmartRouter: LOCAL fast path ────────────────────────────────────
        if self._router.classify(prompt) == RouteTarget.LOCAL:
            resp = self._local.chat(
                messages=[{"role": "user", "content": prompt}],
                system=_DIRECT_SYSTEM,
            )
            if on_token:
                for ch in resp.content:
                    on_token(ch)
            return resp.content, [], meta

        # ── 3. Cloud path: classify → delegate ────────────────────────────────
        categories = self._classify(prompt)

        if categories == ["DIRECT"]:
            content = self._cloud.stream_chat(
                messages=[{"role": "user", "content": prompt}],
                system=_DIRECT_SYSTEM,
                on_token=on_token,
            )
            self._run_analyst(prompt, content, meta)
            return content, [], meta

        collected: list = []
        research_result: Optional[AgentMessage] = None

        if "RESEARCH" in categories:
            result = self.bus.send(AgentMessage(
                sender=AgentRole.MANAGER,
                recipient=AgentRole.RESEARCH,
                content=prompt,
            ))
            if result:
                research_result = result
                collected.append(result)

        if "CODER" in categories:
            msg_meta: dict = {}
            if research_result:
                msg_meta["research_context"] = research_result.content
            result = self.bus.send(AgentMessage(
                sender=AgentRole.MANAGER,
                recipient=AgentRole.CODER,
                content=prompt,
                metadata=msg_meta,
            ))
            if result:
                collected.append(result)

        if not collected:
            content = self._cloud.stream_chat(
                messages=[{"role": "user", "content": prompt}],
                system=_DIRECT_SYSTEM,
                on_token=on_token,
            )
            self._run_analyst(prompt, content, meta)
            return content, [], meta

        results_text = "\n\n".join(
            f"[{r.sender.value.upper()} AGENT]:\n{r.content}" for r in collected
        )
        # ── 4. Streaming synthesis ─────────────────────────────────────────────
        content = self._cloud.stream_chat(
            messages=[{"role": "user", "content": _SYNTHESIS_PROMPT.format(
                prompt=prompt, results=results_text,
            )}],
            on_token=on_token,
        )

        # ── 5. Analyst ─────────────────────────────────────────────────────────
        self._run_analyst(prompt, content, meta)

        return content, collected, meta

    def _run_analyst(self, prompt: str, solution: str, meta: dict) -> None:
        if not self._analyst:
            return
        try:
            result = self._analyst.analyze_and_save(prompt, solution)
            if result.should_save and result.skill:
                meta["skill_saved"] = result.skill.name
                meta["analyst_reason"] = result.reason
            else:
                meta["analyst_reason"] = result.reason
        except Exception:
            pass  # Analyst failure must never break the main response

    def handle(self, message: AgentMessage) -> AgentMessage:
        content, _, _ = self.run(message.content)
        return AgentMessage(
            sender=AgentRole.MANAGER,
            content=content,
            task_id=message.task_id,
        )
