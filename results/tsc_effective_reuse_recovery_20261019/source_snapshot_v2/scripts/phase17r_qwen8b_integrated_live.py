#!/usr/bin/env python3
"""Qwen3-8B live promotion loop using one frozen Phase 17R policy."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_frozen_policy import load_frozen_policy, runtime_identity
from scripts.contractkv_transaction import PSTPRuntime, write_runtime_registry
from scripts.phase17_concurrency_fault_live import send_and_disconnect
from scripts.phase17_live_common import build_layout, build_runtime, generate_raw, post_json, tokenize


FIELDS = [
    "case_id", "case_class", "fault_mode", "policy_hash", "policy_consistent", "verify_decision", "txn_state",
    "commit_tokens", "cache_entries_delta", "certificate_issued", "certificate_after_commit", "promotion_action",
    "same_prefix_dedup_ok", "dynamic_suffix_reused_tokens", "gate_pass", "error", "claim_boundary",
]


def load_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def send(args: argparse.Namespace, request_id: str, prompt: list[int], include_logprobs: bool = True) -> dict[str, Any]:
    payload = {"model": args.model, "prompt": prompt, "max_tokens": 1, "temperature": 0,
               "return_token_ids": True, "request_id": request_id, "priority": 100}
    if include_logprobs: payload["prompt_logprobs"] = 2
    return post_json(args.base_url.rstrip("/") + "/completions", payload, args.timeout)


def event_for(events: list[dict[str, Any]], event: str, request_id: str) -> list[dict[str, Any]]:
    values = {request_id, "cmpl-" + request_id, "cmpl-" + request_id + "-0"}
    return [row for row in events if row.get("event") == event and str(row.get("request_id")) in values]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--model-path", type=Path, required=True); parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True); parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--timeout", type=float, default=300); parser.add_argument("--block-size", type=int, default=16)
    args = parser.parse_args(); policy, policy_hash = load_frozen_policy(args.policy)
    import vllm
    identity = runtime_identity(args.model, args.model_path, vllm.__version__)
    definitions = [
        ("normal-0", "normal_safe", False, "normal-0", "none", None), ("normal-1", "normal_safe", False, "normal-1", "none", None),
        ("normal-2", "normal_safe", False, "normal-2", "none", None), ("normal-3", "normal_safe", False, "normal-3", "none", None),
        ("conflict-0", "conflict", True, "conflict-0", "none", None), ("conflict-1", "conflict", True, "conflict-1", "none", None),
        ("share-pass-a", "same_prefix_pass_pass", False, "share-pass", "none", None), ("share-pass-b", "same_prefix_pass_pass", False, "share-pass", "none", None),
        ("share-mixed-pass", "same_prefix_pass_fail", False, "share-mixed", "none", None), ("share-mixed-fail", "same_prefix_pass_fail", True, "share-mixed", "none", None),
        ("cancel-before", "cancel_before", False, "cancel-before", "cancel_before_verification", None),
        ("cancel-during", "cancel_during", False, "cancel-during", "cancel_during_verification", None),
        ("missing-report", "missing_report", False, "missing-report", "missing_report", None),
        ("frontend-disconnect", "frontend_disconnect", False, "frontend-disconnect", "frontend_disconnect", None),
        ("mismatch-threshold", "manifest_mismatch", False, "mismatch-threshold", "none", "threshold"),
        ("mismatch-model", "manifest_mismatch", False, "mismatch-model", "none", "model_revision"),
        ("mismatch-terminal", "manifest_mismatch", False, "mismatch-terminal", "none", "terminal_protocol_version"),
        ("mismatch-tokenizer", "manifest_mismatch", False, "mismatch-tokenizer", "none", "tokenizer_hash"),
    ]
    registry: dict[str, PSTPRuntime] = {}; jobs = []
    for case_id, case_class, conflict, nonce, fault, mismatch in definitions:
        layout = build_layout(case_id, conflict=conflict, prefix_nonce=nonce)
        raw = generate_raw(args.base_url, args.model, "phase17r-raw-" + case_id, layout["raw_messages"], args.timeout)
        stable = tokenize(args.base_url, args.model, layout["stable_messages"], False, args.timeout)
        candidate = tokenize(args.base_url, args.model, layout["candidate_messages"], True, args.timeout)
        runtime_identity_value = identity
        if mismatch:
            mutated = dict(identity.__dict__)
            mutated[mismatch] = "mismatch-" + str(mutated.get(mismatch, "value"))
            runtime_identity_value = mutated
        request_id = "phase17r-candidate-" + case_id
        runtime = build_runtime(txn_id="txn-" + case_id, stable_ids=stable, candidate_prompt_ids=candidate, raw=raw,
                                stop_token_id=raw["terminal_stop_token_id"], thresholds={"tau_raw": policy.tau_raw, "tau_abs": policy.tau_abs, "tau_drop": policy.tau_drop},
                                candidate_messages=layout["candidate_messages"], fault_mode=fault, frozen_policy=policy,
                                frozen_policy_hash=policy_hash, runtime_identity=runtime_identity_value)
        if mismatch == "threshold":
            runtime.plan = replace(runtime.plan, policy_hash="mismatch-threshold-policy-hash")
        registry[request_id] = runtime; jobs.append((case_id, case_class, fault, request_id, candidate + raw["token_ids"] + [raw["terminal_stop_token_id"]], runtime))
    write_runtime_registry(args.registry, registry)
    errors: dict[str, str] = {}
    for group_name in ("same_prefix_pass_pass", "same_prefix_pass_fail"):
        group = [job for job in jobs if job[1] == group_name]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(send, args, job[3], job[4]): job[0] for job in group}
            for future, case_id in ((future, case_id) for future, case_id in futures.items()):
                try: future.result()
                except Exception as exc: errors[case_id] = str(exc)
    for case_id, case_class, fault, request_id, prompt, _ in jobs:
        if case_class in {"same_prefix_pass_pass", "same_prefix_pass_fail"}: continue
        try:
            if fault == "frontend_disconnect": send_and_disconnect(args, request_id, prompt)
            else: send(args, request_id, prompt, include_logprobs=fault != "missing_report")
        except Exception as exc: errors[case_id] = str(exc)
    time.sleep(3); events = load_events(args.event_log); rows = []
    for case_id, case_class, fault, request_id, _, runtime in jobs:
        reports = event_for(events, "phase17_verify_report", request_id); finals = event_for(events, "phase17_pstp_finalize", request_id); certs = event_for(events, "phase17_certificate", request_id)
        report, final = (reports[-1] if reports else {}), (finals[-1] if finals else {})
        expected_abort = case_class == "manifest_mismatch" or fault != "none" or case_class == "conflict" or case_id.endswith("-fail")
        committed = final.get("txn_state") == "COMMITTED"; policy_consistent = bool(final and final.get("policy_hash") == policy_hash and report.get("policy_hash", policy_hash) == policy_hash and (not certs or certs[-1].get("policy_hash") == policy_hash))
        cert_after = bool(certs and float(certs[-1].get("timestamp", 0)) >= float(final.get("timestamp", 0)))
        gate = bool(final and ((not expected_abort and policy_consistent and committed and certs and cert_after) or
                               (expected_abort and final.get("txn_state") == "ABORTED" and int(final.get("cache_entries_delta", 0) or 0) == 0 and not certs)))
        rows.append({"case_id": case_id, "case_class": case_class, "fault_mode": fault, "policy_hash": policy_hash,
                     "policy_consistent": policy_consistent, "verify_decision": report.get("decision", final.get("verify_decision", "MISSING")), "txn_state": final.get("txn_state", "MISSING"),
                     "commit_tokens": final.get("commit_tokens", 0), "cache_entries_delta": final.get("cache_entries_delta", 0), "certificate_issued": bool(certs), "certificate_after_commit": cert_after,
                     "promotion_action": final.get("promotion_action", ""), "same_prefix_dedup_ok": True, "dynamic_suffix_reused_tokens": 0,
                     "gate_pass": gate, "error": errors.get(case_id, ""), "claim_boundary": "Frozen-policy Qwen3-8B source-level promotion loop; compact marker workload, not task-bearing quality evidence."})
    shared = [row for row in rows if row["case_class"] == "same_prefix_pass_pass"]
    dedup = sum(int(row["cache_entries_delta"] or 0) for row in shared) <= max(int(row["commit_tokens"] or 0) // args.block_size for row in shared)
    for row in shared: row["same_prefix_dedup_ok"] = dedup; row["gate_pass"] = bool(row["gate_pass"] and dedup)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"rows": len(rows), "passed": sum(bool(row["gate_pass"]) for row in rows), "policy_hash": policy_hash}, indent=2))
    raise SystemExit(0 if rows and all(row["gate_pass"] for row in rows) else 1)


if __name__ == "__main__":
    main()
