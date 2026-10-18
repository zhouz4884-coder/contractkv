#!/usr/bin/env python3
"""Real vLLM cache-state conflict between static and residency-aware layouts."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import percentile, send_chat_stream
from scripts.phase14m_physical_dedup import fit_shared_text
from scripts.summarize_vllm_prefix_metrics import summarize as summarize_metrics

POLICIES = ("raw-order", "static-posc", "logical-ledger-caposc", "physical-residency-caposc")
RAW_FIELDS = [
    "seed", "policy", "turn_id", "selected_layout", "request_id", "success",
    "quality_sanity", "ttft_ms", "tpot_ms", "latency_ms", "prompt_tokens",
    "prefix_hit_tokens", "new_prefill_tokens", "used_gpu_blocks", "free_gpu_blocks",
    "physical_feedback_available", "residency_prediction_blocks", "residency_error_blocks",
    "claim_boundary",
]
SUMMARY_FIELDS = [
    "seed", "policy", "turns", "completion_rate", "quality_sanity_rate",
    "mean_ttft_ms", "p95_ttft_ms", "mean_prefix_hit_tokens", "mean_new_prefill_tokens",
    "used_block_high_water", "physical_feedback_rate", "within_one_block_rate",
    "claim_boundary",
]


def load_events(path: Path, offset: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        handle.seek(offset)
        payload = handle.read().decode("utf-8", errors="replace")
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def messages_for(layout: str, component_a: str, component_b: str, marker: str, turn_id: int) -> list[dict[str, str]]:
    system = "Return exactly the requested marker. /no_think"
    a = f"[CODEBASE_A]\n{component_a}"
    b = f"[DOCUMENT_B]\n{component_b}"
    obs = f"[TOOL_OBS] turn={turn_id}; marker={marker}; status=ok."
    query = "Return exactly marker from TOOL_OBS."
    if layout == "a-first":
        content = f"{a}\n\n{b}\n\n{obs}\n\n{query}"
    elif layout == "b-first":
        content = f"{b}\n\n{a}\n\n{obs}\n\n{query}"
    else:
        content = f"{obs}\n\n{a}\n\n{b}\n\n{query}"
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


def choose_layout(policy: str, physical_a_resident: bool) -> str:
    if policy == "raw-order":
        return "raw"
    if policy in {"static-posc", "logical-ledger-caposc"}:
        return "b-first"
    return "a-first" if physical_a_resident else "b-first"


def predicted_common_prefix_blocks(tokenizer: Any, warm_messages: list[dict[str, str]], candidate_messages: list[dict[str, str]], block_size: int = 16) -> int:
    warm_ids = tokenizer.apply_chat_template(warm_messages, tokenize=True, add_generation_prompt=True)
    candidate_ids = tokenizer.apply_chat_template(candidate_messages, tokenize=True, add_generation_prompt=True)
    matched = 0
    for left, right in zip(warm_ids, candidate_ids):
        if left != right:
            break
        matched += 1
    return matched // block_size


def join(rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
    metrics = {str(item.get("request_id")): item for item in summarize_metrics(events)}
    observations: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("event") == "prefix_cache_request_observation":
            observations.setdefault(str(event.get("request_id")), []).append(event)
    for row in rows:
        metric = metrics.get(str(row["request_id"]), {})
        group = observations.get(str(row["request_id"]), [])
        initial = next((event for event in group if event.get("initial_prefill_observation")), {})
        row.update({
            "prompt_tokens": metric.get("prompt_tokens", ""),
            "prefix_hit_tokens": metric.get("prefix_hit_tokens", ""),
            "new_prefill_tokens": metric.get("new_prefill_tokens", ""),
            "used_gpu_blocks": max((int(event.get("used_gpu_blocks") or 0) for event in group), default=0),
            "free_gpu_blocks": min((int(event.get("free_gpu_blocks") or 0) for event in group), default=0),
            "physical_feedback_available": bool(initial.get("physical_block_hashes")),
        })
        predicted = int(row.get("residency_prediction_blocks") or 0)
        actual = int(float(metric.get("prefix_hit_tokens") or 0)) // 16
        row["residency_error_blocks"] = abs(predicted - actual)


def summarize(rows: list[dict[str, Any]], seed: int, policy: str) -> dict[str, Any]:
    success = [row for row in rows if row.get("success")]
    ttft = [float(row["ttft_ms"]) for row in success]
    errors = [int(row.get("residency_error_blocks") or 0) for row in success]
    return {
        "seed": seed, "policy": policy, "turns": len(rows),
        "completion_rate": len(success) / len(rows) if rows else 0.0,
        "quality_sanity_rate": sum(bool(row.get("quality_sanity")) for row in success) / len(success) if success else 0.0,
        "mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0, "p95_ttft_ms": percentile(ttft, .95),
        "mean_prefix_hit_tokens": statistics.mean(float(row.get("prefix_hit_tokens") or 0) for row in success) if success else 0.0,
        "mean_new_prefill_tokens": statistics.mean(float(row.get("new_prefill_tokens") or 0) for row in success) if success else 0.0,
        "used_block_high_water": max((int(row.get("used_gpu_blocks") or 0) for row in success), default=0),
        "physical_feedback_rate": sum(bool(row.get("physical_feedback_available")) for row in success) / len(success) if success else 0.0,
        "within_one_block_rate": sum(error <= 1 for error in errors) / len(errors) if errors else 0.0,
        "claim_boundary": "Real cache-state conflict with prior request physical feedback; not a general pre-request multi-candidate residency RPC.",
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=POLICIES, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--component-tokens", type=int, default=2048)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    component_a = fit_shared_text(tokenizer, args.component_tokens)
    offset = args.metrics_events.stat().st_size if args.metrics_events.exists() else 0
    warm_messages = messages_for("a-first", component_a, "initial documentation", "WARM", -1)
    warm = send_chat_stream(args.base_url, args.model, warm_messages, 32, 240, f"phase15c-{args.seed}-{args.policy}-warm")
    if not warm.get("success"):
        raise SystemExit(f"warm request failed: {warm.get('error_message')}")
    time.sleep(.2)
    warm_events = load_events(args.metrics_events, offset)
    warm_observation = next((event for event in warm_events if event.get("request_id") == warm.get("request_id") and event.get("physical_block_hashes")), None)
    physical_a_resident = warm_observation is not None
    rows = []
    for turn in range(args.turns):
        marker = f"M{turn}X"
        component_b = f"unique_epoch_{args.seed}_{turn} " + fit_shared_text(tokenizer, args.component_tokens - 8)
        layout = choose_layout(args.policy, physical_a_resident)
        request_messages = messages_for(layout, component_a, component_b, marker, turn)
        predicted_blocks = predicted_common_prefix_blocks(tokenizer, warm_messages, request_messages) if args.policy == "physical-residency-caposc" and physical_a_resident else 0
        result = send_chat_stream(args.base_url, args.model, request_messages, 32, 240, f"phase15c-{args.seed}-{args.policy}-{turn}")
        rows.append({
            "seed": args.seed, "policy": args.policy, "turn_id": turn, "selected_layout": layout,
            "request_id": result.get("request_id", ""), "success": result.get("success", False),
            "quality_sanity": marker in str(result.get("output_text", "")), "ttft_ms": result.get("ttft_ms", 0),
            "tpot_ms": result.get("tpot_ms", 0), "latency_ms": result.get("total_latency_ms", 0),
            "residency_prediction_blocks": predicted_blocks,
            "claim_boundary": "Real vLLM endpoint conflict; physical policy uses confirmed prior A-first residency.",
        })
    time.sleep(.5)
    join(rows, load_events(args.metrics_events, offset))
    write_csv(args.raw_output, rows, RAW_FIELDS)
    write_csv(args.summary_output, [summarize(rows, args.seed, args.policy)], SUMMARY_FIELDS)
    print(json.dumps(summarize(rows, args.seed, args.policy), indent=2))
    return 0 if all(row.get("success") and row.get("quality_sanity") for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
