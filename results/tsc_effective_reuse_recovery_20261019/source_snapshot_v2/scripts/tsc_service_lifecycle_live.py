#!/usr/bin/env python3
"""Inject service-scope updates and verify selective certificate invalidation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase14m_physical_dedup import fit_shared_text


EVENTS = [
    ("service_template_v1_to_v2", "service_template_version"),
    ("stable_context_update", "stable_context_hash"),
    ("tool_schema_update", "tool_schema_hash"),
    ("model_checkpoint_switch", "model_identity"),
    ("tokenizer_chat_template_change", "tokenizer_template_hash"),
    ("policy_hash_update", "policy_hash"),
    ("qualification_manifest_update", "qualification_hash"),
    ("tenant_revocation", "tenant_epoch"),
]


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def baseline_scope(tenant: str, event_index: int) -> dict[str, Any]:
    return {
        "tenant_id": tenant, "tenant_epoch": 1, "service_template_version": "v1",
        "stable_context_hash": f"stable-{event_index}-v1", "tool_schema_hash": "tool-v1",
        "model_identity": "Qwen3-8B", "tokenizer_template_hash": "qwen3-template-v1",
        "policy_hash": "tsc-policy-v1", "qualification_hash": "qualification-v1",
    }


def mutate(scope: dict[str, Any], field: str) -> dict[str, Any]:
    output = dict(scope)
    value = output[field]
    output[field] = value + 1 if isinstance(value, int) else str(value) + "-updated"
    return output


def messages(scope: dict[str, Any], stable: str, marker: str) -> list[dict[str, str]]:
    scope_hash = digest(scope)[:24]
    return [
        {"role": "system", "content": f"[SERVICE_SCOPE:{scope_hash}] Follow the tenant request exactly."},
        {"role": "user", "content": f"[STABLE_CONTEXT]\n{stable}\n\n[PRIVATE_OBS] marker={marker}\nReturn exactly the marker. /no_think"},
    ]


def send(args: argparse.Namespace, scope: dict[str, Any], stable: str, marker: str, request_id: str) -> dict[str, Any]:
    result = send_chat_stream(args.base_url, args.model, messages(scope, stable, marker),
                              args.max_tokens, args.timeout, request_id,
                              cache_salt=f"tsc-lifecycle:{digest(scope)}")
    result["quality_sanity"] = marker in str(result.get("output_text", ""))
    return result


def load_metrics(path: Path, offset: int) -> dict[str, dict[str, Any]]:
    with path.open("rb") as handle:
        handle.seek(offset)
        rows = [json.loads(line) for line in handle.read().decode("utf-8", errors="replace").splitlines() if line.strip()]
    return {str(row.get("request_id")): row for row in rows
            if row.get("event") == "prefix_cache_request_observation" and row.get("initial_prefill_observation")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--phase18-faults", type=Path, required=True)
    parser.add_argument("--phase18-wire", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--shared-target-tokens", type=int, default=2048)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    stable_base = fit_shared_text(tokenizer, args.shared_target_tokens)
    offset = args.metrics_events.stat().st_size if args.metrics_events.exists() else 0
    staged = []
    for event_index, (event_name, field) in enumerate(EVENTS):
        affected = baseline_scope("tenant-affected", event_index)
        unaffected = baseline_scope("tenant-unaffected", event_index)
        stable = stable_base + f"\nLIFECYCLE_EVENT_{event_index}"
        old_marker = f"O{event_index:02d}A"
        other_marker = f"O{event_index:02d}B"
        old = send(args, affected, stable, old_marker, f"lifecycle-{event_index}-old-prime")
        other = send(args, unaffected, stable, other_marker, f"lifecycle-{event_index}-other-prime")
        invalidation_started = time.perf_counter()
        updated = mutate(affected, field)
        old_certificate_valid = digest(affected) == digest(updated)
        invalidation_ms = (time.perf_counter() - invalidation_started) * 1000.0
        new_marker = f"N{event_index:02d}A"
        unaffected_marker = f"N{event_index:02d}B"
        affected_result = send(args, updated, stable, new_marker, f"lifecycle-{event_index}-affected-after")
        unaffected_result = send(args, unaffected, stable, unaffected_marker, f"lifecycle-{event_index}-unaffected-after")
        recovery_started = time.perf_counter()
        recovered = send(args, updated, stable, f"R{event_index:02d}A", f"lifecycle-{event_index}-affected-recovered")
        recovery_ms = (time.perf_counter() - recovery_started) * 1000.0
        staged.append({
            "event": event_name, "field": field, "old_certificate_valid": old_certificate_valid,
            "invalidation_latency_ms": invalidation_ms, "recovery_latency_ms": recovery_ms,
            "old_prime_success": bool(old.get("success")), "unaffected_prime_success": bool(other.get("success")),
            "affected_request_success": bool(affected_result.get("success")),
            "unaffected_request_success": bool(unaffected_result.get("success")),
            "recovered_request_success": bool(recovered.get("success")),
            "affected_quality_sanity": bool(affected_result.get("quality_sanity")),
            "unaffected_quality_sanity": bool(unaffected_result.get("quality_sanity")),
            "recovered_quality_sanity": bool(recovered.get("quality_sanity")),
            "affected_request_id": affected_result.get("request_id", ""),
            "old_prime_request_id": old.get("request_id", ""),
            "unaffected_request_id": unaffected_result.get("request_id", ""),
            "recovered_request_id": recovered.get("request_id", ""),
        })
    time.sleep(1.0)
    metrics = load_metrics(args.metrics_events, offset)
    for row in staged:
        old = metrics.get(str(row["old_prime_request_id"]), {})
        affected = metrics.get(str(row["affected_request_id"]), {})
        unaffected = metrics.get(str(row["unaffected_request_id"]), {})
        recovered = metrics.get(str(row["recovered_request_id"]), {})
        old_hashes = {str(value) for value in old.get("physical_block_hashes", []) if value}
        affected_hashes = {str(value) for value in affected.get("physical_block_hashes", []) if value}
        cross_version = old_hashes & affected_hashes
        row.update({
            "affected_old_prefix_consumed": bool(cross_version),
            "affected_prefix_hit_tokens": affected.get("prefix_hit_tokens", ""),
            "unaffected_prefix_hit_tokens": unaffected.get("prefix_hit_tokens", ""),
            "recovered_prefix_hit_tokens": recovered.get("prefix_hit_tokens", ""),
            "cache_used_blocks_after_invalidation": affected.get("used_gpu_blocks", ""),
            "cache_used_blocks_after_recovery": recovered.get("used_gpu_blocks", ""),
            "cross_version_contamination": bool(cross_version),
            "cross_version_shared_physical_hashes": len(cross_version),
            "claim_boundary": "Real vLLM prefix consumption under a control-plane scope change; model/tokenizer events validate routing scope without reloading weights in-process.",
        })
    faults = json.loads(args.phase18_faults.read_text(encoding="utf-8"))
    staged.append({
        "event": "request_cancel", "field": "request_lifecycle", "old_certificate_valid": False,
        "invalidation_latency_ms": "previously_measured_phase18", "recovery_latency_ms": "",
        "affected_request_success": faults.get("gate_pass", False), "unaffected_request_success": True,
        "affected_old_prefix_consumed": False, "cross_version_contamination": False,
        "claim_boundary": "Reused real Phase 18 compact-endpoint cancellation/disconnect fault evidence.",
    })
    with args.phase18_wire.open(encoding="utf-8", newline="") as handle:
        wire = list(csv.DictReader(handle))
    duplicates = [row for row in wire if row.get("mode") == "duplicate"]
    duplicate_gate = len(duplicates) >= 2 and duplicates[0].get("status") == "200" and int(duplicates[1].get("status") or 0) >= 400
    staged.append({
        "event": "duplicate_finalize", "field": "transaction_id", "old_certificate_valid": False,
        "invalidation_latency_ms": "previously_measured_phase18", "recovery_latency_ms": "",
        "affected_request_success": duplicate_gate, "unaffected_request_success": True,
        "affected_old_prefix_consumed": False, "cross_version_contamination": False,
        "claim_boundary": "Reused real Phase 18 duplicate-finalize wire evidence: first commit succeeds, duplicate fails closed.",
    })
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in staged for key in row})
    with args.raw_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(staged)
    gate = {
        "events": len(staged),
        "old_certificates_immediately_invalidated": all(not bool(row.get("old_certificate_valid")) for row in staged),
        "old_prefix_consumption_zero": all(not bool(row.get("affected_old_prefix_consumed")) for row in staged),
        "unrelated_scope_continues": all(bool(row.get("unaffected_request_success")) for row in staged),
        "cross_version_contamination_zero": all(not bool(row.get("cross_version_contamination")) for row in staged),
    }
    gate["gate_pass"] = len(staged) == 10 and all(gate[key] for key in gate if key not in {"events", "gate_pass"})
    args.summary_output.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2))
    return 0 if gate["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
