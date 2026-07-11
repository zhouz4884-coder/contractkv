#!/usr/bin/env python3
"""Live vLLM validation for Prefix-Selective Transactional Promotion."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import PSTPSpec, VerifyDecision, build_pstp_spec, write_registry
from scripts.summarize_vllm_prefix_metrics import summarize as summarize_prefix_events


FIELDS = [
    "case_id", "decision", "shadow_success", "marker_ok", "expected_stable_tokens",
    "stable_prefix_end_token", "tokenization_glue_loss", "glue_status", "block_size",
    "commit_tokens", "committed_full_blocks", "discarded_partial_tokens",
    "cache_entries_delta", "visible_blocks_before_finalize", "visible_blocks_after_finalize",
    "candidate_prompt_tokens", "candidate_cached_tokens", "candidate_new_prefill_tokens",
    "inherited_common_tokens", "dynamic_suffix_tokens", "dynamic_suffix_reused_tokens", "stable_probe_reuse_fraction",
    "duplicate_finalize_events", "gate_pass", "error", "claim_boundary",
]


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def tokenize(base_url: str, model: str, messages: list[dict[str, str]], add_generation_prompt: bool, timeout: float) -> list[int]:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    result = post_json(root + "/tokenize", {
        "model": model,
        "messages": messages,
        "add_generation_prompt": add_generation_prompt,
    }, timeout)
    return [int(token) for token in result.get("tokens", [])]


def build_case(case_id: str, glue: bool = False) -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
    nonce = hashlib.sha256(case_id.encode()).hexdigest()[:10]
    stable_text = " ".join(f"{nonce}_stable_{index}" for index in range(420))
    marker = f"PSTP_OK_{case_id}"
    system = {"role": "system", "content": "/no_think Reply with only the requested marker."}
    if glue:
        stable_messages = [system, {"role": "user", "content": stable_text}]
        candidate_messages = [
            system,
            {"role": "user", "content": stable_text + f" dynamic_suffix_{nonce} Return exactly: {marker}"},
        ]
    else:
        stable_messages = [system, {"role": "user", "content": stable_text}]
        candidate_messages = [
            *stable_messages,
            {"role": "user", "content": f"[DYNAMIC_SUFFIX {nonce}] Return exactly this marker: {marker}"},
        ]
    return stable_messages, candidate_messages, marker


def send_chat(base_url: str, model: str, request_id: str, messages: list[dict[str, str]], timeout: float, priority: int = 100) -> dict[str, Any]:
    try:
        response = post_json(base_url.rstrip("/") + "/chat/completions", {
            "model": model, "messages": messages, "max_tokens": 16,
            "temperature": 0, "top_p": 1, "stream": False,
            "request_id": request_id, "priority": priority,
        }, timeout)
        choices = response.get("choices") or []
        text = str(choices[0].get("message", {}).get("content") or "") if choices else ""
        return {"success": bool(text), "output_text": text, "request_id": str(response.get("id", request_id)), "error": ""}
    except Exception as exc:
        return {"success": False, "output_text": "", "request_id": request_id, "error": str(exc)[:400]}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def prefix_by_request(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("request_id")): row for row in summarize_prefix_events(load_jsonl(path))}


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    case_specs = [
        ("pass", VerifyDecision.PASS, False),
        ("fail", VerifyDecision.FAIL, False),
        ("incomplete", VerifyDecision.INCOMPLETE, False),
        ("cancelled", VerifyDecision.CANCELLED, False),
        ("idempotence", VerifyDecision.PASS, False),
        ("glue", VerifyDecision.PASS, True),
    ]
    registry: dict[str, PSTPSpec] = {}
    case_data: dict[str, dict[str, Any]] = {}
    for case_id, decision, glue in case_specs:
        stable_messages, candidate_messages, marker = build_case(case_id, glue)
        stable_ids = tokenize(args.base_url, args.model, stable_messages, False, args.timeout)
        candidate_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
        request_id = f"phase16r-pstp-{case_id}-{time.time_ns()}"
        spec = build_pstp_spec(
            txn_id=f"txn-{case_id}", stable_ids=stable_ids, candidate_ids=candidate_ids,
            verify_decision=decision, block_size=args.block_size,
            failure_reason="harness decision" if decision is not VerifyDecision.PASS else "",
        )
        registry[request_id] = spec
        case_data[case_id] = {
            "request_id": request_id, "spec": spec, "stable_messages": stable_messages,
            "candidate_messages": candidate_messages, "marker": marker,
            "candidate_tokens": len(candidate_ids),
        }
    write_registry(args.registry, registry)

    for case_id, _, _ in case_specs:
        item = case_data[case_id]
        item["shadow"] = send_chat(
            args.base_url, args.model, item["request_id"], item["candidate_messages"], args.timeout,
        )
        time.sleep(0.15)
        if case_id in {"pass", "idempotence", "glue"}:
            item["stable_probe"] = send_chat(
                args.base_url, args.model, f"phase16r-stable-probe-{case_id}-{time.time_ns()}",
                item["stable_messages"], args.timeout, priority=0,
            )
        item["candidate_probe"] = send_chat(
            args.base_url, args.model, f"phase16r-candidate-probe-{case_id}-{time.time_ns()}",
            item["candidate_messages"], args.timeout, priority=0,
        )
        time.sleep(0.15)

    time.sleep(1.0)
    events = load_jsonl(args.event_log)
    metrics = prefix_by_request(args.prefix_metrics_log)
    rows = []
    for case_id, expected_decision, _ in case_specs:
        item = case_data[case_id]
        spec: PSTPSpec = item["spec"]
        request_ids = {item["request_id"], "chatcmpl-" + item["request_id"]}
        finalizes = [event for event in events if event.get("event") == "pstp_finalize" and str(event.get("request_id")) in request_ids]
        duplicates = [event for event in events if event.get("event") == "pstp_finalize_duplicate" and str(event.get("request_id")) in request_ids]
        event = finalizes[-1] if finalizes else {}
        candidate_metric = metrics.get(str(item["candidate_probe"]["request_id"]), {})
        stable_metric = metrics.get(str(item.get("stable_probe", {}).get("request_id", "")), {})
        commit_tokens = int(event.get("commit_tokens", 0) or 0)
        prompt_tokens = int(candidate_metric.get("prompt_tokens", item["candidate_tokens"]) or 0)
        new_prefill = int(candidate_metric.get("new_prefill_tokens", prompt_tokens) or 0)
        cached = int(candidate_metric.get("cached_tokens", max(0, prompt_tokens - new_prefill)) or 0)
        if cached == 0 and new_prefill < prompt_tokens:
            cached = prompt_tokens - new_prefill
        dynamic_tokens = max(0, prompt_tokens - commit_tokens)
        inherited_common = min(cached, args.block_size) if commit_tokens == 0 else 0
        dynamic_reused = max(0, cached - commit_tokens - inherited_common)
        stable_reuse = min(cached, commit_tokens) / max(commit_tokens, 1) if commit_tokens else 0.0
        should_commit = expected_decision is VerifyDecision.PASS and spec.verify_decision is VerifyDecision.PASS
        abort_clean = int(event.get("cache_entries_after", 0) or 0) - int(event.get("cache_entries_before", 0) or 0) == 0
        pass_gate = bool(
            item["shadow"]["success"]
            and item["marker"] in item["shadow"]["output_text"]
            and finalizes
            and (
                (should_commit and event.get("action") == "commit" and commit_tokens % args.block_size == 0 and dynamic_reused <= args.block_size)
                or (not should_commit and event.get("action") == "abort" and abort_clean and cached <= args.block_size)
            )
            and (case_id != "idempotence" or len(duplicates) == 1)
        )
        rows.append({
            "case_id": case_id, "decision": spec.verify_decision.value,
            "shadow_success": item["shadow"]["success"], "marker_ok": item["marker"] in item["shadow"]["output_text"],
            "expected_stable_tokens": spec.expected_stable_tokens,
            "stable_prefix_end_token": spec.stable_prefix_end_token,
            "tokenization_glue_loss": spec.tokenization_glue_loss, "glue_status": spec.glue_status,
            "block_size": event.get("block_size", args.block_size), "commit_tokens": commit_tokens,
            "committed_full_blocks": event.get("committed_full_blocks", 0),
            "discarded_partial_tokens": event.get("discarded_partial_tokens", 0),
            "cache_entries_delta": int(event.get("cache_entries_after", 0) or 0) - int(event.get("cache_entries_before", 0) or 0),
            "visible_blocks_before_finalize": event.get("visible_blocks_before_finalize", ""),
            "visible_blocks_after_finalize": event.get("visible_blocks_after_finalize", ""),
            "candidate_prompt_tokens": prompt_tokens, "candidate_cached_tokens": cached,
            "candidate_new_prefill_tokens": new_prefill, "dynamic_suffix_tokens": dynamic_tokens,
            "inherited_common_tokens": inherited_common,
            "dynamic_suffix_reused_tokens": dynamic_reused,
            "stable_probe_reuse_fraction": round(stable_reuse, 6),
            "duplicate_finalize_events": len(duplicates), "gate_pass": pass_gate,
            "error": item["shadow"]["error"],
            "claim_boundary": "Real vLLM V1 PSTP harness decisions; verifier-to-PSTP automation is deferred to Phase 17.",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8016/v1")
    parser.add_argument("--model", default="qwen3-4b")
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--prefix-metrics-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("results/hard_systems/phase16r_pstp_live_v0.csv"))
    args = parser.parse_args()
    rows = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
