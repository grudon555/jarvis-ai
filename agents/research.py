from __future__ import annotations

from pathlib import Path

import chromadb

from core.bus import AgentBus, AgentMessage, AgentRole
from .base import BaseAgent

_SKIP = {".venv", ".jarvis_db", "__pycache__", ".git", "node_modules", ".mypy_cache"}
_EXTENSIONS = (".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".env.example")


class ResearchAgent(BaseAgent):
    role = AgentRole.RESEARCH

    def __init__(self, bus: AgentBus, project_root: str = ".") -> None:
        super().__init__(bus)
        self._root = Path(project_root).resolve()
        self._chroma = chromadb.PersistentClient(
            path=str(self._root / ".jarvis_db")
        )
        self._col = self._chroma.get_or_create_collection(
            "documents", metadata={"hnsw:space": "cosine"}
        )

    def index(self) -> int:
        docs, ids, metas = [], [], []
        for ext in _EXTENSIONS:
            for path in self._root.rglob(f"*{ext}"):
                if any(skip in path.parts for skip in _SKIP):
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore").strip()
                    if not content:
                        continue
                    rel = str(path.relative_to(self._root))
                    docs.append(content[:4000])
                    ids.append(rel)
                    metas.append({"path": str(path), "ext": ext})
                except OSError:
                    pass
        if docs:
            self._col.upsert(documents=docs, ids=ids, metadatas=metas)
        return len(docs)

    def search(self, query: str, n_results: int = 3) -> list[dict]:
        total = self._col.count()
        if total == 0:
            return []
        results = self._col.query(
            query_texts=[query], n_results=min(n_results, total)
        )
        output = []
        for i, doc in enumerate(results["documents"][0]):
            output.append({
                "path": results["metadatas"][0][i].get("path", "?"),
                "content": doc[:600],
                "similarity": round(1 - results["distances"][0][i], 3),
            })
        return output

    def handle(self, message: AgentMessage) -> AgentMessage:
        indexed = self.index()
        results = self.search(message.content)

        if not results:
            body = f"No relevant documents found. ({indexed} files indexed)"
        else:
            parts = [f"Found {len(results)} relevant file(s) — {indexed} files indexed:\n"]
            for r in results:
                parts.append(
                    f"[{r['path']}] similarity={r['similarity']:.0%}\n{r['content']}"
                )
            body = "\n\n---\n\n".join(parts)

        return AgentMessage(
            sender=AgentRole.RESEARCH,
            recipient=AgentRole.MANAGER,
            content=body,
            task_id=message.task_id,
        )
