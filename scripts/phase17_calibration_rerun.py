#!/usr/bin/env python3
"""Fresh Qwen3-8B margin rerun for the frozen Phase 17 candidate pool."""

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

from scripts.contractkv_verifier import (
    RawAttestation,
    VerifyThresholds,
    make_verify_report,
    split_terminal_stop_token,
    target_rank_and_margin,
)
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_full_pool_qc_inputs import _retokenize_case, candidate_identity
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.phase17_live_common import digest, post_json


FIELDS = [
    "sample_key", "candidate_id", "partition", "dataset", "task", "sample_id",
    "unsafe_quality_drop", "quality_drop_vs_raw", "expected_prefix_gain",
    "raw_finish_reason", "answer_tokens", "top1_matches", "stop_consistent",
    "raw_margin_q05", "candidate_margin_q05", "degradation_q95",
    "robustness_reserve_at_zero", "verification_status", "failure_reason",
    "prompt_tokens", "error_type", "error_message", "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sample_key(sample: dict[str, Any]) -> str:
    return f"{sample.get('dataset')}::{sample.get('task')}::{sample.get('sample_id')}"


def prompt_ids(job: dict[str, Any], sample: dict[str, Any], tokenizer: Any, max_model_len: int) -> tuple[list[int], list[dict[str, str]]]:
    case = _retokenize_case(build_case(sample, stable_word_limit=2600), tokenizer, max_model_len)
    order_value = job.get("topological_order", "[]")
    order = json.loads(order_value) if isinstance(order_value, str) else list(order_value)
    identity = candidate_identity(case, [str(value) for value in order])
    expected = str(job.get("candidate_id", ""))
    if expected and identity["candidate_id"] != expected:
        raise ValueError(f"candidate identity mismatch: {identity['candidate_id']} != {expected}")
    text = _ordered_text([str(value) for value in order], case["segments"])
    messages = quality_messages(case, text)
    return tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True), messages


def generate_raw(args: argparse.Namespace, job: dict[str, Any], sample: dict[str, Any], tokenizer: Any) -> dict[str, Any]:
    ids, messages = prompt_ids(job, sample, tokenizer, args.max_model_len)
    response = post_json(args.base_url.rstrip("/") + "/chat/completions", {
        "model": args.model, "messages": messages, "max_tokens": args.max_tokens,
        "temperature": 0, "top_p": 1, "logprobs": True, "top_logprobs": 2,
        "return_token_ids": True, "stream": False,
        "request_id": f"phase17-cal-raw-{job['job_id']}",
    }, args.timeout)
    token_ids, margins, finish_reason, source = extract_raw_tokens_and_margins(response)
    answer_ids, answer_margins, terminal_stop_token_id = split_terminal_stop_token(
        token_ids, margins, finish_reason)
    return {
        "sample_key": job["sample_key"], "job_id": job["job_id"],
        "prompt_tokens": len(ids), "token_ids": answer_ids, "token_margins": answer_margins,
        "terminal_stop_token_id": terminal_stop_token_id,
        "finish_reason": finish_reason, "token_source": source,
        "model_hash": digest(args.model), "tokenizer_hash": digest(ids),
        "chat_template_hash": digest(messages), "error_type": "none", "error_message": "",
    }


