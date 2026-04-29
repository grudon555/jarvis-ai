from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from .config import settings


class RouteTarget(Enum):
    LOCAL = "local"
    CLOUD = "cloud"


# Each keyword adds +3 to the complexity score → pushes toward CLOUD
_CLOUD_SIGNALS = {
    "architektur", "architecture", "implementier", "implement",
    "refactor", "refaktorier", "design pattern", "system design",
    "analysier", "analyze", "analyse", "erkläre im detail", "explain in detail",
    "debug", "optimier", "optimize", "migration", "deployment",
    "infrastruktur", "infrastructure", "api design", "database schema",
    "datenbankschema", "skalier", "scale", "performance", "security",
    "sicherheit", "review mein", "review my", "generier", "generate",
    "schreib mir", "write me", "erstell mir", "create for me",
}

# Each keyword adds -2 → pushes toward LOCAL
_LOCAL_SIGNALS = {
    "was ist", "what is", "wer ist", "who is", "wann", "when",
    "wo ist", "where is", "wie viel", "how much", "wie viele", "how many",
    "aktuell", "current", "status", "version", "datum", "date",
    "uhrzeit", "time", "übersetze", "translate", "kurz", "briefly",
    "schnell", "quick",
}


def _has_code_block(text: str) -> bool:
    return "```" in text or bool(re.search(r"^\s{4}\S", text, re.MULTILINE))


def _score(prompt: str) -> int:
    lower = prompt.lower()
    score = 0

    for kw in _CLOUD_SIGNALS:
        if kw in lower:
            score += 3

    for kw in _LOCAL_SIGNALS:
        if kw in lower:
            score -= 2

    if _has_code_block(prompt):
        score += 5

    if len(prompt) > 300:
        score += 3
    elif len(prompt) > 150:
        score += 1

    # Multiple questions or bullet points indicate a complex, multi-part request
    if prompt.count("?") > 1 or bool(re.search(r"^\s*[-*•]\s", prompt, re.MULTILINE)):
        score += 2

    return score


class SmartRouter:
    def __init__(self, threshold: Optional[int] = None):
        self._threshold = threshold if threshold is not None else settings.router_threshold

    def classify(self, prompt: str) -> RouteTarget:
        return RouteTarget.CLOUD if _score(prompt) >= self._threshold else RouteTarget.LOCAL

    def explain(self, prompt: str) -> dict:
        score = _score(prompt)
        return {
            "target": RouteTarget.CLOUD if score >= self._threshold else RouteTarget.LOCAL,
            "score": score,
            "threshold": self._threshold,
            "has_code": _has_code_block(prompt),
            "length": len(prompt),
        }
