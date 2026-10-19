#!/usr/bin/env python3
"""Pure burst-aware quiescence decisions shared by probes and tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ShadowAdmissionReport:
    admitted: bool
    reason: str
    idle_age_ms: float
    current_backoff_ms: float
    collision_count: int
    chunk_tokens: int
    free_blocks: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def collision_backoff_ms(
    collision_count: int,
    base_backoff_ms: float = 1.0,
    max_backoff_ms: float = 8.0,
) -> float:
    if collision_count <= 0:
        return 0.0
    return min(max_backoff_ms, base_backoff_ms * (2 ** (collision_count - 1)))


def decide_shadow_admission(
    *,
    foreground_waiting: bool,
    foreground_running: bool,
    in_collision_backoff: bool,
    idle_age_ms: float,
    idle_grace_ms: float,
    free_blocks: int,
    block_watermark: int,
    collision_count: int,
    current_backoff_ms: float,
    chunk_tokens: int,
    quiescence_enabled: bool = True,
) -> ShadowAdmissionReport:
    if foreground_waiting:
        reason = "foreground_waiting"
    elif foreground_running:
        reason = "foreground_running"
    elif in_collision_backoff:
        reason = "collision_backoff"
    elif quiescence_enabled and idle_age_ms < idle_grace_ms:
        reason = "idle_hysteresis"
    elif free_blocks < block_watermark:
        reason = "kv_pressure"
    else:
        reason = "quiescent"
    return ShadowAdmissionReport(
        admitted=reason == "quiescent",
        reason=reason,
        idle_age_ms=float(idle_age_ms),
        current_backoff_ms=max(0.0, float(current_backoff_ms)),
        collision_count=int(collision_count),
        chunk_tokens=max(0, int(chunk_tokens)),
        free_blocks=int(free_blocks),
    )
