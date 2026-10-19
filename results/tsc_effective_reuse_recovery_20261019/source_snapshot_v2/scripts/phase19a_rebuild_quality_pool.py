#!/usr/bin/env python3
"""Rebuild all Phase 19A quality evidence under one frozen provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_frozen_policy import (
    GREEDY_CONFIG,
    load_frozen_policy,
    runtime_identity,
    validate_policy_runtime,
)
from scripts.contractkv_verifier import (
    RawAttestation,
    VerificationIncomplete,
    VerifyThresholds,
    make_verify_report,
    split_terminal_stop_token,
    target_rank_and_margin,
)
from scripts.phase12_task_quality_sanity import score_answer
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_full_pool_qc_inputs import _retokenize_case, candidate_identity
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.phase17_live_common import post_json


OUTPUT_FIELDS = [
    "sample_key", "candidate_id", "partition", "dataset", "task", "sample_id",
    "model_revision", "tokenizer_hash", "chat_template_hash",
    "candidate_builder_hash", "evaluator_hash", "policy_hash",
    "raw_prompt_hash", "candidate_prompt_hash", "raw_answer_ids_hash",
    "candidate_answer_ids_hash", "raw_stop", "candidate_stop",
    "raw_finish_reason", "candidate_finish_reason", "raw_score",
    "candidate_score", "quality_drop", "fresh_unsafe_label",
    "verifier_decision", "verifier_failure_reason", "certificate_eligible",
    "expected_prefix_gain", "candidate_identity_match", "protocol_status",
    "raw_request_id", "candidate_request_id", "verifier_request_id",
    "raw_output_tokens", "candidate_output_tokens", "raw_margin_q05",
    "candidate_margin_q05", "degradation_q95", "robustness_reserve",
    "error_type", "error_message", "timestamp", "claim_boundary",
]


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def file_bundle_hash(paths: list[Path]) -> str:
    return digest([{ "path": path.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest() }
                   for path in paths])


def source_revision(module_file: str) -> tuple[str, bool]:
    root = Path(module_file).resolve().parents[1]
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True).strip())
        return revision, dirty
    except Exception:
        return "unavailable", True


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def sample_key(row: dict[str, Any]) -> str:
    return f"{row.get('dataset')}::{row.get('task')}::{row.get('sample_id')}"


def prompt_for(job: dict[str, Any], sample: dict[str, Any], tokenizer: Any,
               max_model_len: int) -> tuple[list[int], list[dict[str, str]], dict[str, str]]:
    case = _retokenize_case(build_case(sample, stable_word_limit=2600),
                            tokenizer, max_model_len)
    order_value = job.get("topological_order", "[]")
    order = json.loads(order_value) if isinstance(order_value, str) else list(order_value)
    order = [str(value) for value in order]
    identity = candidate_identity(case, order)
    messages = quality_messages(case, _ordered_text(order, case["segments"]))
    ids = tokenizer.apply_chat_template(messages, tokenize=True,
                                        add_generation_prompt=True)
    return [int(value) for value in ids], messages, identity


def request_with_retry(args: argparse.Namespace, endpoint: str,
                       payload: dict[str, Any]) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(args.retries + 1):
        try:
            return post_json(args.base_url.rstrip("/") + endpoint, payload, args.timeout)
        except Exception as exc:
            last = exc
            if attempt < args.retries:
                time.sleep(min(8.0, 1.5 * (attempt + 1)))
    assert last is not None
    raise last


def free_decode(args: argparse.Namespace, job: dict[str, Any], sample: dict[str, Any],
                tokenizer: Any, role: str) -> dict[str, Any]:
    prompt_ids, messages, identity = prompt_for(job, sample, tokenizer,
                                                 args.max_model_len)
    request_id = f"phase19a-{role}-{job['job_id']}"
    response = request_with_retry(args, "/chat/completions", {
        "model": args.model, "messages": messages, "stream": False,
        "request_id": request_id, **GREEDY_CONFIG,
    })
    choice = (response.get("choices") or [{}])[0]
    token_ids, margins, finish_reason, token_source = extract_raw_tokens_and_margins(response)
    protocol_status = "COMPLETE"
    terminal: int | None = None
    answer_ids = [int(value) for value in token_ids]
    answer_margins = [float(value) for value in margins]
    try:
        answer_ids, answer_margins, terminal = split_terminal_stop_token(
            token_ids, margins, finish_reason)
    except VerificationIncomplete:
        protocol_status = "INCOMPLETE"
    text = str((choice.get("message") or {}).get("content") or "")
    scores = score_answer(text, sample.get("answer", ""),
                          str(sample.get("dataset", "")))
    return {
        "sample_key": job["sample_key"], "job_id": job["job_id"],
        "candidate_id": identity["candidate_id"], "order_hash": identity["order_hash"],
        "prompt_hash": digest(prompt_ids), "prompt_tokens": len(prompt_ids),
        "answer_ids": answer_ids, "answer_margins": answer_margins,
        "answer_ids_hash": digest(answer_ids), "terminal_stop_token_id": terminal,
        "finish_reason": finish_reason, "protocol_status": protocol_status,
        "token_source": token_source, "score": float(scores["score"]),
        "output_text": text, "request_id": request_id,
        "output_tokens": len(answer_ids), "error_type": "none", "error_message": "",
    }


def incomplete_generation(job: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "sample_key": str(job.get("sample_key", "")),
        "job_id": str(job.get("job_id", "")),
        "candidate_id": str(job.get("candidate_id", "")),
        "protocol_status": "INCOMPLETE", "finish_reason": "",
        "error_type": type(exc).__name__, "error_message": str(exc),
    }


def verify_candidate(args: argparse.Namespace, job: dict[str, Any], sample: dict[str, Any],
                     raw: dict[str, Any], tokenizer: Any, policy: Any) -> dict[str, Any]:
    if raw.get("protocol_status") != "COMPLETE":
        return {"decision": "INCOMPLETE", "failure_reason": "raw free decode incomplete",
                "request_id": ""}
    prompt_ids, _, identity = prompt_for(job, sample, tokenizer, args.max_model_len)
    expected = str(job["candidate_id"])
    if identity["candidate_id"] != expected:
        return {"decision": "INCOMPLETE", "failure_reason": "candidate identity mismatch",
                "request_id": ""}
    raw_ids = [int(value) for value in raw["answer_ids"]]
    raw_margins = [float(value) for value in raw["answer_margins"]]
    terminal = int(raw["terminal_stop_token_id"])
    forced = prompt_ids + raw_ids + [terminal]
    request_id = f"phase19a-verify-{job['job_id']}"
    response = request_with_retry(args, "/completions", {
        "model": args.model, "prompt": forced, "max_tokens": 1,
        "temperature": 0, "prompt_logprobs": 2, "return_token_ids": True,
        "request_id": request_id,
    })
    choice = (response.get("choices") or [{}])[0]
    returned = [int(value) for value in (choice.get("prompt_token_ids") or [])]
    if returned != forced:
        raise VerificationIncomplete("vLLM changed teacher-forced token-ID prompt")
    logprobs = choice.get("prompt_logprobs") or []
    ranks, candidate_margins = [], []
    for offset, target in enumerate(raw_ids, start=len(prompt_ids)):
        rank, margin = target_rank_and_margin(logprobs[offset], target)
        ranks.append(rank); candidate_margins.append(margin)
    stop_rank, _ = target_rank_and_margin(logprobs[len(prompt_ids) + len(raw_ids)], terminal)
    report = make_verify_report(
        RawAttestation(tuple(raw_ids), tuple(raw_margins), str(raw["finish_reason"]),
                       (terminal,), policy.model_revision, policy.tokenizer_hash,
                       policy.chat_template_hash),
        raw_ids, candidate_margins, ranks, terminal if stop_rank == 1 else None,
        VerifyThresholds(policy.tau_raw, policy.tau_abs, policy.tau_drop),
    )
    return {
        "decision": report.decision.value, "failure_reason": report.failure_reason,
        "request_id": request_id, "raw_margin_q05": report.raw_margin_q05,
        "candidate_margin_q05": report.candidate_margin_q05,
        "degradation_q95": report.degradation_q95,
        "robustness_reserve": report.robustness_reserve,
    }


def finite_or_blank(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-8b")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--full-pool", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--raw-cache", type=Path, required=True)
    parser.add_argument("--candidate-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance-output", type=Path, required=True)
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()

    import vllm
    from transformers import AutoTokenizer

    policy, policy_hash = load_frozen_policy(args.policy)
    runtime = runtime_identity(args.model, args.model_path, vllm.__version__)
    vllm_source_revision, vllm_source_dirty = source_revision(vllm.__file__)
    runtime_errors = validate_policy_runtime(policy, runtime)
    if runtime_errors:
        raise RuntimeError("frozen runtime mismatch: " + "; ".join(runtime_errors))
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    samples = {sample_key(row): row for row in load_jsonl(args.full_pool)}
    jobs = load_jsonl(args.jobs)
    raw_jobs = {str(row["sample_key"]): row for row in jobs if row.get("policy") == "raw-order"}
    candidate_jobs = [row for row in jobs if row.get("policy") != "raw-order"]
    with args.labels.open(encoding="utf-8", newline="") as handle:
        labels = {(row["sample_key"], row["candidate_id"]): row for row in csv.DictReader(handle)}
    with args.features.open(encoding="utf-8", newline="") as handle:
        features = {(row["sample_key"], row["candidate_id"]): row for row in csv.DictReader(handle)}
    job_keys = {(str(row["sample_key"]), str(row["candidate_id"])) for row in candidate_jobs}
    if len(candidate_jobs) != 734 or set(labels) != job_keys:
        raise RuntimeError(f"frozen candidate join mismatch jobs={len(candidate_jobs)} labels={len(labels)}")

    repo = Path(__file__).resolve().parents[1]
    builder_hash = file_bundle_hash([
        repo / "scripts/phase14c_full_pool_qc_inputs.py",
        repo / "scripts/phase13b_fresh_policy_quality_replay.py",
        repo / "scripts/phase12f_real_vllm_caposc_replay.py",
    ])
    evaluator_hash = file_bundle_hash([
        repo / "scripts/phase12_task_quality_sanity.py",
        repo / "scripts/contractkv_verifier.py",
        repo / "scripts/phase19a_rebuild_quality_pool.py",
    ])
    split_hash = digest(sorted((key[0], key[1], labels[key]["partition"]) for key in labels))
    provenance = {
        "schema_version": "phase19a.frozen-provenance.v1",
        **asdict(runtime), "policy_hash": policy_hash,
        "candidate_builder_hash": builder_hash, "evaluator_hash": evaluator_hash,
        "candidate_count": 734, "raw_sample_count": len(raw_jobs),
        "candidate_split_hash": split_hash, "quality_epsilon": 0.03,
        "decode_config": GREEDY_CONFIG,
        "vllm_source_revision": vllm_source_revision,
        "vllm_source_dirty": vllm_source_dirty,
        "source_patch": "vLLM-0.10.2 ContractKV compact-egress branch; standard generation API",
    }
    args.provenance_output.parent.mkdir(parents=True, exist_ok=True)
    args.provenance_output.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    raw_existing = {row["sample_key"]: row for row in load_jsonl(args.raw_cache)
                    if row.get("error_type") == "none" or not args.retry_errors}
    needed_raw = [raw_jobs[key] for key in sorted({str(row["sample_key"]) for row in candidate_jobs})
                  if key not in raw_existing]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(free_decode, args, job, samples[job["sample_key"]], tokenizer, "raw"): job
                   for job in needed_raw}
        for index, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try: row = future.result()
            except Exception as exc: row = incomplete_generation(job, exc)
            append_jsonl(args.raw_cache, row); raw_existing[row["sample_key"]] = row
            if index % 25 == 0: print(f"raw={index}/{len(needed_raw)}", flush=True)

    candidate_existing = {(row["sample_key"], row["candidate_id"]): row
                          for row in load_jsonl(args.candidate_cache)
                          if row.get("error_type") == "none" or not args.retry_errors}

    def candidate_task(job: dict[str, Any]) -> dict[str, Any]:
        key = str(job["sample_key"]); expected = str(job["candidate_id"])
        try:
            generated = free_decode(args, job, samples[key], tokenizer, "candidate")
            actual = generated["candidate_id"]
            identity_match = actual == expected
            if not identity_match:
                return {**generated, "candidate_id": expected,
                        "candidate_id_actual": actual, "candidate_identity_match": False,
                        "verification": {"decision": "INCOMPLETE",
                                         "failure_reason": "candidate identity mismatch",
                                         "request_id": ""}}
            verification = verify_candidate(args, job, samples[key], raw_existing[key],
                                            tokenizer, policy)
            return {**generated, "candidate_id": expected, "candidate_id_actual": actual,
                    "candidate_identity_match": True, "verification": verification}
        except Exception as exc:
            return {**incomplete_generation(job, exc), "candidate_id_actual": "",
                    "candidate_identity_match": False,
                    "verification": {"decision": "INCOMPLETE",
                                     "failure_reason": str(exc), "request_id": ""}}

    pending = [job for job in candidate_jobs
               if (str(job["sample_key"]), str(job["candidate_id"])) not in candidate_existing]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(candidate_task, job): job for job in pending}
        for index, future in enumerate(as_completed(futures), 1):
            row = future.result(); append_jsonl(args.candidate_cache, row)
            candidate_existing[(row["sample_key"], row["candidate_id"])] = row
            if index % 25 == 0: print(f"candidate={index}/{len(pending)}", flush=True)

    output = []
    for job in candidate_jobs:
        key = (str(job["sample_key"]), str(job["candidate_id"]))
        label, feature = labels[key], features[key]
        raw, candidate = raw_existing[key[0]], candidate_existing[key]
        raw_prompt_ids, _, _ = prompt_for(raw_jobs[key[0]], samples[key[0]], tokenizer,
                                          args.max_model_len)
        candidate_prompt_ids, _, candidate_identity_actual = prompt_for(
            job, samples[key[0]], tokenizer, args.max_model_len)
        verification = candidate.get("verification") or {}
        complete = (raw.get("protocol_status") == "COMPLETE"
                    and candidate.get("protocol_status") == "COMPLETE")
        scores_valid = raw.get("error_type") == "none" and candidate.get("error_type") == "none"
        drop = max(0.0, float(raw["score"]) - float(candidate["score"])) if scores_valid else None
        unsafe = (drop > 0.03) if drop is not None and complete else None
        # Candidate identity is a deterministic builder property and remains
        # auditable even when free decoding cannot produce a margin certificate.
        identity_match = candidate_identity_actual["candidate_id"] == key[1]
        eligible = bool(complete and identity_match and unsafe is False
                        and verification.get("decision") == "PASS")
        if not identity_match:
            error_type = "candidate_identity_mismatch"
        elif raw.get("error_type") != "none":
            error_type = "raw_" + str(raw.get("error_type") or "unknown")
        elif candidate.get("error_type") != "none":
            error_type = "candidate_" + str(candidate.get("error_type") or "unknown")
        else:
            error_type = "none"
        row = {
            "sample_key": key[0], "candidate_id": key[1], "partition": label["partition"],
            "dataset": label["dataset"], "task": label["task"], "sample_id": label["sample_id"],
            "model_revision": runtime.model_revision, "tokenizer_hash": runtime.tokenizer_hash,
            "chat_template_hash": runtime.chat_template_hash,
            "candidate_builder_hash": builder_hash, "evaluator_hash": evaluator_hash,
            "policy_hash": policy_hash,
            "raw_prompt_hash": raw.get("prompt_hash") or digest(raw_prompt_ids),
            "candidate_prompt_hash": candidate.get("prompt_hash") or digest(candidate_prompt_ids),
            "raw_answer_ids_hash": raw.get("answer_ids_hash") or digest(raw.get("answer_ids", [])),
            "candidate_answer_ids_hash": candidate.get("answer_ids_hash") or digest(candidate.get("answer_ids", [])),
            "raw_stop": raw.get("terminal_stop_token_id", ""),
            "candidate_stop": candidate.get("terminal_stop_token_id", ""),
            "raw_finish_reason": raw.get("finish_reason", ""),
            "candidate_finish_reason": candidate.get("finish_reason", ""),
            "raw_score": raw.get("score", ""), "candidate_score": candidate.get("score", ""),
            "quality_drop": "" if drop is None else drop,
            "fresh_unsafe_label": "" if unsafe is None else unsafe,
            "verifier_decision": verification.get("decision", "INCOMPLETE"),
            "verifier_failure_reason": verification.get("failure_reason", ""),
            "certificate_eligible": eligible,
            "expected_prefix_gain": feature.get("expected_prefix_gain", 0),
            "candidate_identity_match": identity_match,
            "protocol_status": "COMPLETE" if complete else "INCOMPLETE",
            "raw_request_id": raw.get("request_id", ""),
            "candidate_request_id": candidate.get("request_id", ""),
            "verifier_request_id": verification.get("request_id", ""),
            "raw_output_tokens": raw.get("output_tokens", ""),
            "candidate_output_tokens": candidate.get("output_tokens", ""),
            "raw_margin_q05": finite_or_blank(verification.get("raw_margin_q05", "")),
            "candidate_margin_q05": finite_or_blank(verification.get("candidate_margin_q05", "")),
            "degradation_q95": finite_or_blank(verification.get("degradation_q95", "")),
            "robustness_reserve": finite_or_blank(verification.get("robustness_reserve", "")),
            "error_type": error_type, "error_message": candidate.get("error_message", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "claim_boundary": "Fresh frozen-provenance Qwen3-8B task-sanity and intrinsic attestation; not official benchmark scoring.",
        }
        output.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader(); writer.writerows(output)
    print(json.dumps({"rows": len(output),
                      "complete": sum(row["protocol_status"] == "COMPLETE" for row in output),
                      "incomplete": sum(row["protocol_status"] == "INCOMPLETE" for row in output),
                      "identity_mismatch": sum(not row["candidate_identity_match"] for row in output),
                      "certificate_eligible": sum(row["certificate_eligible"] for row in output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