def verify_candidate(args: argparse.Namespace, job: dict[str, Any], sample: dict[str, Any], raw: dict[str, Any], label: dict[str, str], feature: dict[str, str], tokenizer: Any) -> dict[str, Any]:
    started = time.perf_counter()
    base = {
        "sample_key": job["sample_key"], "candidate_id": job["candidate_id"],
        "partition": job["partition"], "dataset": job["dataset"], "task": job["task"],
        "sample_id": job["sample_id"], "unsafe_quality_drop": label["unsafe_quality_drop"],
        "quality_drop_vs_raw": label["quality_drop_vs_raw"],
        "expected_prefix_gain": feature.get("expected_prefix_gain", "0"),
        "claim_boundary": "Fresh Qwen3-8B API token-ID/logprob calibration evidence; offline threshold selection, not live promotion.",
    }
    try:
        ids, _ = prompt_ids(job, sample, tokenizer, args.max_model_len)
        raw_ids = [int(value) for value in raw["token_ids"]]
        terminal_stop_token_id = int(raw.get("terminal_stop_token_id", args.stop_token_id))
        # v0 raw attestations predate explicit terminal-token splitting.
        if raw.get("terminal_stop_token_id") is None and raw_ids:
            terminal_stop_token_id = raw_ids[-1]
            raw_ids = raw_ids[:-1]
            raw_margins = [float(value) for value in raw["token_margins"][:-1]]
        else:
            raw_margins = [float(value) for value in raw["token_margins"]]
        forced = ids + raw_ids + [terminal_stop_token_id]
        response = post_json(args.base_url.rstrip("/") + "/completions", {
            "model": args.model, "prompt": forced, "max_tokens": 1,
            "temperature": 0, "prompt_logprobs": 2, "return_token_ids": True,
            "request_id": f"phase17-cal-candidate-{job['job_id']}",
        }, args.timeout)
        choice = (response.get("choices") or [{}])[0]
        logprobs = choice.get("prompt_logprobs") or []
        returned_ids = [int(value) for value in (choice.get("prompt_token_ids") or [])]
        if returned_ids != forced:
            raise ValueError("vLLM changed candidate token-ID prompt")
        ranks, margins = [], []
        for offset, target in enumerate(raw_ids, start=len(ids)):
            rank, margin = target_rank_and_margin(logprobs[offset], target)
            ranks.append(rank); margins.append(margin)
        stop_rank, _ = target_rank_and_margin(logprobs[len(ids) + len(raw_ids)], terminal_stop_token_id)
        attestation = RawAttestation(
            token_ids=tuple(raw_ids), token_margins=tuple(raw_margins),
            finish_reason=str(raw["finish_reason"]), stop_token_ids=(terminal_stop_token_id,),
            model_hash=str(raw["model_hash"]), tokenizer_hash=str(raw["tokenizer_hash"]),
            chat_template_hash=str(raw["chat_template_hash"]),
        )
        report = make_verify_report(
            attestation, raw_ids, margins, ranks,
            terminal_stop_token_id if stop_rank == 1 else None,
            VerifyThresholds(0.0, 0.0, 1e9),
        )
        base.update({
            "raw_finish_reason": raw["finish_reason"], "answer_tokens": report.answer_tokens,
            "top1_matches": report.top1_matches, "stop_consistent": report.stop_consistent,
            "raw_margin_q05": report.raw_margin_q05,
            "candidate_margin_q05": report.candidate_margin_q05,
            "degradation_q95": report.degradation_q95,
            "robustness_reserve_at_zero": report.robustness_reserve,
            "verification_status": report.decision.value, "failure_reason": report.failure_reason,
            "prompt_tokens": len(ids), "error_type": "none", "error_message": "",
            "verification_ms": (time.perf_counter() - started) * 1000,
        })
    except Exception as exc:
        base.update({
            "raw_finish_reason": raw.get("finish_reason", ""), "answer_tokens": 0,
            "top1_matches": 0, "stop_consistent": False,
            "raw_margin_q05": "", "candidate_margin_q05": "", "degradation_q95": "",
            "robustness_reserve_at_zero": "-inf", "verification_status": "INCOMPLETE",
            "failure_reason": str(exc), "prompt_tokens": 0,
            "error_type": type(exc).__name__, "error_message": str(exc),
        })
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--full-pool", type=Path, default=Path("results/workload/phase14d_full_pool_v2.jsonl"))
    parser.add_argument("--jobs", type=Path, default=Path("results/end_to_end/phase14r_quality_jobs_v5.jsonl"))
    parser.add_argument("--labels", type=Path, default=Path("results/end_to_end/phase14r_quality_labels_v5.csv"))
    parser.add_argument("--features", type=Path, default=Path("results/end_to_end/phase14r_qc_candidate_features_v5.csv"))
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--candidate-output", type=Path, required=True)
    parser.add_argument("--stop-token-id", type=int, default=151645)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--max-candidates", type=int, default=0)
    parser.add_argument("--retry-all", action="store_true")
    args = parser.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    samples = {sample_key(row): row for row in load_jsonl(args.full_pool)}
    jobs = load_jsonl(args.jobs)
    raw_jobs = {str(row["sample_key"]): row for row in jobs if str(row.get("policy")) == "raw-order"}
    candidate_jobs = [row for row in jobs if str(row.get("policy")) != "raw-order"]
    if args.max_candidates:
        candidate_jobs = candidate_jobs[:args.max_candidates]
    with args.labels.open(encoding="utf-8", newline="") as handle:
        labels = {(row["sample_key"], row["candidate_id"]): row for row in csv.DictReader(handle)}
    with args.features.open(encoding="utf-8", newline="") as handle:
        features = {(row["sample_key"], row["candidate_id"]): row for row in csv.DictReader(handle)}
    raw_existing = {row["sample_key"]: row for row in load_jsonl(args.raw_output) if row.get("error_type") == "none"}
    needed_samples = sorted({str(job["sample_key"]) for job in candidate_jobs})
    for index, key in enumerate(needed_samples, 1):
        if key in raw_existing:
            continue
        try:
            row = generate_raw(args, raw_jobs[key], samples[key], tokenizer)
        except Exception as exc:
            row = {"sample_key": key, "error_type": type(exc).__name__, "error_message": str(exc)}
        append_jsonl(args.raw_output, row)
        if row.get("error_type") == "none":
            raw_existing[key] = row
        if index % 25 == 0:
            print(f"raw={index}/{len(needed_samples)}", flush=True)
    existing = {} if args.retry_all else {
        (row["sample_key"], row["candidate_id"]): row
        for row in load_jsonl(args.candidate_output)
        if row.get("error_type") == "none"
    }
    for index, job in enumerate(candidate_jobs, 1):
        identity = (str(job["sample_key"]), str(job["candidate_id"]))
        if identity in existing:
            continue
        raw = raw_existing.get(identity[0])
        if raw is None:
            row = {"sample_key": identity[0], "candidate_id": identity[1], "partition": job["partition"],
                   "error_type": "raw_attestation_missing", "error_message": "fresh raw request failed",
                   "verification_status": "INCOMPLETE", "claim_boundary": "Fail closed before candidate request."}
        else:
            row = verify_candidate(args, job, samples[identity[0]], raw, labels[identity], features[identity], tokenizer)
        append_jsonl(args.candidate_output, row); existing[identity] = row
        if index % 25 == 0:
            print(f"candidate={index}/{len(candidate_jobs)}", flush=True)
    rows = [existing[(str(job["sample_key"]), str(job["candidate_id"]))] for job in candidate_jobs]
    csv_path = args.candidate_output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"raw": len(raw_existing), "candidates": len(rows), "errors": sum(row.get("error_type") != "none" for row in rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
