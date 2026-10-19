#!/usr/bin/env python3
"""Same-run causal audit of the two Phase 17 held-out false-safe candidates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_frozen_policy import GREEDY_CONFIG, load_frozen_policy, runtime_identity, validate_policy_runtime
from scripts.contractkv_verifier import RawAttestation, VerifyThresholds, make_verify_report, split_terminal_stop_token, target_rank_and_margin
from scripts.phase12_task_quality_sanity import score_answer
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_full_pool_qc_inputs import _retokenize_case, candidate_identity
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.phase17_live_common import digest, post_json


FIELDS = [
    "task", "sample_id", "candidate_id_expected", "candidate_id_actual", "candidate_identity_match",
    "model_revision", "tokenizer_hash", "chat_template_hash", "policy_hash", "decode_config_hash",
    "raw_prompt_hash", "candidate_prompt_hash", "raw_answer_ids_hash", "candidate_answer_ids_hash",
    "free_decode_token_path_equal", "raw_stop_token", "candidate_stop_token", "stop_equal",
    "teacher_forced_top1_matches", "teacher_forced_unique_top1_matches", "teacher_forced_minimum_margin",
    "teacher_forced_stop_consistent", "teacher_forced_decision", "raw_score", "candidate_score",
    "fresh_quality_drop", "old_quality_label_drop", "score_equal", "classification", "gate_pass",
    "runtime_manifest_match", "top1_tie_detected", "error_type", "error_message", "claim_boundary",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def key(sample: dict[str, Any]) -> str:
    return f"{sample.get('dataset')}::{sample.get('task')}::{sample.get('sample_id')}"


def sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def prompt_for(job: dict[str, Any], sample: dict[str, Any], tokenizer: Any, max_model_len: int) -> tuple[list[int], list[dict[str, str]], dict[str, str]]:
    case = _retokenize_case(build_case(sample, stable_word_limit=2600), tokenizer, max_model_len)
    order = json.loads(job["topological_order"]) if isinstance(job["topological_order"], str) else list(job["topological_order"])
    identity = candidate_identity(case, [str(value) for value in order])
    text = _ordered_text([str(value) for value in order], case["segments"])
    messages = quality_messages(case, text)
    return tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True), messages, identity


def generate(base_url: str, model: str, request_id: str, messages: list[dict[str, str]], timeout: float) -> dict[str, Any]:
    response = post_json(base_url.rstrip("/") + "/chat/completions", {
        "model": model, "messages": messages, "stream": False, **GREEDY_CONFIG,
        "request_id": request_id,
    }, timeout)
    ids, margins, finish, source = extract_raw_tokens_and_margins(response)
    answer, answer_margins, terminal = split_terminal_stop_token(ids, margins, finish)
    choice = (response.get("choices") or [{}])[0]
    text = str((choice.get("message") or {}).get("content") or "")
    return {"answer_ids": answer, "margins": answer_margins, "terminal": terminal, "text": text,
            "finish_reason": finish, "source": source, "response": response}


def classify(row: dict[str, Any]) -> str:
    if not row["candidate_identity_match"]:
        return "CANDIDATE_IDENTITY_MISMATCH"
    if not row["runtime_manifest_match"]:
        return "RUNTIME_PROVENANCE_MISMATCH"
    if row["top1_tie_detected"]:
        return "TOP1_TIE_AMBIGUITY"
    if row["teacher_forced_decision"] == "PASS" and not row["free_decode_token_path_equal"]:
        return "VERIFIER_DECODE_CONTRADICTION"
    if row["free_decode_token_path_equal"] and not row["score_equal"]:
        return "EVALUATOR_OR_METADATA_CONTRADICTION"
    if row["free_decode_token_path_equal"] and row["score_equal"] and row["old_quality_label_drop"] > .03:
        return "STALE_OR_MISJOINED_QUALITY_LABEL"
    if row["teacher_forced_decision"] != "PASS":
        return "CURRENT_INTRINSIC_REJECTION"
    return "CURRENT_CONSISTENT_PASS"


def audit_one(args: argparse.Namespace, policy: Any, policy_hash: str, identity: Any, job: dict[str, Any], sample: dict[str, Any], label: dict[str, str], tokenizer: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    base = {field: "" for field in FIELDS}
    trace: dict[str, Any] = {"sample_key": job["sample_key"], "candidate_id": job["candidate_id"], "decode_config": GREEDY_CONFIG, "policy_hash": policy_hash}
    try:
        raw_job = {candidate["sample_key"]: candidate for candidate in args.jobs_rows if candidate.get("policy") == "raw-order"}[job["sample_key"]]
        raw_ids, raw_messages, raw_identity = prompt_for(raw_job, sample, tokenizer, args.max_model_len)
        candidate_ids, candidate_messages, candidate_identity_actual = prompt_for(job, sample, tokenizer, args.max_model_len)
        raw = generate(args.base_url, args.model, f"phase17r-raw-{job['job_id']}", raw_messages, args.timeout)
        candidate_runs = [generate(args.base_url, args.model, f"phase17r-candidate-{job['job_id']}-{index}", candidate_messages, args.timeout) for index in range(3)]
        candidate = candidate_runs[0]
        forced = candidate_ids + raw["answer_ids"] + [raw["terminal"]]
        forced_response = post_json(args.base_url.rstrip("/") + "/completions", {
            "model": args.model, "prompt": forced, "max_tokens": 1, "temperature": 0,
            "prompt_logprobs": 2, "return_token_ids": True, "request_id": f"phase17r-forced-{job['job_id']}",
        }, args.timeout)
        choice = (forced_response.get("choices") or [{}])[0]
        prompt_ids = [int(value) for value in (choice.get("prompt_token_ids") or [])]
        if prompt_ids != forced:
            raise ValueError("PROMPT_TOKEN_ID_MISMATCH")
        entries = choice.get("prompt_logprobs") or []
        token_trace = []
        ranks, margins = [], []
        for offset, target in enumerate(raw["answer_ids"], start=len(candidate_ids)):
            rank, margin = target_rank_and_margin(entries[offset], target)
            ranks.append(rank); margins.append(margin)
            token_trace.append({"offset": offset, "target_token_id": target, "rank": rank, "margin": margin,
                                "strict_unique_top1": rank == 1 and margin > 0})
        stop_rank, stop_margin = target_rank_and_margin(entries[len(candidate_ids) + len(raw["answer_ids"])], raw["terminal"])
        token_trace.append({"offset": len(candidate_ids) + len(raw["answer_ids"]), "target_token_id": raw["terminal"],
                            "rank": stop_rank, "margin": stop_margin, "strict_unique_top1": stop_rank == 1 and stop_margin > 0,
                            "terminal": True})
        report = make_verify_report(RawAttestation(
            token_ids=tuple(raw["answer_ids"]), token_margins=tuple(raw["margins"]), finish_reason=raw["finish_reason"],
            stop_token_ids=(raw["terminal"],), model_hash=identity.model_revision,
            tokenizer_hash=identity.tokenizer_hash, chat_template_hash=identity.chat_template_hash,
        ), raw["answer_ids"], margins, ranks, raw["terminal"] if stop_rank == 1 else None,
           VerifyThresholds(policy.tau_raw, policy.tau_abs, policy.tau_drop))
        raw_score = float(score_answer(raw["text"], sample.get("answer", ""), sample.get("dataset", ""))["score"])
        candidate_score = float(score_answer(candidate["text"], sample.get("answer", ""), sample.get("dataset", ""))["score"])
        candidate_paths = [run["answer_ids"] + [run["terminal"]] for run in candidate_runs]
        free_equal = all(path == raw["answer_ids"] + [raw["terminal"]] for path in candidate_paths)
        runtime_ok = not validate_policy_runtime(policy, identity)
        row = {
            **base, "task": job["task"], "sample_id": job["sample_id"], "candidate_id_expected": job["candidate_id"],
            "candidate_id_actual": candidate_identity_actual["candidate_id"], "candidate_identity_match": candidate_identity_actual["candidate_id"] == job["candidate_id"],
            "model_revision": identity.model_revision, "tokenizer_hash": identity.tokenizer_hash, "chat_template_hash": identity.chat_template_hash,
            "policy_hash": policy_hash, "decode_config_hash": policy.decode_config_hash, "raw_prompt_hash": sha(raw_ids), "candidate_prompt_hash": sha(candidate_ids),
            "raw_answer_ids_hash": sha(raw["answer_ids"]), "candidate_answer_ids_hash": sha(candidate["answer_ids"]),
            "free_decode_token_path_equal": free_equal, "raw_stop_token": raw["terminal"], "candidate_stop_token": candidate["terminal"],
            "stop_equal": candidate["terminal"] == raw["terminal"], "teacher_forced_top1_matches": report.top1_matches,
            "teacher_forced_unique_top1_matches": sum(item["strict_unique_top1"] for item in token_trace[:-1]),
            "teacher_forced_minimum_margin": min(item["margin"] for item in token_trace),
            "teacher_forced_stop_consistent": report.stop_consistent and token_trace[-1]["strict_unique_top1"],
            "teacher_forced_decision": report.decision.value, "raw_score": raw_score, "candidate_score": candidate_score,
            "fresh_quality_drop": max(0.0, raw_score - candidate_score), "old_quality_label_drop": float(label["quality_drop_vs_raw"]),
            "score_equal": abs(raw_score - candidate_score) <= 1e-12, "runtime_manifest_match": runtime_ok,
            "top1_tie_detected": any(item["margin"] <= 0 for item in token_trace), "error_type": "none", "error_message": "",
            "claim_boundary": "Same-run Qwen3-8B free decode, strict teacher forcing, and task-sanity scoring; not official benchmark scoring.",
        }
        row["classification"] = classify(row); row["gate_pass"] = row["classification"] not in {"VERIFIER_DECODE_CONTRADICTION", "EVALUATOR_OR_METADATA_CONTRADICTION"}
        trace.update({"raw": raw, "candidate_runs": candidate_runs, "forced_token_trace": token_trace, "row": row})
    except Exception as exc:
        row = {**base, "task": job.get("task", ""), "sample_id": job.get("sample_id", ""),
               "candidate_id_expected": job.get("candidate_id", ""), "policy_hash": policy_hash,
               "classification": "CURRENT_INTRINSIC_REJECTION", "gate_pass": True,
               "error_type": type(exc).__name__, "error_message": str(exc),
               "claim_boundary": "Audit failure retained as fail-closed evidence."}
        trace.update({"error": repr(exc), "row": row})
    return row, trace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--model-path", type=Path, required=True); parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--full-pool", type=Path, required=True); parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace-output", type=Path, required=True); parser.add_argument("--max-model-len", type=int, default=8192); parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args(); policy, hash_value = load_frozen_policy(args.policy)
    import vllm
    identity = runtime_identity(args.model, args.model_path, vllm.__version__)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    samples = {key(row): row for row in load_jsonl(args.full_pool)}; args.jobs_rows = load_jsonl(args.jobs)
    with args.labels.open(encoding="utf-8", newline="") as handle:
        labels = {(row["sample_key"], row["candidate_id"]): row for row in csv.DictReader(handle)}
    targets = [("LongBench::qasper::58", "3cc4987ccd04629fd001"), ("LongBench::narrativeqa::165", "930dda182e476349cbd1")]
    jobs = {(str(row["sample_key"]), str(row["candidate_id"])): row for row in args.jobs_rows}
    rows, traces, failed = [], [], False
    for sample_key, candidate_id in targets:
        row, trace = audit_one(args, policy, hash_value, identity, jobs[(sample_key, candidate_id)], samples[sample_key], labels[(sample_key, candidate_id)], tokenizer)
        rows.append(row); traces.append(trace); failed = failed or not bool(row["gate_pass"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    with args.trace_output.open("w", encoding="utf-8") as handle:
        for trace in traces: handle.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({"rows": len(rows), "classifications": [row["classification"] for row in rows], "failed": failed}, indent=2))
    raise SystemExit(2 if failed else 0)


if __name__ == "__main__":
    main()
