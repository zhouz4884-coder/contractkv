#!/usr/bin/env python3
"""Freeze round-robin and Zipf service-template arrival orders."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def build(sessions: list[dict[str, Any]], gaps: list[float], distribution: str,
          seed: int, alpha: float = 1.2) -> list[dict[str, Any]]:
    by_template: dict[str, list[str]] = defaultdict(list)
    for row in sessions:
        by_template[str(row["service_template_id"])].append(str(row["tsc_session_id"]))
    templates = sorted(by_template)
    rng = random.Random(seed)
    template_positions = defaultdict(int)
    session_turns = defaultdict(lambda: 1)
    last_seen: dict[str, int] = {}
    weights = [1.0 / ((index + 1) ** alpha) for index in range(len(templates))]
    output = []
    for sequence, gap in enumerate(gaps):
        if distribution == "round_robin":
            template = templates[sequence % len(templates)]
        elif distribution == "zipf":
            template = rng.choices(templates, weights=weights, k=1)[0]
        else:
            raise ValueError(distribution)
        members = sorted(by_template[template])
        position = template_positions[template]
        session_id = members[position % len(members)]
        template_positions[template] += 1
        turn = session_turns[session_id]
        session_turns[session_id] = 1 if turn == 9 else turn + 1
        reuse_distance = sequence - last_seen[template] if template in last_seen else -1
        last_seen[template] = sequence
        output.append({
            "sequence": sequence, "session_id": session_id, "turn_id": turn,
            "service_template_id": template, "reuse_distance_requests": reuse_distance,
            "unit_exponential_gap": gap, "template_arrival_distribution": distribution,
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--base-arrivals", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--template-count", type=int, required=True)
    parser.add_argument("--seed", type=int, default=27101)
    args = parser.parse_args()
    sessions = load(args.sessions)
    base = load(args.base_arrivals)
    gaps = [float(row["unit_exponential_gap"]) for row in base]
    manifest = {"template_count": args.template_count, "requests": len(gaps), "distributions": {}}
    for distribution in ("round_robin", "zipf"):
        rows = build(sessions, gaps, distribution, args.seed + (distribution == "zipf"))
        path = args.output_dir / f"tsc_residency_arrivals_t{args.template_count}_{distribution}_v0.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        manifest["distributions"][distribution] = {"sha256": digest(rows), "path": str(path)}
    out = args.output_dir / f"tsc_residency_arrivals_t{args.template_count}_commitment_v0.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
