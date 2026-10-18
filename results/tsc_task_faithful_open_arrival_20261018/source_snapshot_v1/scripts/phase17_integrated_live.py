#!/usr/bin/env python3
"""Live VerifyReport -> PSTP -> certificate integration probe."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_transaction import PSTPRuntime, write_runtime_registry
from scripts.phase17_live_common import build_layout, build_live_smoke_policy, build_runtime, generate_raw, post_json, tokenize
from scripts.summarize_vllm_prefix_metrics import summarize as summarize_prefix_events


FIELDS = [
    "case_id", "case_type", "txn_id", "verify_decision", "txn_state",
    "failure_reason", "robustness_reserve", "stable_prefix_end_token",
    "commit_tokens", "committed_full_blocks", "cache_entries_delta",
    "certificate_issued", "certificate_after_commit", "candidate_prompt_tokens",
    "probe_cached_tokens", "stable_reuse_fraction", "dynamic_suffix_reused_tokens",
    "duplicate_finalize_events", "marker_ok", "gate_pass", "error",
    "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def send_candidate(args: argparse.Namespace, request_id: str, prompt_ids: list[int]) -> dict[str, Any]:
    return post_json(args.base_url.rstrip("/") + "/completions", {
        "model": args.model, "prompt": prompt_ids, "max_tokens": 1,
        "temperature": 0, "stream": False, "prompt_logprobs": 2,
        "return_token_ids": True, "request_id": request_id, "priority": 100,
    }, args.timeout)


def send_probe(args: argparse.Namespace, request_id: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    return post_json(args.base_url.rstrip("/") + "/chat/completions", {
        "model": args.model, "messages": messages, "max_tokens": 16,
        "temperature": 0, "stream": False, "request_id": request_id,
    }, args.timeout)


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    cases = [(f"safe-{index}", False) for index in range(args.safe_cases)]
    cases += [(f"conflict-{index}", True) for index in range(args.conflict_cases)]
    thresholds = {"tau_raw": args.tau_raw, "tau_abs": args.tau_abs, "tau_drop": args.tau_drop}
    frozen_policy, identity = build_live_smoke_policy(args.model_id, args.model_path, args.vllm_version, thresholds)
    from scripts.contractkv_frozen_policy import policy_hash
    registry: dict[str, PSTPRuntime] = {}
    prepared = []
    for case_id, conflict in cases:
        layout = build_layout(case_id, conflict=conflict)
        raw = generate_raw(args.base_url, args.model, f"phase17-raw-{case_id}", layout["raw_messages"], args.timeout)
        stable_ids = tokenize(args.base_url, args.model, layout["stable_messages"], False, args.timeout)
        candidate_ids = tokenize(args.base_url, args.model, layout["candidate_messages"], True, args.timeout)
        request_id = f"phase17-candidate-{case_id}"
        runtime = build_runtime(
            txn_id=f"txn-{case_id}", stable_ids=stable_ids,
            candidate_prompt_ids=candidate_ids, raw=raw,
            stop_token_id=args.stop_token_id,
            thresholds=thresholds,
            candidate_messages=layout["candidate_messages"],
            frozen_policy=frozen_policy, frozen_policy_hash=policy_hash(frozen_policy), runtime_identity=identity,
        )
        registry[request_id] = runtime
        prepared.append((case_id, conflict, request_id, layout, raw, candidate_ids, runtime))
    write_runtime_registry(args.registry, registry)

    responses = {}
    probes = {}
    for case_id, _, request_id, layout, raw, candidate_ids, _ in prepared:
        forced = candidate_ids + raw["token_ids"] + [raw["terminal_stop_token_id"]]
        try:
            responses[case_id] = send_candidate(args, request_id, forced)
        except Exception as exc:
            responses[case_id] = {"error": str(exc)}
        time.sleep(.1)
        probe_id = f"phase17-probe-{case_id}-{time.time_ns()}"
        try:
            probes[case_id] = (probe_id, send_probe(args, probe_id, layout["candidate_messages"]))
        except Exception as exc:
            probes[case_id] = (probe_id, {"error": str(exc)})
    time.sleep(1)

    events = load_jsonl(args.event_log)
    prefix = {str(row.get("request_id")): row for row in summarize_prefix_events(load_jsonl(args.prefix_metrics_log))}
    rows = []
    for case_id, conflict, request_id, layout, raw, candidate_ids, runtime in prepared:
        request_ids = {request_id, "cmpl-" + request_id, "cmpl-" + request_id + "-0"}
        verify = [event for event in events if event.get("event") == "phase17_verify_report" and str(event.get("request_id")) in request_ids]
        finalize = [event for event in events if event.get("event") == "phase17_pstp_finalize" and str(event.get("request_id")) in request_ids]
        certificate = [event for event in events if event.get("event") == "phase17_certificate" and str(event.get("request_id")) in request_ids]
        duplicates = [event for event in events if event.get("event") == "phase17_finalize_duplicate" and str(event.get("request_id")) in request_ids]
        report = verify[-1] if verify else {}
        final = finalize[-1] if finalize else {}
        probe_id, probe_response = probes[case_id]
        metric = prefix.get(probe_id) or prefix.get("chatcmpl-" + probe_id) or {}
        prompt_tokens = int(metric.get("prompt_tokens", len(candidate_ids)) or 0)
        new_prefill = int(metric.get("new_prefill_tokens", prompt_tokens) or 0)
        cached = max(0, prompt_tokens - new_prefill)
        commit = int(final.get("commit_tokens", 0) or 0)
        dynamic_reuse = max(0, cached - commit - (args.block_size if commit == 0 else 0))
        should_commit = not conflict and report.get("decision") == "PASS" and float(report.get("robustness_reserve", -1)) >= 0
        marker_ok = layout["marker"] in raw["text"]
        gate = bool(
            marker_ok and finalize and
            ((should_commit and final.get("txn_state") == "COMMITTED" and certificate and commit % args.block_size == 0 and dynamic_reuse == 0)
             or (not should_commit and final.get("txn_state") == "ABORTED" and int(final.get("cache_entries_delta", 0)) == 0 and not certificate))
        )
        cert_after = bool(certificate and float(certificate[-1].get("timestamp", 0)) >= float(final.get("timestamp", 0)))
        rows.append({
            "case_id": case_id, "case_type": "conflict" if conflict else "safe",
            "txn_id": runtime.plan.txn_id, "verify_decision": report.get("decision", "MISSING"),
            "txn_state": final.get("txn_state", "MISSING"),
            "failure_reason": report.get("failure_reason", final.get("failure_reason", "")),
            "robustness_reserve": report.get("robustness_reserve", ""),
            "stable_prefix_end_token": runtime.plan.stable_prefix_end_token,
            "commit_tokens": commit, "committed_full_blocks": final.get("committed_full_blocks", 0),
            "cache_entries_delta": final.get("cache_entries_delta", ""),
            "certificate_issued": bool(certificate), "certificate_after_commit": cert_after,
            "candidate_prompt_tokens": prompt_tokens, "probe_cached_tokens": cached,
            "stable_reuse_fraction": min(cached, commit) / max(commit, 1) if commit else 0,
            "dynamic_suffix_reused_tokens": dynamic_reuse,
            "duplicate_finalize_events": len(duplicates), "marker_ok": marker_ok,
            "gate_pass": gate, "error": responses[case_id].get("error", probe_response.get("error", "")),
            "claim_boundary": "Live vLLM EngineCore VerifyReport drives PSTP; compact marker workload, not task-bearing equivalence.",
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8017/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--model-id", default="qwen3-4b")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--vllm-version", default="0.10.2")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--prefix-metrics-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--safe-cases", type=int, default=12)
    parser.add_argument("--conflict-cases", type=int, default=4)
    parser.add_argument("--stop-token-id", type=int, default=151645)
    parser.add_argument("--tau-raw", type=float, default=0)
    parser.add_argument("--tau-abs", type=float, default=0)
    parser.add_argument("--tau-drop", type=float, default=4)
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    rows = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"rows": len(rows), "passed": sum(row["gate_pass"] for row in rows)}, indent=2))
    return 0 if rows and all(row["gate_pass"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
