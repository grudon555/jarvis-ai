from __future__ import annotations

import re

from core.bus import AgentBus, AgentMessage, AgentRole
from core.llm import CloudLLM
from .base import BaseAgent

_SUMMARIZE_PROMPT = """\
You are Jarvis. Using the web search results and page content below, answer the user's question \
with accurate, up-to-date information. Be concise. Cite sources (URLs) where relevant.

User question: {query}

--- Search results & page content ---
{context}
"""


class WebAgent(BaseAgent):
    role = AgentRole.WEB

    def __init__(self, bus: AgentBus, llm: CloudLLM) -> None:
        super().__init__(bus)
        self._llm = llm

    def handle(self, message: AgentMessage) -> AgentMessage:
        from plugins.web import web_search, fetch_url

        query = message.content

        search_raw = web_search(query, num_results=5)

        urls = re.findall(r"https?://\S+", search_raw)[:2]
        page_blocks: list[str] = []
        for url in urls:
            content = fetch_url(url, max_length=2500)
            first_line = content.split("\n")[0]
            if not any(first_line.startswith(p) for p in ("Fehler", "Timeout", "HTTP")):
                page_blocks.append(content)

        context = search_raw
        if page_blocks:
            context += "\n\n--- Full page content ---\n\n" + "\n\n---\n\n".join(page_blocks)

        resp = self._llm.chat(
            messages=[{"role": "user", "content": _SUMMARIZE_PROMPT.format(
                query=query, context=context,
            )}]
        )

        return AgentMessage(
            sender=AgentRole.WEB,
            recipient=AgentRole.MANAGER,
            content=resp.content,
            task_id=message.task_id,
        )
