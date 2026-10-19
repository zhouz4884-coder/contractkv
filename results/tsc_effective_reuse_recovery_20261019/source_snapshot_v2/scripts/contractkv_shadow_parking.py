"""Parked shadow request state used by the vLLM Phase 18 hook."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class ParkedShadow:
    request: Any
    minimum_wake_ns: int
    generation: int
    park_reason: str
    computed_tokens: int

class ShadowParking:
    def __init__(self) -> None:
        self.items: dict[str, ParkedShadow] = {}
        self.generation = 0
    def park(self, request: Any, wake_ns: int, reason: str) -> bool:
        request_id = str(request.request_id)
        if request_id in self.items:
            self.items[request_id].minimum_wake_ns = max(self.items[request_id].minimum_wake_ns, wake_ns)
            return False
        self.generation += 1
        self.items[request_id] = ParkedShadow(request, wake_ns, self.generation, reason, int(getattr(request, "num_computed_tokens", 0) or 0))
        return True
    def cancel(self, request_id: str) -> ParkedShadow | None:
        return self.items.pop(str(request_id), None)
    def wake(self, now_ns: int, max_wake: int = 1) -> list[ParkedShadow]:
        eligible = sorted((item for item in self.items.values() if item.minimum_wake_ns <= now_ns), key=lambda item: (item.minimum_wake_ns, item.generation))[:max_wake]
        for item in eligible:
            self.items.pop(str(item.request.request_id), None)
        return eligible
