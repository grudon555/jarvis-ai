from __future__ import annotations

from abc import ABC, abstractmethod

from core.bus import AgentBus, AgentMessage, AgentRole


class BaseAgent(ABC):
    role: AgentRole

    def __init__(self, bus: AgentBus) -> None:
        self.bus = bus
        bus.register(self)

    @abstractmethod
    def handle(self, message: AgentMessage) -> AgentMessage:
        ...
