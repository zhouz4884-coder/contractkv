#!/usr/bin/env python3
"""Teacher-forced token-path certification for Phase 14 SLC-A."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_full_pool_qc_inputs import _retokenize_case, candidate_identity
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages


RAW_FIELDS = [
    "timestamp", "sample_key", "candidate_id", "partition", "dataset", "task",
    "sample_id", "unsafe_quality_drop", "quality_drop_vs_raw", "answer_tokens",
    "matched_answer_tokens", "token_path_match_rate", "all_token_top1_match",
    "minimum_logit_margin", "mean_logit_margin", "raw_finish_reason", "stop_top1_token_id", "eos_consistency",
    "certificate_issued", "expected_prefix_gain", "verification_ms",
    "prompt_tokens", "error_type", "error_message", "claim_boundary",
]

SUMMARY_FIELDS = [
    "partition", "dataset", "task", "candidates", "unsafe_candidates",
    "certificate_issued", "certificate_issue_rate", "unsafe_rejected",
    "unsafe_rejection_rate", "safe_candidates", "safe_certified",
    "safe_certificate_coverage", "mean_token_path_match_rate",
    "mean_minimum_logit_margin", "retained_prefix_gain_fraction",
    "mean_verification_ms", "p95_verification_ms", "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(round((len(values) - 1) * q)))]


def sample_key(sample: dict[str, Any]) -> str:
    return f"{sample.get('dataset')}::{sample.get('task')}::{sample.get('sample_id')}"


def build_prompt_ids(
    job: dict[str, Any],
    sample: dict[str, Any],
    tokenizer: Any,
    max_model_len: int,
    stable_word_limit: int,
) -> list[int]:
    case = _retokenize_case(
        build_case(sample, stable_word_limit=stable_word_limit), tokenizer, max_model_len,
    )
    order_value = job.get("topological_order", "[]")
    order = json.loads(order_value) if isinstance(order_value, str) else list(order_value)
    identity = candidate_identity(case, [str(item) for item in order])
    for field in ("candidate_id", "order_hash"):
        expected = str(job.get(field, ""))
        if expected and expected != identity[field]:
            raise ValueError(
                f"SLC prompt identity mismatch for {field}: expected={expected} actual={identity[field]}"
            )
    text = _ordered_text([str(item) for item in order], case["segments"])
    messages = quality_messages(case, text)
    return tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True,
    )


def answer_logit_slice(prompt_tokens: int, answer_tokens: int) -> slice:
    """Causal-LM logits at i predict input token i+1."""
    if prompt_tokens <= 0 or answer_tokens <= 0:
        raise ValueError("prompt and answer token counts must be positive")
    return slice(prompt_tokens - 1, prompt_tokens - 1 + answer_tokens)


def select_truncated_answer_and_stop_logits(logits: Any, answer_tokens: int) -> tuple[Any, Any]:
    """Read ``logits_to_keep=A+1`` output without absolute prompt indices."""
    if int(logits.shape[1]) != answer_tokens + 1:
        raise ValueError(
            f"truncated logits length {int(logits.shape[1])} does not equal answer_tokens + 1 ({answer_tokens + 1})")
    return logits[0, :answer_tokens, :], logits[0, answer_tokens, :]


def stop_is_consistent(
    raw_finish_reason: str,
    stop_top1_token_id: int,
    eos_token_id: int | None,
    stop_token_ids: set[int] | None = None,
) -> bool:
    """Fail closed unless the recorded stop agrees with a model stop token."""
    if raw_finish_reason != "stop":
        return False
    accepted = set(stop_token_ids or ())
    if eos_token_id is not None:
        accepted.add(int(eos_token_id))
    return stop_top1_token_id in accepted


def verify_token_path(
    model: Any,
    tokenizer: Any,
    prompt_ids: list[int],
    raw_output_text: str,
    raw_finish_reason: str,
    margin_threshold: float,
    stop_token_ids: set[int] | None = None,
) -> dict[str, Any]:
    import torch

    answer_ids = tokenizer.encode(raw_output_text, add_special_tokens=False)
    if not answer_ids:
        raise ValueError("raw answer token sequence is empty")
    input_ids = torch.tensor([prompt_ids + answer_ids], dtype=torch.long, device=model.device)
    started = time.perf_counter()
    with torch.inference_mode():
        output = model(
            input_ids=input_ids,
            use_cache=False,
            logits_to_keep=len(answer_ids) + 1,
        )
        prediction_logits, stop_logits = select_truncated_answer_and_stop_logits(output.logits, len(answer_ids))
        prediction_logits = prediction_logits.float()
        targets = torch.tensor(answer_ids, device=prediction_logits.device)
        top2_values, top2_ids = prediction_logits.topk(2, dim=-1)
        top1_ids = top2_ids[:, 0]
        raw_logits = prediction_logits.gather(1, targets[:, None]).squeeze(1)
        best_other = torch.where(
            top1_ids == targets, top2_values[:, 1], top2_values[:, 0],
        )
        margins = raw_logits - best_other
        matches = top1_ids == targets
        stop_top1 = int(stop_logits.float().argmax().item())
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    matched = int(matches.sum().item())
    minimum_margin = float(margins.min().item())
    all_match = matched == len(answer_ids)
    eos_id = getattr(tokenizer, "eos_token_id", None)
    # A generation stopped by max length is not an output-stop certificate.
    # Missing legacy metadata also fails closed rather than being assumed safe.
    eos_consistency = stop_is_consistent(
        raw_finish_reason, stop_top1, eos_id, stop_token_ids,
    )
    certificate = all_match and eos_consistency and minimum_margin >= margin_threshold
    return {
        "answer_tokens": len(answer_ids),
        "matched_answer_tokens": matched,
        "token_path_match_rate": matched / len(answer_ids),
        "all_token_top1_match": all_match,
        "minimum_logit_margin": minimum_margin,
        "mean_logit_margin": float(margins.mean().item()),
        "raw_finish_reason": raw_finish_reason,
        "stop_top1_token_id": stop_top1,
        "eos_consistency": eos_consistency,
        "certificate_issued": certificate,
        "verification_ms": elapsed_ms,
        "prompt_tokens": len(prompt_ids),
    }


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    ).to(args.device)
    model.eval()

    samples = {sample_key(sample): sample for sample in load_jsonl(args.full_pool)}
    jobs = load_jsonl(args.jobs)
    labels = {(row["sample_key"], row["candidate_id"]): row for row in load_csv(args.labels)}
    features = {(row["sample_key"], row["candidate_id"]): row for row in load_csv(args.features)}
    outputs = load_jsonl(args.raw_outputs)
    raw_by_sample = {
        str(row.get("sample_key")): row for row in outputs
        if str(row.get("policy")) == "raw-order" and _bool(row.get("success"))
    }
    existing_rows = load_jsonl(args.output) if args.output.exists() else []
    existing = {
        (str(row.get("sample_key")), str(row.get("candidate_id"))): row
        for row in existing_rows
    }
    candidates = [job for job in jobs if str(job.get("policy")) != "raw-order"]
    if args.partitions:
        allowed = set(args.partitions.split(","))
        candidates = [job for job in candidates if str(job.get("partition")) in allowed]
    if args.max_candidates:
        candidates = candidates[:args.max_candidates]
    rows = list(existing.values())
    for index, job in enumerate(candidates, start=1):
        identity = (str(job.get("sample_key")), str(job.get("candidate_id")))
        if identity in existing:
            continue
        label = labels.get(identity)
        raw = raw_by_sample.get(identity[0])
        sample = samples.get(identity[0])
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        row = {
            "timestamp": started_at,
            "sample_key": identity[0],
            "candidate_id": identity[1],
            "partition": job.get("partition", ""),
            "dataset": job.get("dataset", ""),
            "task": job.get("task", ""),
            "sample_id": job.get("sample_id", ""),
            "unsafe_quality_drop": label.get("unsafe_quality_drop", "") if label else "",
            "quality_drop_vs_raw": label.get("quality_drop_vs_raw", "") if label else "",
            "expected_prefix_gain": features.get(identity, {}).get("expected_prefix_gain", 0),
            "error_type": "none",
            "error_message": "",
            "claim_boundary": "Single-turn teacher-forced greedy token-path and stop-token certificate; future-turn transfer requires Phase 14SLC-B.",
        }
        try:
            if sample is None or raw is None or label is None:
                raise KeyError("missing sample, raw output, or paired label")
            prompt_ids = build_prompt_ids(
                job, sample, tokenizer, args.max_model_len, args.stable_word_limit,
            )
            row.update(verify_token_path(
                model, tokenizer, prompt_ids, str(raw.get("output_text", "")),
                str(raw.get("finish_reason", "")),
                args.margin_threshold,
                args.stop_token_ids,
            ))
        except Exception as exc:
            row.update({
                "certificate_issued": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })
        rows.append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows), encoding="utf-8")
        if index % 10 == 0:
            print(f"verified={index}/{len(candidates)} certificates={sum(_bool(item.get('certificate_issued')) for item in rows)}", flush=True)
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("partition")), str(row.get("dataset")), str(row.get("task")))].append(row)
        groups[(str(row.get("partition")), "all", "all")].append(row)
        groups[("all", "all", "all")].append(row)
    output = []
    for (partition, dataset, task), group in sorted(groups.items()):
        valid = [row for row in group if row.get("error_type") == "none"]
        unsafe = [row for row in valid if _bool(row.get("unsafe_quality_drop"))]
        safe = [row for row in valid if not _bool(row.get("unsafe_quality_drop"))]
        certified = [row for row in valid if _bool(row.get("certificate_issued"))]
        unsafe_rejected = [row for row in unsafe if not _bool(row.get("certificate_issued"))]
        safe_certified = [row for row in safe if _bool(row.get("certificate_issued"))]
        total_gain = sum(_float(row.get("expected_prefix_gain")) for row in safe)
        retained_gain = sum(_float(row.get("expected_prefix_gain")) for row in safe_certified)
        times = [_float(row.get("verification_ms")) for row in valid]
        output.append({
            "partition": partition, "dataset": dataset, "task": task,
            "candidates": len(valid), "unsafe_candidates": len(unsafe),
            "certificate_issued": len(certified),
            "certificate_issue_rate": len(certified) / len(valid) if valid else 0.0,
            "unsafe_rejected": len(unsafe_rejected),
            "unsafe_rejection_rate": len(unsafe_rejected) / len(unsafe) if unsafe else 1.0,
            "safe_candidates": len(safe), "safe_certified": len(safe_certified),
            "safe_certificate_coverage": len(safe_certified) / len(safe) if safe else 0.0,
            "mean_token_path_match_rate": statistics.mean(_float(row.get("token_path_match_rate")) for row in valid) if valid else 0.0,
            "mean_minimum_logit_margin": statistics.mean(_float(row.get("minimum_logit_margin")) for row in valid) if valid else 0.0,
            "retained_prefix_gain_fraction": retained_gain / total_gain if total_gain else 0.0,
            "mean_verification_ms": statistics.mean(times) if times else 0.0,
            "p95_verification_ms": percentile(times, .95),
            "claim_boundary": "Teacher-forced token-path equivalence for the observed raw answer under deterministic greedy continuation; not future-turn proof.",
        })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--raw-outputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--margin-threshold", type=float, default=0.0)
    parser.add_argument(
        "--stop-token-ids",
        default="",
        help="Comma-separated additional model stop-token IDs; EOS is always accepted.",
    )
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--partitions", default="")
    parser.add_argument("--max-candidates", type=int, default=0)
    args = parser.parse_args()
    args.stop_token_ids = {
        int(item.strip()) for item in args.stop_token_ids.split(",") if item.strip()
    }
    rows = run(args)
    write_csv(args.summary_output, summarize(rows), SUMMARY_FIELDS)
    print(json.dumps(next(row for row in summarize(rows) if row["partition"] == "all"), ensure_ascii=False, indent=2))
    return 0 if rows and all(row.get("error_type") == "none" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
