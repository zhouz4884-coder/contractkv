"""Low-overhead ContractKV tracing for scheduler critical paths."""

from __future__ import annotations

import os
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import IntEnum


class TraceMode(IntEnum):
    OFF = 0
    COUNTERS = 1
    RING = 2


class EventCode(IntEnum):
    SHADOW_ADMIT = 1
    SHADOW_PARK = 2
    SHADOW_WAKE = 3
    SHADOW_ROUND = 4
    FG_ARRIVAL = 5
    FG_FIRST_SCHEDULE = 6
    VERIFY_FINALIZE = 7


@dataclass
class ContractKVTrace:
    mode: TraceMode
    capacity: int = 200_000
    counters: Counter[int] = field(default_factory=Counter)
    events: deque[tuple[int, int, int, int, int]] = field(init=False)

    def __post_init__(self) -> None:
        self.events = deque(maxlen=self.capacity)

    @classmethod
    def from_env(cls) -> "ContractKVTrace":
        name = os.environ.get("CONTRACTKV_TRACE_MODE", "COUNTERS").upper()
        return cls(TraceMode[name])

    def emit(self, code: EventCode, request_key: int = 0, value0: int = 0, value1: int = 0) -> None:
        if self.mode is TraceMode.OFF:
            return
        self.counters[int(code)] += 1
        if self.mode is TraceMode.RING:
            self.events.append((time.monotonic_ns(), int(code), int(request_key), int(value0), int(value1)))

    def summary(self) -> dict[str, int]:
        return {str(key): int(value) for key, value in sorted(self.counters.items())}
