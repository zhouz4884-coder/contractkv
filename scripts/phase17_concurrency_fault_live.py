#!/usr/bin/env python3
"""Concurrent transaction isolation and fail-closed fault injection for Phase 17."""

from __future__ import annotations

import argparse
import csv
import http.client
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_transaction import PSTPRuntime, write_runtime_registry
from scripts.phase17_live_common import build_layout, build_runtime, generate_raw, post_json, tokenize


FIELDS = [
    "scenario", "case_id", "txn_id", "fault_mode", "verify_decision",
    "txn_state", "commit_tokens", "cache_entries_delta", "certificate_issued",
    "finalize_count", "duplicate_finalize_events", "free_blocks_before_cleanup",
    "free_blocks_after_cleanup", "cleanup_block_delta", "shared_chain_delta_ok",
    "abort_isolation_ok", "state_isolation_ok", "no_stale_pointer_signal",
    "gate_pass", "error", "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def send_candidate(args: argparse.Namespace, request_id: str, prompt_ids: list[int], include_logprobs: bool = True) -> dict[str, Any]:
    payload = {
        "model": args.model, "prompt": prompt_ids, "max_tokens": 1,
        "temperature": 0, "stream": False, "return_token_ids": True,
        "request_id": request_id, "priority": 100,
    }
    if include_logprobs:
        payload["prompt_logprobs"] = 2
    return post_json(args.base_url.rstrip("/") + "/completions", payload, args.timeout)


def send_and_disconnect(args: argparse.Namespace, request_id: str, prompt_ids: list[int]) -> None:
    parsed = urlparse(args.base_url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    body = json.dumps({
        "model": args.model, "prompt": prompt_ids, "max_tokens": 1,
        "temperature": 0, "prompt_logprobs": 2,
        "request_id": request_id, "priority": 100,
    })
    connection.request("POST", "/v1/completions", body=body, headers={"Content-Type": "application/json"})
    connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8017/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-token-id", type=int, default=151645)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()

    definitions = [
        ("same_prefix_two_pass", "same-pass-a", False, "shared-pass", "none"),
        ("same_prefix_two_pass", "same-pass-b", False, "shared-pass", "none"),
        ("same_prefix_pass_fail", "mixed-pass", False, "shared-mixed", "none"),
        ("same_prefix_pass_fail", "mixed-fail", True, "shared-mixed", "none"),
        ("different_prefix", "different-a", False, "different-a", "none"),
        ("different_prefix", "different-b", False, "different-b", "none"),
        ("cancel_before", "cancel-before", False, "cancel-before", "cancel_before_verification"),
        ("cancel_during", "cancel-during", False, "cancel-during", "cancel_during_verification"),
        ("missing_report", "missing-report", False, "missing-report", "missing_report"),
        ("frontend_disconnect", "frontend-disconnect", False, "frontend-disconnect", "frontend_disconnect"),
    ]
    registry: dict[str, PSTPRuntime] = {}
    jobs = []
    for scenario, case_id, conflict, nonce, fault in definitions:
        layout = build_layout(case_id, conflict=conflict, prefix_nonce=nonce)
        raw = generate_raw(args.base_url, args.model, f"phase17-fault-raw-{case_id}", layout["raw_messages"], args.timeout)
        stable_ids = tokenize(args.base_url, args.model, layout["stable_messages"], False, args.timeout)
        candidate_ids = tokenize(args.base_url, args.model, layout["candidate_messages"], True, args.timeout)
        request_id = f"phase17-fault-{case_id}"
        runtime = build_runtime(
            txn_id=f"txn-{case_id}", stable_ids=stable_ids,
            candidate_prompt_ids=candidate_ids, raw=raw,
            stop_token_id=args.stop_token_id,
            thresholds={"tau_raw": 0.0, "tau_abs": 0.0, "tau_drop": 4.0},
            candidate_messages=layout["candidate_messages"], fault_mode=fault,
        )
        registry[request_id] = runtime
        jobs.append((scenario, case_id, request_id, candidate_ids + raw["token_ids"] + [raw["terminal_stop_token_id"]], runtime))
    write_runtime_registry(args.registry, registry)

    errors: dict[str, str] = {}
    concurrent_groups = ["same_prefix_two_pass", "same_prefix_pass_fail", "different_prefix"]
    for scenario in concurrent_groups:
        group = [job for job in jobs if job[0] == scenario]
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(send_candidate, args, job[2], job[3]): job[1] for job in group}
            for future, case_id in [(future, case_id) for future, case_id in futures.items()]:
                try:
                    future.result()
                except Exception as exc:
                    errors[case_id] = str(exc)
    for scenario, case_id, request_id, prompt_ids, _ in jobs:
        if scenario in concurrent_groups:
            continue
        try:
            if scenario == "frontend_disconnect":
                send_and_disconnect(args, request_id, prompt_ids)
            else:
                send_candidate(args, request_id, prompt_ids, include_logprobs=scenario != "missing_report")
        except Exception as exc:
            errors[case_id] = str(exc)
    time.sleep(3)

    events = load_jsonl(args.event_log)
    event_by_txn: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for event in events:
        txn = str(event.get("txn_id", ""))
        if txn:
            event_by_txn.setdefault(txn, {}).setdefault(str(event.get("event")), []).append(event)
    scenario_rows: dict[str, list[dict[str, Any]]] = {}
    rows = []
    for scenario, case_id, _, _, runtime in jobs:
        grouped = event_by_txn.get(runtime.plan.txn_id, {})
        final = (grouped.get("phase17_pstp_finalize") or [{}])[-1]
        cleanup = (grouped.get("phase17_post_cleanup") or [{}])[-1]
        duplicates = grouped.get("phase17_finalize_duplicate") or []
        certs = grouped.get("phase17_certificate") or []
        before = int(final.get("free_blocks_before_cleanup", 0) or 0)
        after = int(cleanup.get("free_blocks_after_cleanup", before) or before)
        row = {
            "scenario": scenario, "case_id": case_id, "txn_id": runtime.plan.txn_id,
            "fault_mode": runtime.plan.fault_mode,
            "verify_decision": final.get("verify_decision", "MISSING"),
            "txn_state": final.get("txn_state", "MISSING"),
            "commit_tokens": int(final.get("commit_tokens", 0) or 0),
            "cache_entries_delta": int(final.get("cache_entries_delta", 0) or 0),
            "certificate_issued": bool(certs), "finalize_count": final.get("finalize_count", 0),
            "duplicate_finalize_events": len(duplicates),
            "free_blocks_before_cleanup": before, "free_blocks_after_cleanup": after,
            "cleanup_block_delta": after - before,
            "shared_chain_delta_ok": True, "abort_isolation_ok": True,
            "state_isolation_ok": final.get("txn_id") == runtime.plan.txn_id,
            "no_stale_pointer_signal": bool(cleanup) and all(int(value) >= 1 for value in final.get("physical_block_ref_counts", [])),
            "gate_pass": False, "error": errors.get(case_id, ""),
            "claim_boundary": "Live vLLM concurrent/fault probe with source-level fault modes; stale-pointer check is invariant-based, not memory-sanitizer proof.",
        }
        rows.append(row); scenario_rows.setdefault(scenario, []).append(row)

    for scenario, group in scenario_rows.items():
        if scenario == "same_prefix_two_pass":
            commits = [row for row in group if row["txn_state"] == "COMMITTED"]
            shared_ok = len(commits) >= 1 and sum(row["cache_entries_delta"] for row in commits) <= max(row["commit_tokens"] // 16 for row in commits)
        else:
            shared_ok = True
        abort_ok = all(row["cache_entries_delta"] == 0 and not row["certificate_issued"] for row in group if row["txn_state"] == "ABORTED")
        for row in group:
            row["shared_chain_delta_ok"] = shared_ok
            row["abort_isolation_ok"] = abort_ok
            expected_abort = row["fault_mode"] != "none" or "fail" in row["case_id"]
            state_ok = row["txn_state"] == ("ABORTED" if expected_abort else row["txn_state"])
            row["gate_pass"] = bool(
                row["txn_state"] in {"COMMITTED", "ABORTED"}
                and row["state_isolation_ok"] and row["shared_chain_delta_ok"]
                and row["abort_isolation_ok"] and row["duplicate_finalize_events"] == 1
                and (not expected_abort or (row["txn_state"] == "ABORTED" and not row["certificate_issued"]))
                and state_ok
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"rows": len(rows), "passed": sum(row["gate_pass"] for row in rows)}, indent=2))
    return 0 if rows and all(row["gate_pass"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
