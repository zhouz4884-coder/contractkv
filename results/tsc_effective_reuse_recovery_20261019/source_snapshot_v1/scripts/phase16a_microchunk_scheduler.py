#!/usr/bin/env python3
"""Phase 16A scheduler-only micro-chunk prototype.

This is not a vLLM kernel patch. It is an executable scheduler model that
captures the design rule needed after Phase 15D: shadow verification may only
run in idle, bounded micro-chunks, and foreground interference is bounded by
one in-flight chunk rather than by an entire shadow request.
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RAW_FIELDS = [
    "seed",
    "policy",
    "slack_ms",
    "request_id",
    "active_arrival_ms",
    "active_ttft_ms",
    "active_penalty_ms",
    "shadow_tokens_done",
    "shadow_state",
    "shadow_pause_count",
    "foreground_arrived_during_chunk",
]

SUMMARY_FIELDS = [
    "policy",
    "slack_ms",
    "seeds",
    "active_requests",
    "active_completion_rate",
    "active_p50_ttft_ms",
    "active_p95_ttft_ms",
    "active_p99_ttft_ms",
    "active_p95_penalty_ms",
    "active_p99_penalty_ms",
    "shadow_completion_rate",
    "shadow_starved_rate",
    "shadow_scheduler_share",
    "mean_shadow_pause_count",
    "mean_chunk_wall_ms",
    "foreground_completion_rate",
    "gate_pass",
    "claim_boundary",
]


@dataclass(frozen=True)
class PolicyConfig:
    name: str
    chunk_tokens: int
    idle_only: bool
    ordinary_shadow: bool = False


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * pct
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    frac = pos - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def poisson_arrivals(seed: int, count: int, duration_ms: float) -> list[float]:
    rng = random.Random(seed)
    # Draw exponential gaps then rescale to a fixed horizon so all policies see
    # the same foreground shape.
    gaps = [rng.expovariate(1.0) for _ in range(count)]
    total = sum(gaps)
    scale = duration_ms / max(total, 1e-9)
    t = 0.0
    arrivals = []
    for gap in gaps:
        t += gap * scale
        arrivals.append(t)
    return arrivals


def base_ttft(seed: int, index: int) -> float:
    rng = random.Random(seed * 1009 + index)
    return max(35.0, rng.gauss(58.0, 5.0))


def chunk_wall_ms(chunk_tokens: int, context_tokens: int) -> float:
    # The model is intentionally conservative: chunk time grows with both chunk
    # length and current context length, and includes a small scheduler overhead.
    context_factor = 1.0 + min(context_tokens, 4096) / 32768.0
    return 0.55 + (chunk_tokens / 8.0) * context_factor


def simulate_policy(
    seed: int,
    policy: PolicyConfig,
    slack_ms: int,
    active_requests: int,
    duration_ms: float,
    shadow_tokens: int,
    active_gpu_ms: float,
) -> list[dict[str, Any]]:
    arrivals = poisson_arrivals(seed, active_requests, duration_ms)
    rows: list[dict[str, Any]] = []
    now = 0.0
    shadow_done = 0
    shadow_pause_count = 0
    foreground_arrived_during_chunk = 0
    shadow_state = "no_shadow" if policy.name == "baseline" else "running"
    chunk_samples: list[float] = []

    def record_active(index: int, arrival: float, start_after: float) -> None:
        wait = max(0.0, start_after - arrival)
        rows.append(
            {
                "seed": seed,
                "policy": policy.name,
                "slack_ms": slack_ms,
                "request_id": f"s{seed}-a{index}",
                "active_arrival_ms": round(arrival, 6),
                "active_ttft_ms": round(base_ttft(seed, index) + wait, 6),
                "active_penalty_ms": round(wait, 6),
                "shadow_tokens_done": shadow_done,
                "shadow_state": shadow_state,
                "shadow_pause_count": shadow_pause_count,
                "foreground_arrived_during_chunk": foreground_arrived_during_chunk,
            }
        )

    if policy.name == "baseline":
        for index, arrival in enumerate(arrivals):
            now = max(now, arrival)
            record_active(index, arrival, now)
            now += active_gpu_ms
        return rows

    active_index = 0
    while active_index < len(arrivals):
        arrival = arrivals[active_index]
        if now < arrival and shadow_done < shadow_tokens and now < slack_ms:
            remaining = shadow_tokens - shadow_done
            chunk = remaining if policy.ordinary_shadow else min(policy.chunk_tokens, remaining)
            wall = chunk_wall_ms(chunk, shadow_done)
            chunk_samples.append(wall)
            chunk_end = now + wall
            if policy.ordinary_shadow:
                # Ordinary endpoint shadow monopolizes the current scheduler
                # opportunity until the full request chunk is done.
                while active_index < len(arrivals) and arrivals[active_index] < chunk_end:
                    foreground_arrived_during_chunk += 1
                    record_active(active_index, arrivals[active_index], chunk_end)
                    active_index += 1
                now = chunk_end
                shadow_done += chunk
                continue

            if arrivals[active_index] < chunk_end:
                foreground_arrived_during_chunk += 1
                shadow_pause_count += 1
                record_active(active_index, arrival, chunk_end)
                active_index += 1
                now = chunk_end + active_gpu_ms
                shadow_done += chunk
                continue
            now = chunk_end
            shadow_done += chunk
            continue

        now = max(now, arrival)
        record_active(active_index, arrival, now)
        active_index += 1
        now += active_gpu_ms

    if shadow_done >= shadow_tokens:
        shadow_state = "completed"
    elif slack_ms <= now:
        shadow_state = "slack_expired"
    else:
        shadow_state = "starved"
    for row in rows:
        row["shadow_state"] = shadow_state
        row["shadow_tokens_done"] = shadow_done
        row["shadow_pause_count"] = shadow_pause_count
        row["foreground_arrived_during_chunk"] = foreground_arrived_during_chunk
        row["_chunk_samples"] = chunk_samples
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["policy"]), int(row["slack_ms"])), []).append(row)
    out = []
    for (policy, slack_ms), items in sorted(grouped.items()):
        ttfts = [float(row["active_ttft_ms"]) for row in items]
        penalties = [float(row["active_penalty_ms"]) for row in items]
        seeds = sorted({str(row["seed"]) for row in items})
        completed_by_seed = []
        starved_by_seed = []
        pause_by_seed = []
        share_by_seed = []
        chunk_walls: list[float] = []
        for seed in seeds:
            seed_rows = [row for row in items if str(row["seed"]) == seed]
            tokens = max(int(row["shadow_tokens_done"]) for row in seed_rows)
            state = str(seed_rows[-1]["shadow_state"])
            completed_by_seed.append(1.0 if state == "completed" else 0.0)
            starved_by_seed.append(1.0 if state in {"starved", "slack_expired"} else 0.0)
            pause_by_seed.append(max(int(row["shadow_pause_count"]) for row in seed_rows))
            total_active_tokens = len(seed_rows) * 16
            share_by_seed.append(tokens / max(tokens + total_active_tokens, 1))
            for value in seed_rows[-1].get("_chunk_samples", []):
                chunk_walls.append(float(value))
        p95_penalty = percentile(penalties, 0.95)
        p99_penalty = percentile(penalties, 0.99)
        gate = (
            policy == "baseline"
            or (
                p95_penalty <= 10.0
                and p99_penalty <= 20.0
                and statistics.mean(completed_by_seed) >= (0.70 if slack_ms >= 2000 else 0.0)
            )
        )
        out.append(
            {
                "policy": policy,
                "slack_ms": slack_ms,
                "seeds": ",".join(seeds),
                "active_requests": len(items),
                "active_completion_rate": 1.0,
                "active_p50_ttft_ms": round(percentile(ttfts, 0.50), 6),
                "active_p95_ttft_ms": round(percentile(ttfts, 0.95), 6),
                "active_p99_ttft_ms": round(percentile(ttfts, 0.99), 6),
                "active_p95_penalty_ms": round(p95_penalty, 6),
                "active_p99_penalty_ms": round(p99_penalty, 6),
                "shadow_completion_rate": round(statistics.mean(completed_by_seed), 6),
                "shadow_starved_rate": round(statistics.mean(starved_by_seed), 6),
                "shadow_scheduler_share": round(statistics.mean(share_by_seed), 6),
                "mean_shadow_pause_count": round(statistics.mean(pause_by_seed), 6),
                "mean_chunk_wall_ms": round(statistics.mean(chunk_walls), 6) if chunk_walls else 0.0,
                "foreground_completion_rate": 1.0,
                "gate_pass": gate,
                "claim_boundary": "Scheduler-only executable model; not a vLLM source-level micro-chunk actuator.",
            }
        )
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def run(args: argparse.Namespace) -> None:
    policies = [
        PolicyConfig("baseline", 0, idle_only=True),
        PolicyConfig("naive-ordinary-shadow", args.shadow_tokens, idle_only=False, ordinary_shadow=True),
        *[PolicyConfig(f"IDLE_ONLY-{chunk}", chunk, idle_only=True) for chunk in args.chunk_tokens],
    ]
    raw_rows: list[dict[str, Any]] = []
    for seed in args.seeds:
        for slack in args.slack_ms:
            for policy in policies:
                raw_rows.extend(
                    simulate_policy(
                        seed=seed,
                        policy=policy,
                        slack_ms=slack,
                        active_requests=args.active_requests,
                        duration_ms=args.duration_ms,
                        shadow_tokens=args.shadow_tokens,
                        active_gpu_ms=args.active_gpu_ms,
                    )
                )
    clean_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in raw_rows]
    write_csv(args.raw_output, clean_rows, RAW_FIELDS)
    write_csv(args.summary_output, summarize(raw_rows), SUMMARY_FIELDS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[16001, 16002, 16003, 16004, 16005])
    parser.add_argument("--slack-ms", type=int, nargs="+", default=[500, 2000])
    parser.add_argument("--chunk-tokens", type=int, nargs="+", default=[16, 32, 64, 128])
    parser.add_argument("--active-requests", type=int, default=80)
    parser.add_argument("--duration-ms", type=float, default=2000.0)
    parser.add_argument("--shadow-tokens", type=int, default=4096)
    parser.add_argument("--active-gpu-ms", type=float, default=3.0)
    parser.add_argument("--raw-output", type=Path, default=Path("results/runtime/phase16a_microchunk_scheduler_raw_v0.csv"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/runtime/phase16a_microchunk_scheduler_summary_v0.csv"))
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
