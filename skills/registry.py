from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import chromadb

_REGISTRY_FILE = "_registry.json"
_SIMILARITY_THRESHOLD = 0.72  # cosine similarity — below this, skill is not considered a match


@dataclass
class SkillData:
    name: str
    description: str
    tags: list
    function_code: str
    efficiency_score: float
    created: str = field(default_factory=lambda: datetime.now().isoformat()[:10])
    use_count: int = 0


@dataclass
class SkillMatch:
    name: str
    description: str
    code: str
    similarity: float


class SkillRegistry:
    def __init__(self, skills_dir: str = "skills", db_dir: str = ".jarvis_db") -> None:
        self._dir = Path(skills_dir).resolve()
        self._dir.mkdir(exist_ok=True)
        self._reg_path = self._dir / _REGISTRY_FILE

        self._chroma = chromadb.PersistentClient(path=str(Path(db_dir).resolve()))
        self._col = self._chroma.get_or_create_collection(
            "skills", metadata={"hnsw:space": "cosine"}
        )

        self._reg: dict = self._load()
        self._sync_chroma()

    def _load(self) -> dict:
        if self._reg_path.exists():
            try:
                return json.loads(self._reg_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _flush(self) -> None:
        self._reg_path.write_text(json.dumps(self._reg, indent=2), encoding="utf-8")

    def _sync_chroma(self) -> None:
        for name, meta in self._reg.items():
            existing = self._col.get(ids=[name])
            if not existing["ids"]:
                self._col.upsert(
                    ids=[name],
                    documents=[meta["description"]],
                    metadatas=[{"name": name, "tags": ",".join(meta.get("tags", []))}],
                )

    def save(self, skill: SkillData) -> str:
        path = self._dir / f"{skill.name}.py"
        header = (
            f"# jarvis-skill\n"
            f"# name: {skill.name}\n"
            f"# description: {skill.description}\n"
            f"# tags: {', '.join(skill.tags)}\n"
            f"# created: {skill.created}\n"
            f"# efficiency_score: {skill.efficiency_score}\n\n"
        )
        path.write_text(header + skill.function_code, encoding="utf-8")

        self._reg[skill.name] = {
            "file": f"{skill.name}.py",
            "description": skill.description,
            "tags": skill.tags,
            "created": skill.created,
            "efficiency_score": skill.efficiency_score,
            "use_count": 0,
        }
        self._flush()

        self._col.upsert(
            ids=[skill.name],
            documents=[skill.description],
            metadatas=[{"name": skill.name, "tags": ",".join(skill.tags)}],
        )
        return str(path)

    def search(self, query: str, n_results: int = 2) -> list[SkillMatch]:
        total = self._col.count()
        if total == 0:
            return []
        results = self._col.query(
            query_texts=[query],
            n_results=min(n_results, total),
        )
        matches = []
        for i, _doc in enumerate(results["documents"][0]):
            sim = 1 - results["distances"][0][i]
            if sim < _SIMILARITY_THRESHOLD:
                continue
            name = results["ids"][0][i]
            code = self._get_code(name)
            if code:
                matches.append(SkillMatch(
                    name=name,
                    description=_doc,
                    code=code,
                    similarity=round(sim, 3),
                ))
                if name in self._reg:
                    self._reg[name]["use_count"] = self._reg[name].get("use_count", 0) + 1
        if matches:
            self._flush()
        return matches

    def _get_code(self, name: str) -> Optional[str]:
        meta = self._reg.get(name)
        if not meta:
            return None
        path = self._dir / meta["file"]
        return path.read_text(encoding="utf-8") if path.exists() else None

    def list_all(self) -> list[dict]:
        return [{"name": n, **m} for n, m in self._reg.items()]

    @property
    def count(self) -> int:
        return len(self._reg)
