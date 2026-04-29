from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AgentRole(str, Enum):
    MANAGER = "manager"
    CODER = "coder"
    RESEARCH = "research"


@dataclass
class AgentMessage:
    sender: AgentRole
    content: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    recipient: Optional[AgentRole] = None
    metadata: dict = field(default_factory=dict)


class AgentBus:
    """Synchronous request/response message bus for agent communication."""

    def __init__(self) -> None:
        self._agents: dict[AgentRole, Any] = {}
        self._log: list[AgentMessage] = []

    def register(self, agent: Any) -> None:
        self._agents[agent.role] = agent

    def send(self, message: AgentMessage) -> Optional[AgentMessage]:
        self._log.append(message)
        if message.recipient and message.recipient in self._agents:
            response = self._agents[message.recipient].handle(message)
            if response:
                self._log.append(response)
            return response
        return None

    @property
    def log(self) -> list[AgentMessage]:
        return list(self._log)
