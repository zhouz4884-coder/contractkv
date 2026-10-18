#!/usr/bin/env python3
"""Enforce the prospective service-template mechanism pilot gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_one(path: Path, slo: float = 1500.0) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return next(row for row in rows if float(row["slo_ttft_ms"]) == slo)


def evaluate(d0: dict[str, Any], d1: dict[str, Any], d2: dict[str, Any]) -> dict[str, Any]:
    d0_net = float(d0["mean_ttft_ms"]) + float(d0.get("mean_scope_check_ms", 0))
    d1_net = float(d1["mean_ttft_ms"]) + float(d1.get("mean_scope_check_ms", 0))
    d2_net = (float(d2["mean_ttft_ms"]) + float(d2.get("mean_scope_check_ms", 0))
              + float(d2.get("unhidden_verification_ms_per_future_request", 0)))
    d1_gain = max(0.0, d0_net - d1_net)
    d2_gain = max(0.0, d0_net - d2_net)
    d1_prefill = float(d1["mean_new_prefill_tokens"])
    d2_prefill = float(d2["mean_new_prefill_tokens"])
    checks = {
        "offered_requests_exact": int(d2["offered_requests"]) == 1125,
        "completion_complete": float(d2["completion_rate"]) == 1.0,
        "quality_complete": float(d2["quality_sanity_rate"]) == 1.0,
        "scope_checks_complete": float(d2.get("scope_check_pass_rate", 0)) == 1.0,
        "private_suffix_excluded": float(d2.get("private_suffix_exclusion_rate", 0)) == 1.0,
        "unauthorized_reuse_zero": float(d2.get("unauthorized_cross_domain_reused_hashes", 0)) == 0.0,
        "dynamic_suffix_reuse_zero": float(d2.get("dynamic_suffix_reuse_blocks", 0)) == 0.0,
        "actual_verifier_calls_exact": int(d2["actual_verifier_endpoint_calls"]) == 5,
        "transaction_commits_exact": int(d2["transaction_commits"]) == 5,
        "new_prefill_within_5pct_of_d1": abs(d2_prefill - d1_prefill) / max(d1_prefill, 1.0) <= .05,
        "retains_90pct_of_d1_net_gain": d2_gain / max(d1_gain, 1e-9) >= .90,
    }
    return {
        "schema_version": "tsc.locality-pilot-gate.v0",
        "d0_net_mean_ttft_ms": d0_net, "d1_net_mean_ttft_ms": d1_net,
        "d2_net_mean_ttft_ms": d2_net, "d2_fraction_of_d1_gain": d2_gain / max(d1_gain, 1e-9),
        "d1_mean_new_prefill_tokens": d1_prefill, "d2_mean_new_prefill_tokens": d2_prefill,
        "checks": checks, "gate_pass": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=Path, default=Path("results/tsc_service/locality_cells"))
    parser.add_argument("--output", type=Path,
                        default=Path("results/tsc_service/service_locality_pilot_gate_v0.json"))
    args = parser.parse_args()
    names = {
        "d0": "qwen_g25_r0_D0-native-apc_fp8",
        "d1": "qwen_g25_r0_D1-frozen-safe_fp8",
        "d2": "qwen_g25_r0_D2-template-contractkv_fp8",
    }
    result = evaluate(**{key: load_one(args.cells / value / "summary.jsonl") for key, value in names.items()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
