#!/usr/bin/env python3
"""Measure ContractKV verification break-even contours and 12 live points."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase14c_full_pool_qc_inputs import _retokenize_case
from scripts.phase14m_physical_dedup import fit_shared_text
from scripts.phase17_live_common import generate_raw
from scripts.tsc_open_loop_service import compact_verify_service, service_messages


BOUNDARY_POINTS = [
    (1000, 2, 0, 1), (1000, 5, 1000, 2), (1000, 10, 3000, 4),
    (2000, 2, 0, 2), (2000, 5, 1000, 4), (2000, 10, 3000, 8),
    (4000, 2, 0, 1), (4000, 5, 1000, 2), (4000, 10, 3000, 4),
    (6000, 2, 0, 2), (6000, 10, 3000, 4), (6000, 20, 6000, 8),
]


def segment(segment_id: str, segment_type: str, text: str, dependencies: list[str]) -> dict[str, Any]:
    return {"segment_id": segment_id, "segment_type": segment_type, "text": text,
            "token_count": 0, "dependencies": dependencies}


def build_case(tokenizer: Any, target_tokens: int, point: str, turn: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    stable = fit_shared_text(tokenizer, target_tokens) + f"\nECONOMIC_SCOPE_{point}"
    marker = f"E{turn:02d}{point[-5:]}"
    segments = [
        segment("sys", "SYS_PROMPT", "Follow the request exactly.", []),
        segment("context", "RAG_CHUNK", stable, ["sys"]),
        segment("tool", "TOOL_OBS", f"Private observation turn={turn}; marker={marker}.", ["sys"]),
        segment("query", "USER_QUERY", "Return exactly the marker from TOOL_OBS. /no_think", ["context", "tool"]),
    ]
    case = {
        "dataset": "RULER", "task": "tsc_economics", "sample_id": point,
        "trajectory_id": point, "turn_id": turn, "segments": segments,
        "expected_answer": marker, "unsafe_answer": "ORDER_ERROR",
    }
    case = _retokenize_case(case, tokenizer, 8192, generation_reserve=64)
    raw = {"topological_order": ["sys", "tool", "context", "query"]}
    compiled = {"topological_order": ["sys", "context", "tool", "query"],
                "selected_policy": "posc", "layout_decision": "canonical-slot", "violated_edges": []}
    return case, raw, compiled


def request(args: argparse.Namespace, case: dict[str, Any], layout: dict[str, Any], tag: str,
            cache_salt: str) -> dict[str, Any]:
    result = send_chat_stream(args.base_url, args.model, service_messages(case, layout["topological_order"]),
                              args.max_tokens, args.timeout, tag, cache_salt=cache_salt)
    result["quality_sanity"] = case["expected_answer"] in str(result.get("output_text", ""))
    return result


def one_session(args: argparse.Namespace, tokenizer: Any, point_index: int, target_tokens: int,
                future_reuses: int, slack_ms: float, lane: int) -> dict[str, Any]:
    point = f"{args.model_identity}-{point_index:02d}-lane{lane}"
    raw_salt = f"tsc-economics-raw:{point}"
    contract_salt = f"{args.policy_hash}:{point}"
    case0, raw0, compiled0 = build_case(tokenizer, target_tokens, point, 0)
    raw_warm = request(args, case0, raw0, f"economics-{point}-raw-warm", raw_salt)
    raw_rows = []
    raw_started = time.perf_counter()
    for turn in range(1, future_reuses + 1):
        case, raw, _ = build_case(tokenizer, target_tokens, point, turn)
        raw_rows.append(request(args, case, raw, f"economics-{point}-raw-t{turn}", raw_salt))
    raw_wall_ms = (time.perf_counter() - raw_started) * 1000.0

    registration_started = time.perf_counter()
    raw_canary = generate_raw(args.base_url, args.model, f"economics-{point}-canary",
                              service_messages(case0, compiled0["topological_order"]),
                              args.timeout, args.registration_max_tokens)
    verify = compact_verify_service(
        args, case0, compiled0, raw_canary, point,
        attestation_mode="prospective-qualified-template-exact-path-v1")
    registration_ms = (time.perf_counter() - registration_started) * 1000.0
    certificate_issued = bool(verify.get("certificate_issued"))
    effective_layout0 = compiled0 if certificate_issued else raw0
    effective_policy = "compiled" if certificate_issued else "raw-fallback"
    contract_warm = request(args, case0, effective_layout0, f"economics-{point}-contract-warm", contract_salt)
    contract_rows = []
    contract_started = time.perf_counter()
    for turn in range(1, future_reuses + 1):
        case, raw, compiled = build_case(tokenizer, target_tokens, point, turn)
        effective_layout = compiled if certificate_issued else raw
        contract_rows.append(request(args, case, effective_layout, f"economics-{point}-contract-t{turn}", contract_salt))
    contract_wall_ms = (time.perf_counter() - contract_started) * 1000.0
    raw_ttft = [float(row.get("ttft_ms") or 0) for row in raw_rows if row.get("success")]
    contract_ttft = [float(row.get("ttft_ms") or 0) for row in contract_rows if row.get("success")]
    unhidden_ms = max(0.0, registration_ms - slack_ms)
    net_contract_wall_ms = contract_wall_ms + unhidden_ms
    return {
        "point_id": point_index, "lane": lane, "model_identity": args.model_identity,
        "stable_prefix_tokens": target_tokens, "future_reuses": future_reuses,
        "tool_slack_ms": slack_ms, "concurrency": 0,
        "raw_completion_rate": sum(bool(row.get("success")) for row in raw_rows) / max(1, len(raw_rows)),
        "contract_completion_rate": sum(bool(row.get("success")) for row in contract_rows) / max(1, len(contract_rows)),
        "raw_quality_sanity_rate": sum(bool(row.get("quality_sanity")) for row in raw_rows) / max(1, len(raw_rows)),
        "contract_quality_sanity_rate": sum(bool(row.get("quality_sanity")) for row in contract_rows) / max(1, len(contract_rows)),
        "certificate_issued": certificate_issued,
        "effective_policy": effective_policy,
        "verify_decision": verify.get("verify_decision", ""),
        "txn_state": verify.get("txn_state", ""),
        "failure_reason": verify.get("failure_reason", ""),
        "verification_ms": float(verify.get("verification_ms") or 0),
        "registration_ms": registration_ms, "unhidden_verification_ms": unhidden_ms,
        "raw_mean_ttft_ms": statistics.mean(raw_ttft) if raw_ttft else 0.0,
        "contract_mean_ttft_ms": statistics.mean(contract_ttft) if contract_ttft else 0.0,
        "saved_ms_per_turn": (statistics.mean(raw_ttft) - statistics.mean(contract_ttft)) if raw_ttft and contract_ttft else 0.0,
        "raw_future_wall_ms": raw_wall_ms, "contract_future_wall_ms": contract_wall_ms,
        "net_contract_wall_ms": net_contract_wall_ms,
        "observed_net_benefit_ms": raw_wall_ms - net_contract_wall_ms,
        "observed_net_benefit_fraction": (raw_wall_ms - net_contract_wall_ms) / raw_wall_ms if raw_wall_ms else 0.0,
        "raw_warm_success": bool(raw_warm.get("success")), "contract_warm_success": bool(contract_warm.get("success")),
        "claim_boundary": "Real same-backend registration and future requests. Slack hides at most measured registration wall time.",
    }


def run_point(args: argparse.Namespace, tokenizer: Any, index: int, point: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    target, reuses, slack, concurrency = point
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        rows = list(pool.map(lambda lane: one_session(args, tokenizer, index, target, reuses, slack, lane), range(concurrency)))
    for row in rows:
        row["concurrency"] = concurrency
    return rows


def contour(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_length: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_length.setdefault(int(row["stable_prefix_tokens"]), []).append(row)
    output = []
    # Sealed validation may supply lengths that intentionally differ from the
    # development grid. Build the contour only for lengths actually measured.
    for length in sorted(by_length):
        group = by_length[length]
        saved = statistics.median(float(row["saved_ms_per_turn"]) for row in group)
        verify = statistics.median(float(row["registration_ms"]) for row in group)
        for reuses in (2, 5, 10, 20):
            for slack in (0, 1000, 3000, 6000):
                cost = max(0.0, verify - slack)
                benefit = reuses * saved - cost
                output.append({
                    "model_identity": group[0]["model_identity"], "stable_prefix_tokens": length,
                    "future_reuses": reuses, "tool_slack_ms": slack,
                    "median_saved_ms_per_turn": saved, "median_registration_ms": verify,
                    "break_even_reuses": max(1, int((cost + max(saved, 1e-9) - 1) // max(saved, 1e-9))) if saved > 0 else -1,
                    "predicted_net_benefit_ms": benefit,
                    "operating_region": "tool-slack-hidden" if cost == 0 else "positive" if benefit > 0 else "negative",
                    "claim_boundary": "Contour interpolates measured live per-turn savings and registration costs; selected boundary points are separately live-replayed.",
                })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--model-identity", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--policy-hash", default="tsc-economics-v0")
    parser.add_argument("--qualification-hash", default="tsc-economics-v0")
    parser.add_argument("--certificate-scope-mode", default="qualified_session")
    parser.add_argument("--load-tier", default="tsc-economics")
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--registration-max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--contour-output", type=Path, required=True)
    parser.add_argument(
        "--boundary-points-json",
        default="",
        help=("Optional JSON file containing [[stable_tokens, future_reuses, "
              "tool_slack_ms, concurrency], ...]. This supports sealed "
              "operating-point validation without changing the frozen default grid."),
    )
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    points = BOUNDARY_POINTS
    if args.boundary_points_json:
        payload = json.loads(Path(args.boundary_points_json).read_text(encoding="utf-8"))
        if not isinstance(payload, list) or not payload:
            raise ValueError("boundary-points JSON must be a non-empty list")
        points = [tuple(int(value) for value in point) for point in payload]
        if any(len(point) != 4 for point in points):
            raise ValueError("each boundary point must contain four integers")
    rows = []
    for index, point in enumerate(points):
        point_rows = run_point(args, tokenizer, index, point)
        rows.extend(point_rows)
        write_csv(args.raw_output, rows)
        print(json.dumps({"point": index, "config": point, "lanes": len(point_rows),
                          "mean_benefit": statistics.mean(row["observed_net_benefit_fraction"] for row in point_rows)}, indent=2))
    write_csv(args.raw_output, rows)
    write_csv(args.contour_output, contour(rows))
    gate = all(row["raw_completion_rate"] == 1.0 and row["contract_completion_rate"] == 1.0 for row in rows)
    return 0 if gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
