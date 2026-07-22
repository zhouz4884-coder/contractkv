#!/usr/bin/env python3
"""Replay frozen Llama layout qualifications against an SGLang endpoint.

This is deliberately an external-runtime portability experiment.  It consumes
the prospectively frozen L0--L3 family map, but does not claim online
certificate issuance or PSTP inside SGLang.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12_prefix_cache_ab import send_chat_stream
from scripts.phase20a_official_quality import standard_score
from scripts.phase22_llama_broad_analysis import family_key
from scripts.phase22_llama_broad_live import expand_stable_segments, layout_for_level
from scripts.phase19b_end_to_end_live import load_jsonl, messages, turn_case
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))]


def claim_boundary(backend: str, mode: str) -> str:
    if backend.startswith("sglang") and mode in {"frozen", "certified"}:
        return (
            "SGLang RadixAttention with a prospectively frozen Llama layout map; "
            "offline portability only, without online ContractKV certificates or PSTP."
        )
    if backend.startswith("sglang"):
        return "SGLang RadixAttention raw-order baseline; no ContractKV layout or certificate."
    if backend == "lmcache":
        return "Fresh vLLM replay through LMCacheConnectorV1 without CacheBlend segmentation."
    if backend == "blendraw":
        return "Fresh vLLM replay with the frozen CacheBlend separator and blending disabled."
    if backend == "cacheblend":
        return "Fresh vLLM replay with CacheBlend segmentation and blending enabled."
    return "Fresh external-runtime replay under the frozen protocol."


def selected_level(sample: dict[str, Any], mode: str, manifest: dict[str, Any],
                   certificate_levels: dict[str, str]) -> str:
    if mode == "raw":
        return "L0"
    if mode == "certified":
        return certificate_levels.get(str(sample["phase19b_session_id"]), "L0")
    return str(manifest["frozen_family_levels"].get(family_key(sample), "L0"))


def request_messages(case: dict[str, Any], order: list[str], separator: str) -> list[dict[str, str]]:
    if not separator:
        return messages(case, order)
    by_id = {str(segment["segment_id"]): segment for segment in case["segments"]}
    ordered_text = separator.join(str(by_id[segment_id].get("text", "")) for segment_id in order)
    result = quality_messages(case, ordered_text)
    result[0]["content"] = f"[PHASE19B:{case['trajectory_id']}]\n" + result[0]["content"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--qualification-manifest", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--backend-label", required=True)
    parser.add_argument("--mode", choices=("raw", "frozen", "certified"), required=True)
    parser.add_argument("--certificate-source", type=Path)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--stable-word-limit", type=int, default=1500)
    parser.add_argument("--stable-pieces", type=int, default=16)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--slo-ms", type=float, default=1500.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--segment-separator", default="",
                        help="Optional method-required separator inserted between ordered segments.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
    sessions = load_jsonl(args.sessions)
    manifest = json.loads(args.qualification_manifest.read_text(encoding="utf-8"))
    ladder = {str(key): float(value) for key, value in manifest["layout_ladder"].items()}
    certificate_levels: dict[str, str] = {}
    if args.mode == "certified":
        if not args.certificate_source:
            raise ValueError("certified mode requires --certificate-source")
        for row in load_jsonl(args.certificate_source):
            if row.get("row_type") == "canary" and row.get("certificate_issued") is True:
                certificate_levels[str(row["session_id"])] = str(row.get("effective_level", "L0"))
    rows: list[dict[str, Any]] = []
    cohorts = [sessions[index:index + args.concurrency]
               for index in range(0, len(sessions), args.concurrency)]

    for cohort_index, cohort in enumerate(cohorts):
        for turn in range(args.turns):
            jobs: list[tuple[dict[str, Any], str, str, list[dict[str, str]], int]] = []
            for sample in cohort:
                session_id = str(sample["phase19b_session_id"])
                level = selected_level(sample, args.mode, manifest, certificate_levels)
                case = expand_stable_segments(
                    turn_case(sample, turn, args.stable_word_limit), args.stable_pieces)
                layout = layout_for_level(case, level, ladder)
                rendered_messages = request_messages(
                    case, layout["topological_order"], args.segment_separator)
                prompt_tokens = len(tokenizer.apply_chat_template(
                    rendered_messages, tokenize=True, add_generation_prompt=True))
                jobs.append((sample, session_id, level, rendered_messages, prompt_tokens))

            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {
                    pool.submit(send_chat_stream, args.base_url, args.model, request_messages,
                                args.max_tokens, args.timeout,
                                f"external-{args.backend_label}-{session_id}-t{turn}"):
                    (sample, session_id, level, prompt_tokens)
                    for sample, session_id, level, request_messages, prompt_tokens in jobs
                }
                batch_rows: list[dict[str, Any]] = []
                for future in as_completed(futures):
                    sample, session_id, level, prompt_tokens = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # The failure is a datapoint, not a silent retry.
                        result = {"success": False, "error_type": type(exc).__name__,
                                  "error_message": str(exc)}
                    score, metric, scoring_error = standard_score(
                        str(sample.get("dataset", "")), str(sample.get("task", "")),
                        str(result.get("output_text", "")), sample.get("answer", ""))
                    batch_rows.append({
                        "backend": args.backend_label,
                        "policy": "raw-order" if args.mode == "raw" else (
                            "offline-vllm-certified-layout" if args.mode == "certified" else "offline-frozen-ladder"),
                        "effective_level": level,
                        "qualified_family": level != "L0",
                        "session_id": session_id, "dataset": sample.get("dataset"),
                        "task": sample.get("task"), "sample_id": sample.get("sample_id"),
                        "turn_id": turn, "row_type": "warmup" if turn == 0 else "future",
                        "success": bool(result.get("success", False)),
                        "ttft_ms": float(result.get("ttft_ms", 0.0) or 0.0),
                        "tpot_ms": float(result.get("tpot_ms", 0.0) or 0.0),
                        "latency_ms": float(result.get("total_latency_ms", 0.0) or 0.0),
                        "prompt_tokens": prompt_tokens,
                        "output_tokens": int(result.get("output_tokens", 0) or 0),
                        "task_score": score, "task_metric": metric,
                        "scoring_error": scoring_error,
                        "cached_tokens": result.get("cached_tokens", ""),
                        "cached_tokens_observable": bool(result.get("cached_tokens_observable", False)),
                        "segment_separator": args.segment_separator,
                        "error_type": result.get("error_type", "none"),
                        "error_message": result.get("error_message", ""),
                        "claim_boundary": claim_boundary(args.backend_label, args.mode),
                    })
            batch_wall_ms = (time.perf_counter() - started) * 1000.0
            batch_id = f"{args.backend_label}-c{cohort_index}-t{turn}"
            for row in batch_rows:
                row["batch_id"] = batch_id
                row["batch_wall_ms"] = batch_wall_ms
            rows.extend(batch_rows)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    future = [row for row in rows if row["row_type"] == "future"]
    successful = [row for row in future if row["success"]]
    ttft = [float(row["ttft_ms"]) for row in successful]
    tpot = [float(row["tpot_ms"]) for row in successful]
    batch_wall: dict[str, float] = {}
    for row in successful:
        batch_wall[row["batch_id"]] = max(batch_wall.get(row["batch_id"], 0.0), float(row["batch_wall_ms"]))
    wall_s = sum(batch_wall.values()) / 1000.0
    summary = {
        "backend": args.backend_label, "policy": args.mode,
        "sessions": len(sessions), "future_requests": len(future),
        "completed_requests": len(successful),
        "completion_rate": len(successful) / max(1, len(future)),
        "mean_ttft_ms": statistics.fmean(ttft) if ttft else 0.0,
        "p95_ttft_ms": percentile(ttft, 0.95),
        "mean_tpot_ms": statistics.fmean(tpot) if tpot else 0.0,
        "p95_tpot_ms": percentile(tpot, 0.95),
        "mean_latency_ms": statistics.fmean(float(row["latency_ms"]) for row in successful) if successful else 0.0,
        "mean_prompt_tokens": statistics.fmean(float(row["prompt_tokens"]) for row in successful) if successful else 0.0,
        "mean_task_score": statistics.fmean(float(row["task_score"]) for row in successful) if successful else 0.0,
        "qualified_future_fraction": (sum(bool(row["qualified_family"]) for row in future) / max(1, len(future))),
        "slo_ms": args.slo_ms,
        "slo_compliant_requests": sum(value <= args.slo_ms for value in ttft),
        "slo_compliant_req_per_sec": sum(value <= args.slo_ms for value in ttft) / max(wall_s, 1e-9),
        "claim_boundary": claim_boundary(args.backend_label, args.mode),
    }
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
