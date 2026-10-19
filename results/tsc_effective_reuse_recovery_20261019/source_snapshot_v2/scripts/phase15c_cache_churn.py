#!/usr/bin/env python3
"""Candidate-level physical residency selection after vLLM cache churn."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase14m_physical_dedup import fit_shared_text
from scripts.phase15c_cache_state_conflict import load_events, messages_for, predicted_common_prefix_blocks
from scripts.summarize_vllm_prefix_metrics import summarize as summarize_metrics

FIELDS = [
    "seed", "cycle", "query_id", "cache_epoch", "pollution_requests",
    "a_resident_blocks", "b_resident_blocks", "selected_layout", "stale_layout",
    "switched_after_eviction", "request_id", "success", "quality_sanity",
    "predicted_hit_blocks", "actual_hit_blocks", "residency_error_blocks",
    "ttft_ms", "new_prefill_tokens", "continuous_stale_selections", "claim_boundary",
]


def candidate_hashes(events: list[dict[str, Any]], request_id: str) -> list[str]:
    observations = [
        event for event in events
        if event.get("event") == "prefix_cache_request_observation"
        and str(event.get("request_id")) == request_id
    ]
    for event in reversed(observations):
        hashes = [str(item) for item in event.get("physical_block_hashes", []) if item]
        if hashes:
            return hashes
    return []


def write_query(path: Path, query: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(query), encoding="utf-8")
    os.replace(temporary, path)


def query_residency(
    query_path: Path,
    result_path: Path,
    base_url: str,
    model: str,
    seed: int,
    cycle: int,
    candidates: list[dict[str, Any]],
    timeout: float = 10.0,
) -> dict[str, Any]:
    query_id = f"phase15c2-{seed}-{cycle}-{uuid.uuid4().hex[:8]}"
    write_query(query_path, {"query_id": query_id, "candidates": candidates})
    heartbeat = [{"role": "user", "content": f"/no_think Reply OK. heartbeat={query_id}"}]
    result = send_chat_stream(base_url, model, heartbeat, 4, 60, query_id)
    if not result.get("success"):
        raise RuntimeError(f"residency heartbeat failed: {result.get('error_message')}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if result_path.exists():
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            if str(payload.get("query_id")) == query_id:
                return payload
        time.sleep(.05)
    raise TimeoutError(f"candidate residency query timed out: {query_id}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--component-tokens", type=int, default=2048)
    parser.add_argument("--pollution-tokens", type=int, default=6000)
    parser.add_argument("--max-pollution", type=int, default=12)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--query-path", type=Path, required=True)
    parser.add_argument("--query-result-path", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    component_a = fit_shared_text(tokenizer, args.component_tokens)
    component_b = "stable documentation " + fit_shared_text(tokenizer, args.component_tokens - 4)
    rows: list[dict[str, Any]] = []
    stale_run = 0
    for cycle in range(args.cycles):
        offset = args.metrics_events.stat().st_size if args.metrics_events.exists() else 0
        warm_a_messages = messages_for("a-first", component_a, component_b, "WARM", -1)
        warm_b_messages = messages_for("b-first", component_a, component_b, "WARM", -1)
        warm_a = send_chat_stream(args.base_url, args.model, warm_a_messages, 8, 240, f"phase15c2-{args.seed}-{cycle}-warm-a")
        warm_b = send_chat_stream(args.base_url, args.model, warm_b_messages, 8, 240, f"phase15c2-{args.seed}-{cycle}-warm-b")
        if not warm_a.get("success") or not warm_b.get("success"):
            raise RuntimeError("candidate warm request failed")
        time.sleep(.2)
        events = load_events(args.metrics_events, offset)
        a_hashes = candidate_hashes(events, str(warm_a.get("request_id")))
        b_hashes = candidate_hashes(events, str(warm_b.get("request_id")))
        if not a_hashes or not b_hashes:
            raise RuntimeError("native candidate block hashes unavailable")

        marker = f"C{args.seed}X{cycle}"
        final_a = messages_for("a-first", component_a, component_b, marker, cycle)
        final_b = messages_for("b-first", component_a, component_b, marker, cycle)
        a_blocks = predicted_common_prefix_blocks(tokenizer, warm_a_messages, final_a)
        b_blocks = predicted_common_prefix_blocks(tokenizer, warm_b_messages, final_b)
        candidate_payload = [
            {"candidate_id": "a-first", "block_hashes": a_hashes[:a_blocks]},
            {"candidate_id": "b-first", "block_hashes": b_hashes[:b_blocks]},
        ]

        query = query_residency(
            args.query_path, args.query_result_path, args.base_url, args.model,
            args.seed, cycle, candidate_payload,
        )
        pollution = 0
        while pollution < args.max_pollution:
            by_id = {item["candidate_id"]: item for item in query["candidates"]}
            if int(by_id["b-first"]["resident_prefix_blocks"]) > int(by_id["a-first"]["resident_prefix_blocks"]):
                break
            pollution_text = (
                f"/no_think pollution seed={args.seed} cycle={cycle} n={pollution}\n"
                + fit_shared_text(tokenizer, args.pollution_tokens - 16)
            )
            pollute = send_chat_stream(
                args.base_url, args.model, [{"role": "user", "content": pollution_text}],
                4, 240, f"phase15c2-{args.seed}-{cycle}-pollute-{pollution}",
            )
            if not pollute.get("success"):
                raise RuntimeError("pollution request failed")
            # Keep B hot while A ages out of the physical block pool.
            refresh = send_chat_stream(
                args.base_url, args.model, warm_b_messages, 4, 240,
                f"phase15c2-{args.seed}-{cycle}-refresh-b-{pollution}",
            )
            if not refresh.get("success"):
                raise RuntimeError("B refresh failed")
            pollution += 1
            query = query_residency(
                args.query_path, args.query_result_path, args.base_url, args.model,
                args.seed, cycle, candidate_payload,
            )

        by_id = {item["candidate_id"]: item for item in query["candidates"]}
        a_resident = int(by_id["a-first"]["resident_prefix_blocks"])
        b_resident = int(by_id["b-first"]["resident_prefix_blocks"])
        selected = "b-first" if b_resident > a_resident else "a-first"
        switched = selected != "a-first" and b_resident > a_resident
        stale_run = stale_run + 1 if selected == "a-first" and b_resident > a_resident else 0
        selected_messages = final_b if selected == "b-first" else final_a
        before_final = args.metrics_events.stat().st_size
        result = send_chat_stream(
            args.base_url, args.model, selected_messages, 16, 240,
            f"phase15c2-{args.seed}-{cycle}-selected",
        )
        time.sleep(.2)
        final_events = load_events(args.metrics_events, before_final)
        metric = next((item for item in summarize_metrics(final_events) if item.get("request_id") == result.get("request_id")), {})
        predicted = b_resident if selected == "b-first" else a_resident
        actual = int(float(metric.get("prefix_hit_tokens") or 0)) // 16
        rows.append({
            "seed": args.seed, "cycle": cycle, "query_id": query.get("query_id", ""),
            "cache_epoch": query.get("cache_epoch", ""), "pollution_requests": pollution,
            "a_resident_blocks": a_resident, "b_resident_blocks": b_resident,
            "selected_layout": selected, "stale_layout": "a-first",
            "switched_after_eviction": switched, "request_id": result.get("request_id", ""),
            "success": result.get("success", False), "quality_sanity": marker in str(result.get("output_text", "")),
            "predicted_hit_blocks": predicted, "actual_hit_blocks": actual,
            "residency_error_blocks": abs(predicted - actual), "ttft_ms": result.get("ttft_ms", 0),
            "new_prefill_tokens": metric.get("new_prefill_tokens", ""),
            "continuous_stale_selections": stale_run,
            "claim_boundary": "Read-only candidate-level vLLM native block-hash residency RPC; no KV placement mutation.",
        })
        write_csv(args.output, rows)
    print(json.dumps({
        "rows": len(rows),
        "switch_rate": sum(bool(row["switched_after_eviction"]) for row in rows) / len(rows),
        "within_one_block_rate": sum(int(row["residency_error_blocks"]) <= 1 for row in rows) / len(rows),
        "max_continuous_stale": max(int(row["continuous_stale_selections"]) for row in rows),
        "quality_sanity_rate": sum(bool(row["quality_sanity"]) for row in rows) / len(rows),
    }, indent=2))
    return 0 if all(row["success"] and row["quality_sanity"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
