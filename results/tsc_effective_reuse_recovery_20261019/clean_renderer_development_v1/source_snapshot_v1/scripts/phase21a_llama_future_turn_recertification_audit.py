#!/usr/bin/env python3
"""Re-attest the reproducible Llama future-turn quality violations."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase19b_end_to_end_live import compact_verify, compile_layout, messages, turn_case
from scripts.phase17_live_common import generate_raw
from scripts.phase20a_official_quality import standard_score
from scripts.phase20b_llama_rejection_audit import generate_diagnostic


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def candidate_layout_at(sample: dict[str, Any], target_turn: int, word_limit: int,
                        slack_ms: float) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = SegmentPrefixLedger()
    sid = str(sample["phase20_session_id"])
    case: dict[str, Any] = {}
    layout: dict[str, Any] = {}
    for turn in range(target_turn + 1):
        case = turn_case(sample, turn, word_limit)
        layout = compile_layout("physical-cache-aware", case, ledger, sid, turn, slack_ms)
        ledger.update(sid, turn, case["segments"], layout["topological_order"],
                      policy=str(layout.get("selected_policy", "physical-cache-aware")))
    return case, layout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--causality", type=Path, required=True)
    parser.add_argument("--phase20-output", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--policy-hash", required=True)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--tool-slack-ms", type=float, default=3000)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()

    sessions = {str(row["phase20_session_id"]): row for row in load_jsonl(args.sessions)}
    phase20 = load_jsonl(args.phase20_output)
    turn0 = {str(row["session_id"]): row for row in phase20 if row.get("row_type") == "canary"}
    with args.causality.open(encoding="utf-8", newline="") as handle:
        affected = [row for row in csv.DictReader(handle)
                    if row.get("cause") == "reproducible_future_turn_layout_sensitivity"]

    rows: list[dict[str, Any]] = []
    for item in affected:
        sid = item["session_id"]
        turn = int(item["turn_id"])
        sample = sessions[sid]
        case, layout = candidate_layout_at(sample, turn, args.stable_word_limit,
                                           args.tool_slack_ms)
        raw_layout = compile_layout("raw-order", case, SegmentPrefixLedger(), sid,
                                    turn, args.tool_slack_ms)
        raw_messages = messages(case, raw_layout["topological_order"])
        candidate_messages = messages(case, layout["topological_order"])
        result: dict[str, Any] = {
            "session_id": sid, "turn_id": turn, "dataset": sample.get("dataset"),
            "task": sample.get("task"), "sample_id": sample.get("sample_id"),
            "turn0_certificate_issued": bool(turn0.get(sid, {}).get("certificate_issued")),
            "dynamic_observation": next((segment.get("text", "") for segment in case["segments"]
                                         if segment.get("segment_type") == "TOOL_OBS"), ""),
            "selected_layout": layout.get("selected_policy", ""),
        }
        try:
            raw = generate_raw(args.base_url, args.model, f"phase21a-raw-{sid}-t{turn}",
                               raw_messages, args.timeout, args.max_tokens)
            candidate = generate_diagnostic(
                args.base_url, args.model, f"phase21a-candidate-{sid}-t{turn}",
                candidate_messages, args.timeout, args.max_tokens)
            verify_args = argparse.Namespace(
                base_url=args.base_url, model=args.model, timeout=args.timeout,
                policy_hash=args.policy_hash, load_tier="phase21a-future-turn")
            verify = compact_verify(verify_args, sample, case, layout, raw,
                                    f"{sid}-t{turn}")
            raw_score, metric, raw_error = standard_score(
                str(sample.get("dataset")), str(sample.get("task")), raw["text"],
                sample.get("answer", ""))
            candidate_score, _, candidate_error = standard_score(
                str(sample.get("dataset")), str(sample.get("task")), candidate["text"],
                sample.get("answer", ""))
            drop = max(0.0, raw_score - candidate_score)
            decision = str(verify.get("verify_decision", "INCOMPLETE"))
            issued = bool(verify.get("certificate_issued"))
            if not issued and drop > .03:
                diagnosis = "STALE_SESSION_CERTIFICATE"
            elif issued and drop > .03:
                diagnosis = "CURRENT_TURN_VERIFIER_UNSOUND"
            elif not issued:
                diagnosis = "FRESH_VERIFIER_FAIL_CLOSED"
            else:
                diagnosis = "NO_REPRODUCED_QUALITY_DROP"
            result.update({
                "fresh_verify_decision": decision,
                "fresh_certificate_issued": issued,
                "fresh_txn_state": verify.get("txn_state", ""),
                "raw_finish_reason": raw.get("finish_reason"),
                "candidate_finish_reason": candidate.get("finish_reason"),
                "raw_output": raw["text"], "candidate_output": candidate["text"],
                "raw_score": raw_score, "candidate_score": candidate_score,
                "quality_metric": metric, "quality_drop": drop,
                "quality_error": raw_error or candidate_error,
                "diagnosis": diagnosis, "error_type": "none", "error_message": "",
            })
        except Exception as exc:
            result.update({"fresh_verify_decision": "INCOMPLETE",
                           "fresh_certificate_issued": False,
                           "diagnosis": "PROTOCOL_INCOMPLETE",
                           "error_type": type(exc).__name__, "error_message": str(exc)})
        rows.append(result)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["diagnosis"]] = counts.get(row["diagnosis"], 0) + 1
    summary = {
        "schema_version": "phase21a.llama-future-recertification.v1",
        "audited_rows": len(rows), "diagnosis_counts": counts,
        "fresh_rejected_or_incomplete": sum(not row.get("fresh_certificate_issued", False) for row in rows),
        "fresh_pass_with_quality_drop": sum(row.get("diagnosis") == "CURRENT_TURN_VERIFIER_UNSOUND" for row in rows),
        "conclusion": ("stale_certificate_scope" if counts.get("STALE_SESSION_CERTIFICATE", 0)
                       else "current_turn_verifier_requires_review"),
        "claim_boundary": "Fresh replay of the 11 pre-identified reproducible rows; no threshold tuning.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
