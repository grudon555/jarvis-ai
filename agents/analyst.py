from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from core.llm import CloudLLM
from skills.registry import SkillData, SkillRegistry

_MIN_LENGTH = 120

_PROMPT = """\
You are a Skill Analyst for Jarvis. Decide if this task+solution should be saved as a reusable Python skill.

SAVE when ALL of these are true:
  ✓ Solves a GENERIC, recurring problem type (parsing, formatting, algorithms, file ops, data transforms)
  ✓ Core logic fits in ONE self-contained function (no external auth, no interactive I/O)
  ✓ Efficient and non-trivial (more than 5 meaningful lines of logic)

DO NOT SAVE when:
  ✗ Highly specific one-off task (rename this exact file, calculate this one number)
  ✗ Pure explanation, conversation, or opinion
  ✗ Requires live network, credentials, or user interaction to be useful at all

If SAVE → respond with ONLY this JSON (no markdown fences, no text outside the JSON):
{{
  "save": true,
  "skill_name": "snake_case_verb_noun",
  "description": "One sentence: what it does and when to use it",
  "tags": ["tag1", "tag2"],
  "efficiency_score": 0.85,
  "function_code": "def skill_snake_case_verb_noun(...):\\n    ..."
}}

If NOT SAVE → respond with ONLY:
{{"save": false, "reason": "one short sentence"}}

---
Task: {prompt}

Solution:
{solution}\
"""


@dataclass
class AnalystResult:
    should_save: bool
    skill: Optional[SkillData] = None
    reason: str = ""


class AnalystAgent:
    """Runs after complex cloud responses to extract and save reusable skills."""

    def __init__(self, llm: CloudLLM, registry: SkillRegistry) -> None:
        self._llm = llm
        self._registry = registry

    def analyze(self, prompt: str, solution: str) -> AnalystResult:
        if len(solution.strip()) < _MIN_LENGTH:
            return AnalystResult(should_save=False, reason="solution too short")

        resp = self._llm.chat(
            messages=[{"role": "user", "content": _PROMPT.format(
                prompt=prompt,
                solution=solution[:3000],
            )}]
        )

        raw = resp.content.strip()
        # Strip accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw).strip()

        try:
            # strict=False allows literal control chars (e.g. unescaped \n in code strings)
            data = json.loads(raw, strict=False)
        except json.JSONDecodeError:
            return AnalystResult(should_save=False, reason="JSON parse error")

        if not data.get("save"):
            return AnalystResult(should_save=False, reason=data.get("reason", ""))

        required = {"skill_name", "description", "tags", "efficiency_score", "function_code"}
        if not required.issubset(data.keys()):
            return AnalystResult(should_save=False, reason="incomplete JSON fields")

        skill = SkillData(
            name=str(data["skill_name"]).lower().replace(" ", "_")[:40],
            description=str(data["description"])[:200],
            tags=[str(t) for t in data["tags"][:5]],
            function_code=str(data["function_code"]),
            efficiency_score=min(1.0, max(0.0, float(data["efficiency_score"]))),
        )
        return AnalystResult(should_save=True, skill=skill)

    def analyze_and_save(self, prompt: str, solution: str) -> AnalystResult:
        result = self.analyze(prompt, solution)
        if result.should_save and result.skill:
            saved_path = self._registry.save(result.skill)
            result.reason = saved_path
        return result
