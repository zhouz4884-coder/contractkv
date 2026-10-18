#!/usr/bin/env python3
"""Audit rejected-safe Llama sessions before designing any Tier-2 rescue."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_task_contracts import evaluate_contract, normalize_answer
from scripts.contractkv_verifier import VerificationIncomplete, target_rank_and_margin
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase17_live_common import api_root, digest, post_json, tokenize
from scripts.phase19b_end_to_end_live import compile_layout, messages, turn_case


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def hash_ids(values: list[int]) -> str:
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def first_divergent(left: list[int], right: list[int]) -> int:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right)) if len(left) != len(right) else -1


def generate_diagnostic(base_url: str, model: str, request_id: str,
                        request_messages: list[dict[str, str]], timeout: float,
                        max_tokens: int) -> dict[str, Any]:
    """Generate token evidence without treating a length stop as an error."""
    response = post_json(base_url.rstrip("/") + "/chat/completions", {
        "model": model, "messages": request_messages, "max_tokens": max_tokens,
        "temperature": 0, "logprobs": True, "top_logprobs": 2,
        "return_token_ids": True, "request_id": request_id,
    }, timeout)
    choice = (response.get("choices") or [{}])[0]
    token_ids = [int(value) for value in (choice.get("token_ids") or [])]
    content = str((choice.get("message") or {}).get("content") or "")
    finish_reason = str(choice.get("finish_reason") or "unknown")
    stop_id = int(response.get("stop_token_id") or -1)
    if finish_reason != "length" and token_ids and token_ids[-1] == stop_id:
        token_ids = token_ids[:-1]
    return {"text": content, "token_ids": token_ids,
            "terminal_stop_token_id": stop_id, "finish_reason": finish_reason}


def select_rejected_safe(labels: Path, sessions: Path) -> list[dict[str, Any]]:
    with labels.open(encoding="utf-8", newline="") as handle:
        wanted = {row["session_id"] for row in csv.DictReader(handle)
                  if row["quality_label"] == "safe" and str(row["certificate_issued"]).lower() != "true"}
    selected = [row for row in load_jsonl(sessions) if str(row["phase19b_session_id"]) in wanted]
    if len(selected) != len(wanted):
        raise ValueError(f"missing rejected-safe sessions: wanted={len(wanted)} selected={len(selected)}")
    return sorted(selected, key=lambda row: str(row["phase19b_session_id"]))


def audit_one(args: argparse.Namespace, sample: dict[str, Any]) -> dict[str, Any]:
    sid = str(sample["phase19b_session_id"]); case = turn_case(sample, 0, args.stable_word_limit)
    ledger = SegmentPrefixLedger()
    raw_layout = compile_layout("raw-order", case, ledger, sid, 0, args.tool_slack_ms)
    candidate_layout = compile_layout("physical-cache-aware", case, ledger, sid, 0, args.tool_slack_ms)
    raw_messages = messages(case, raw_layout["topological_order"])
    candidate_messages = messages(case, candidate_layout["topological_order"])
    raw_prompt_ids = tokenize(args.base_url, args.model, raw_messages, True, args.timeout)
    candidate_prompt_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
    candidate_no_generation = tokenize(args.base_url, args.model, candidate_messages, False, args.timeout)
    suffix = candidate_prompt_ids[len(candidate_no_generation):] if candidate_prompt_ids[:len(candidate_no_generation)] == candidate_no_generation else []
    started = time.perf_counter()
    try:
        raw = generate_diagnostic(args.base_url, args.model, f"phase20b-raw-{sid}", raw_messages,
                                  args.timeout, args.max_tokens)
        candidates = [generate_diagnostic(args.base_url, args.model, f"phase20b-candidate-{sid}-r{repeat}",
                                          candidate_messages, args.timeout, args.max_tokens)
                      for repeat in range(args.repeats)]
        forced_tail = list(raw["token_ids"])
        if raw["finish_reason"] != "length" and raw["terminal_stop_token_id"] >= 0:
            forced_tail.append(raw["terminal_stop_token_id"])
        forced = candidate_prompt_ids + forced_tail
        response = post_json(args.base_url.rstrip("/") + "/completions", {
            "model": args.model, "prompt": forced, "max_tokens": 1,
            "temperature": 0, "prompt_logprobs": 2, "return_token_ids": True,
            "request_id": f"phase20b-forced-{sid}",
        }, args.timeout)
        choice = (response.get("choices") or [{}])[0]
        returned = [int(value) for value in (choice.get("prompt_token_ids") or [])]
        logprobs = choice.get("prompt_logprobs") or []
        forced_prefix = returned[:len(candidate_prompt_ids)]
        prompt_match = forced_prefix == candidate_prompt_ids
        offset_match = len(returned) == len(forced) and len(logprobs) == len(forced)
        ranks: list[int] = []; margins: list[float] = []; absent = -1
        for index, token_id in enumerate(raw["token_ids"]):
            try:
                rank, margin = target_rank_and_margin(logprobs[len(candidate_prompt_ids) + index], token_id)
                ranks.append(rank); margins.append(margin)
            except (VerificationIncomplete, IndexError):
                absent = index; break
        try:
            stop_rank, _ = target_rank_and_margin(
                logprobs[len(candidate_prompt_ids) + len(raw["token_ids"])],
                raw["terminal_stop_token_id"])
        except (VerificationIncomplete, IndexError, TypeError):
            stop_rank = 0
        unique_candidate_paths = {tuple(item["token_ids"] + [item["terminal_stop_token_id"]]) for item in candidates}
        primary = candidates[0]
        contract = evaluate_contract(str(sample["dataset"]), str(sample["task"]),
                                     raw["text"], primary["text"])
        exact_text = raw["text"] == primary["text"]
        normalized_equal = normalize_answer(raw["text"]) == normalize_answer(primary["text"])
        protocol_bug = not prompt_match or not offset_match or not suffix
        if not prompt_match or not suffix:
            taxonomy = "PROMPT_SUFFIX_MISMATCH"
        elif not offset_match:
            taxonomy = "VERIFY_START_OFFSET_MISMATCH"
        elif raw["finish_reason"] == "length" or any(item["finish_reason"] == "length" for item in candidates):
            taxonomy = "LENGTH_STOP"
        elif len(unique_candidate_paths) > 1:
            taxonomy = "NONDETERMINISTIC_TOP1_TIE"
        elif not contract.supported:
            taxonomy = "TASK_CONTRACT_UNAVAILABLE"
        elif contract.equivalent and not exact_text and normalized_equal:
            taxonomy = "TASK_EQUIVALENT_FORMAT_DIVERGENCE"
        elif contract.equivalent and not exact_text:
            taxonomy = "TASK_EQUIVALENT_LEXICAL_DIVERGENCE"
        elif not contract.equivalent:
            taxonomy = "TRUE_TOKEN_PATH_DIVERGENCE"
        elif stop_rank != 1 and absent < 0:
            taxonomy = "TERMINAL_PROTOCOL_MISMATCH"
        else:
            taxonomy = "TRUE_TOKEN_PATH_DIVERGENCE" if absent >= 0 or any(rank != 1 for rank in ranks) else "TASK_EQUIVALENT_FORMAT_DIVERGENCE"
        return {
            "session_id": sid, "dataset": sample["dataset"], "task": sample["task"],
            "sample_id": sample["sample_id"], "raw_prompt_hash": hash_ids(raw_prompt_ids),
            "candidate_prompt_hash": hash_ids(candidate_prompt_ids),
            "candidate_generation_suffix_hash": hash_ids(suffix),
            "forced_prefix_hash": hash_ids(forced_prefix), "verify_start_token": len(candidate_prompt_ids),
            "raw_answer_token_ids": raw["token_ids"],
            "candidate_answer_token_ids": [item["token_ids"] for item in candidates],
            "first_divergent_position": first_divergent(raw["token_ids"], primary["token_ids"]),
            "target_ranks": ranks, "target_margins": margins,
            "target_absent_position": absent, "raw_stop_token": raw["terminal_stop_token_id"],
            "candidate_stop_tokens": [item["terminal_stop_token_id"] for item in candidates],
            "stop_rank": stop_rank, "raw_finish_reason": raw["finish_reason"],
            "candidate_finish_reasons": [item["finish_reason"] for item in candidates],
            "raw_output": raw["text"], "candidate_outputs": [item["text"] for item in candidates],
            "normalized_output_equal": normalized_equal, "candidate_repeats_deterministic": len(unique_candidate_paths) == 1,
            **contract.as_dict(), "prompt_prefix_match": prompt_match,
            "verify_offset_match": offset_match, "protocol_bug": protocol_bug,
            "taxonomy": taxonomy, "elapsed_ms": (time.perf_counter() - started) * 1000,
            "error_type": "none", "error_message": "",
        }
    except Exception as exc:
        return {"session_id": sid, "dataset": sample["dataset"], "task": sample["task"],
                "sample_id": sample["sample_id"], "taxonomy": "TASK_CONTRACT_UNAVAILABLE",
                "protocol_bug": False, "error_type": type(exc).__name__, "error_message": str(exc),
                "elapsed_ms": (time.perf_counter() - started) * 1000}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--labels", type=Path, required=True); parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3); parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--stable-word-limit", type=int, default=2600)
    parser.add_argument("--tool-slack-ms", type=float, default=2000); parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args(); samples = select_rejected_safe(args.labels, args.sessions)
    rows = [audit_one(args, sample) for sample in samples]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    taxonomy = Counter(str(row["taxonomy"]) for row in rows)
    protocol_bugs = sum(row.get("protocol_bug") is True for row in rows)
    task_equivalent = sum(row.get("supported") is True and row.get("equivalent") is True for row in rows)
    errors = sum(row.get("error_type") != "none" for row in rows)
    summary = {
        "sessions": len(rows), "candidate_repeats": args.repeats,
        "taxonomy": dict(sorted(taxonomy.items())), "protocol_bug_cases": protocol_bugs,
        "task_equivalent_cases": task_equivalent,
        "task_equivalent_fraction": task_equivalent / max(1, len(rows)),
        "nondeterministic_cases": sum(row.get("candidate_repeats_deterministic") is False for row in rows),
        "errors": errors,
        "decision": "fix_protocol_and_retest_tier1" if protocol_bugs else "proceed_one_shot_tier2",
        "claim_boundary": "Diagnostic reuse of Phase 19C rejected-safe sessions; never a final held-out result.",
    }
    args.summary_output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2)); return 0 if not errors else 2


if __name__ == "__main__": raise SystemExit(main())
