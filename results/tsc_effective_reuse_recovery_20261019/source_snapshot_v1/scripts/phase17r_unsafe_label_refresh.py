#!/usr/bin/env python3
"""Re-score every historically unsafe Phase 17 candidate with current Qwen3-8B provenance."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_frozen_policy import GREEDY_CONFIG, load_frozen_policy, runtime_identity
from scripts.phase12_task_quality_sanity import score_answer
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase14c_full_pool_qc_inputs import _retokenize_case, candidate_identity
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.contractkv_verifier import split_terminal_stop_token
from scripts.phase17_live_common import post_json


FIELDS = ["sample_key", "candidate_id", "candidate_identity_match", "partition", "dataset", "task", "sample_id", "policy_hash", "model_revision", "tokenizer_hash", "chat_template_hash", "raw_score", "candidate_score", "fresh_quality_drop", "old_quality_drop", "old_unsafe", "fresh_unsafe", "label_status", "error_type", "error_message", "claim_boundary"]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sample_key(row: dict) -> str:
    return f"{row.get('dataset')}::{row.get('task')}::{row.get('sample_id')}"


def prompt(job: dict, sample: dict, tokenizer: object, max_model_len: int):
    case = _retokenize_case(build_case(sample, stable_word_limit=2600), tokenizer, max_model_len)
    order = json.loads(job["topological_order"]) if isinstance(job["topological_order"], str) else list(job["topological_order"])
    identity = candidate_identity(case, [str(value) for value in order])
    messages = quality_messages(case, _ordered_text([str(value) for value in order], case["segments"]))
    return messages, identity


def generate(args: argparse.Namespace, messages: list[dict], request_id: str) -> str:
    response = post_json(args.base_url.rstrip("/") + "/chat/completions", {"model": args.model, "messages": messages, "stream": False, "request_id": request_id, **GREEDY_CONFIG}, args.timeout)
    ids, margins, finish, _ = extract_raw_tokens_and_margins(response)
    split_terminal_stop_token(ids, margins, finish)
    return str(((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", default="qwen3-8b"); parser.add_argument("--model-path", type=Path, required=True); parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--full-pool", type=Path, required=True); parser.add_argument("--jobs", type=Path, required=True); parser.add_argument("--labels", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--max-model-len", type=int, default=8192); parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args(); policy, policy_hash = load_frozen_policy(args.policy)
    import vllm
    identity = runtime_identity(args.model, args.model_path, vllm.__version__)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    samples = {sample_key(row): row for row in load_jsonl(args.full_pool)}; jobs = load_jsonl(args.jobs)
    raw_jobs = {str(row["sample_key"]): row for row in jobs if row.get("policy") == "raw-order"}
    candidate_jobs = {(str(row["sample_key"]), str(row["candidate_id"])): row for row in jobs if row.get("policy") != "raw-order"}
    with args.labels.open(encoding="utf-8", newline="") as handle: labels = [row for row in csv.DictReader(handle) if str(row.get("unsafe_quality_drop", "")).lower() == "true"]
    rows = []
    for index, label in enumerate(labels, 1):
        row = {field: "" for field in FIELDS}; key = str(label["sample_key"]); cid = str(label["candidate_id"])
        row.update({"sample_key": key, "candidate_id": cid, "partition": label["partition"], "dataset": label["dataset"], "task": label["task"], "sample_id": label["sample_id"], "policy_hash": policy_hash, "model_revision": identity.model_revision, "tokenizer_hash": identity.tokenizer_hash, "chat_template_hash": identity.chat_template_hash, "old_quality_drop": label["quality_drop_vs_raw"], "old_unsafe": True, "claim_boundary": "Current Qwen3-8B re-score of every previously unsafe label; task sanity, not official benchmark scoring."})
        try:
            raw_messages, _ = prompt(raw_jobs[key], samples[key], tokenizer, args.max_model_len)
            candidate_messages, candidate_identity_actual = prompt(candidate_jobs[(key, cid)], samples[key], tokenizer, args.max_model_len)
            raw_text = generate(args, raw_messages, f"phase17r-refresh-raw-{index}")
            candidate_text = generate(args, candidate_messages, f"phase17r-refresh-candidate-{index}")
            raw_score = float(score_answer(raw_text, samples[key].get("answer", ""), samples[key].get("dataset", ""))["score"])
            candidate_score = float(score_answer(candidate_text, samples[key].get("answer", ""), samples[key].get("dataset", ""))["score"])
            drop = max(0.0, raw_score - candidate_score)
            row.update({"candidate_identity_match": candidate_identity_actual["candidate_id"] == cid, "raw_score": raw_score, "candidate_score": candidate_score, "fresh_quality_drop": drop, "fresh_unsafe": drop > .03, "label_status": "confirmed_unsafe" if drop > .03 else "stale_or_nonreproducible", "error_type": "none", "error_message": ""})
        except Exception as exc:
            row.update({"candidate_identity_match": False, "fresh_unsafe": "", "label_status": "refresh_incomplete", "error_type": type(exc).__name__, "error_message": str(exc)})
        rows.append(row); print(f"refresh={index}/{len(labels)}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    complete = [row for row in rows if row["error_type"] == "none"]
    print(json.dumps({"rows": len(rows), "complete": len(complete), "confirmed_unsafe": sum(str(row["fresh_unsafe"]).lower() == "true" for row in complete), "stale": sum(row["label_status"] == "stale_or_nonreproducible" for row in complete)}, indent=2))
    return 0 if len(complete) == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
