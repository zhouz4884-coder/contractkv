#!/usr/bin/env python3
"""Freeze the one-shot Tier-2 budget from development data only."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], q: float) -> float:
    if not values: return 0.0
    ordered = sorted(values); index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return float(ordered[index])


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bucket_p95(rows: list[dict], length_key: str, cost_key: str,
               bounds: tuple[int, ...]) -> list[float]:
    values = []
    for bound in bounds:
        bucket = [float(row.get(cost_key, 0)) for row in rows
                  if int(row.get(length_key, 0) or 0) <= bound]
        values.append(percentile(bucket, .95))
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-results", type=Path, required=True)
    parser.add_argument("--split-commitment", type=Path, required=True)
    parser.add_argument("--model-id", required=True); parser.add_argument("--tool-slack-ms", type=float, default=3000)
    parser.add_argument("--guard-ms", type=float, default=100); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); rows = load(args.development_results)
    attempted = [row for row in rows if row.get("tier2_attempted")]
    candidate_p95 = percentile([float(row.get("tier2_candidate_ms", 0)) for row in attempted], .95)
    promotion_p95 = percentile([float(row.get("promotion_cost_probe_ms", 0)) for row in attempted], .95)
    tier1_p95 = percentile([float(row.get("tier1_ms", 0)) for row in rows], .95)
    total_budget = candidate_p95 + promotion_p95 + args.guard_ms
    prompt_buckets = (2048, 4096, 8192)
    output_buckets = (16, 32, 64, 96)
    stable_buckets = (2048, 4096, 8192)
    payload = {
        "schema_version": "phase20.two-tier-policy.v1", "model_id": args.model_id,
        "development_results_sha256": digest_file(args.development_results),
        "split_commitment_sha256": digest_file(args.split_commitment),
        "development_sessions": len(rows), "heldout_opened_for_tuning": False,
        "tier1_mode": "same-backend-teacher-forced-strict-top1",
        "tier2_mode": "ephemeral-free-decode-deterministic-task-contract",
        "ground_truth_online": False, "candidate_cache_visibility": "ephemeral-abort",
        "promotion_mode": "separate-promotion-only-PSTP",
        "tier2_once_per_session": True, "length_stop_fail_closed": True,
        "eligible_tier1_failures": ["top1_path_mismatch", "target_token_absent", "terminal_protocol_mismatch", "incomplete"],
        "tier1_p95_ms": tier1_p95, "tier2_candidate_p95_ms": candidate_p95,
        "tier2_promotion_p95_ms": promotion_p95, "guard_ms": args.guard_ms,
        "prompt_length_buckets": prompt_buckets,
        "candidate_total_p95_ms": bucket_p95(attempted, "candidate_prompt_tokens", "tier2_candidate_ms", prompt_buckets),
        "output_length_buckets": output_buckets,
        "decode_inclusive_total_p95_ms": bucket_p95(attempted, "raw_output_tokens", "tier2_candidate_ms", output_buckets),
        "stable_length_buckets": stable_buckets,
        "promotion_p95_ms": bucket_p95(attempted, "expected_stable_tokens", "promotion_cost_probe_ms", stable_buckets),
        "frozen_total_cost_budget_ms": total_budget,
        "budget_semantics": "incremental Tier-2 p95 plus guard; admit only if it fits slack remaining after actual Tier-1",
        "tool_slack_ms": args.tool_slack_ms,
        "tier2_budget_fits_slack": total_budget <= args.tool_slack_ms,
        "development_tier1_coverage": sum(row.get("tier1_pass") is True for row in rows) / max(1, len(rows)),
        "development_tier2_incremental_coverage": sum(row.get("certificate_tier") == "tier2" for row in rows) / max(1, len(rows)),
        "development_total_safe_coverage": sum(row.get("certificate_issued") is True for row in rows) / max(1, len(rows)),
        "claim_boundary": "Frozen from 25 development sessions before opening the 50-session held-out split.",
    }
    payload["policy_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
