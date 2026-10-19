#!/usr/bin/env python3
"""Run development-only Tier-1 plus ephemeral deterministic Tier-2 rescue."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import VerifyDecision, build_pstp_spec, upsert_registry_spec
from scripts.contractkv_task_contracts import contract_manifest_hash, evaluate_contract
from scripts.phase17_live_common import generate_raw, post_json, tokenize
from scripts.phase19b_end_to_end_live import compact_verify, compile_layout, messages, stable_order, turn_case
from scripts.phase20b_llama_rejection_audit import generate_diagnostic
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def request_chat(base_url: str, model: str, request_id: str,
                 request_messages: list[dict[str, str]], max_tokens: int,
                 timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = post_json(base_url.rstrip("/") + "/chat/completions", {
            "model": model, "messages": request_messages, "max_tokens": max_tokens,
            "temperature": 0, "top_p": 1, "stream": False,
            "request_id": request_id,
        }, timeout)
        choice = (response.get("choices") or [{}])[0]
        return {"success": bool(choice),
                "text": str((choice.get("message") or {}).get("content") or ""),
                "finish_reason": str(choice.get("finish_reason") or "unknown"),
                "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                "error_type": "none", "error_message": ""}
    except Exception as exc:
        return {"success": False, "text": "", "finish_reason": "error",
                "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                "error_type": type(exc).__name__, "error_message": str(exc)[:400]}


def promote_prefix(args: argparse.Namespace, sid: str, prefix_messages: list[dict[str, str]],
                   candidate_messages: list[dict[str, str]]) -> dict[str, Any]:
    stable_ids = tokenize(args.base_url, args.model, prefix_messages, False, args.timeout)
    candidate_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
    request_id = f"phase20c-promote-{sid}-{time.time_ns()}"
    spec = build_pstp_spec(f"phase20c-promote-txn-{sid}", stable_ids, candidate_ids,
                           VerifyDecision.PASS, args.block_size, shadow_work=True)
    upsert_registry_spec(args.registry, request_id, spec)
    response = request_chat(args.base_url, args.model, request_id, prefix_messages, 1, args.timeout)
    return {**response, "request_id": request_id,
            "stable_prefix_tokens": spec.stable_prefix_end_token,
            "expected_stable_tokens": spec.expected_stable_tokens,
            "glue_status": spec.glue_status}


def probe_promotion_cost(args: argparse.Namespace, sid: str,
                         prefix_messages: list[dict[str, str]],
                         candidate_messages: list[dict[str, str]]) -> dict[str, Any]:
    stable_ids = tokenize(args.base_url, args.model, prefix_messages, False, args.timeout)
    candidate_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
    request_id = f"phase20c-promotion-probe-{sid}-{time.time_ns()}"
    spec = build_pstp_spec(f"phase20c-promotion-probe-txn-{sid}", stable_ids, candidate_ids,
                           VerifyDecision.CANCELLED, args.block_size,
                           failure_reason="development-only promotion cost probe", shadow_work=True)
    upsert_registry_spec(args.registry, request_id, spec)
    response = request_chat(args.base_url, args.model, request_id, prefix_messages, 1, args.timeout)
    return {**response, "request_id": request_id,
            "stable_prefix_tokens": spec.stable_prefix_end_token}


def run_one(args: argparse.Namespace, sample: dict[str, Any]) -> dict[str, Any]:
    sid = str(sample["phase20_session_id"]); ledger = SegmentPrefixLedger()
    case = turn_case(sample, 0, args.stable_word_limit)
    raw_layout = compile_layout("raw-order", case, ledger, sid, 0, args.tool_slack_ms)
    candidate_layout = compile_layout("physical-cache-aware", case, ledger, sid, 0, args.tool_slack_ms)
    raw_messages = messages(case, raw_layout["topological_order"])
    candidate_messages = messages(case, candidate_layout["topological_order"])
    prefix_messages = messages(case, stable_order(case, candidate_layout["topological_order"]))
    candidate_prompt_tokens = len(tokenize(args.base_url, args.model, candidate_messages, True, args.timeout))
    expected_stable_tokens = len(tokenize(args.base_url, args.model, prefix_messages, False, args.timeout))
    started = time.perf_counter(); tier1: dict[str, Any]
    try:
        raw = generate_raw(args.base_url, args.model, f"phase20c-raw-{sid}", raw_messages,
                           args.timeout, args.max_tokens)
        tier1 = compact_verify(args, sample, case, candidate_layout, raw, sid)
        raw_complete = True
    except Exception as exc:
        raw = generate_diagnostic(args.base_url, args.model, f"phase20c-raw-diag-{sid}",
                                  raw_messages, args.timeout, args.max_tokens)
        raw_complete = raw.get("finish_reason") != "length"
        tier1 = {"certificate_issued": False, "verify_decision": "INCOMPLETE",
                 "failure_reason": f"{type(exc).__name__}: {exc}", "verification_ms": 0.0,
                 "stable_prefix_tokens": 0}
    tier1_pass = bool(tier1.get("certificate_issued"))
    result = {
        "session_id": sid, "dataset": sample.get("dataset"), "task": sample.get("task"),
        "sample_id": sample.get("sample_id"), "tier1_pass": tier1_pass,
        "tier1_decision": tier1.get("verify_decision", "INCOMPLETE"),
        "tier1_failure_reason": tier1.get("failure_reason", ""),
        "tier1_ms": float(tier1.get("verification_ms", 0) or 0),
        "raw_finish_reason": raw.get("finish_reason", "unknown"),
        "raw_output": raw.get("text", ""), "tier2_attempted": False,
        "tier2_admitted": False, "tier2_contract_pass": False,
        "tier2_promoted": False, "tier2_candidate_ms": 0.0,
        "tier2_promotion_ms": 0.0, "tier2_total_ms": 0.0,
        "contract_manifest_hash": contract_manifest_hash(),
        "candidate_prompt_tokens": candidate_prompt_tokens,
        "expected_stable_tokens": expected_stable_tokens,
        "raw_output_tokens": len(raw.get("token_ids", [])),
        "selected_layout": candidate_layout.get("selected_policy", ""),
        "violated_edges": candidate_layout.get("violated_edges", []),
        "error_type": "none", "error_message": "",
    }
    if tier1_pass:
        result["certificate_tier"] = "tier1"; result["certificate_issued"] = True
        result["stable_prefix_tokens"] = int(tier1.get("stable_prefix_tokens", 0) or 0)
        result["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
        return result

    frozen_path = getattr(args, "frozen_policy", None)
    if frozen_path:
        frozen = json.loads(Path(frozen_path).read_text(encoding="utf-8"))
        incremental_budget = float(frozen["frozen_total_cost_budget_ms"])
        remaining = max(0.0, args.tool_slack_ms - result["tier1_ms"])
        result["tier2_predicted_incremental_ms"] = incremental_budget
        result["tier2_remaining_slack_ms"] = remaining
        if incremental_budget > remaining:
            result["certificate_tier"] = "none"; result["certificate_issued"] = False
            result["error_type"] = "budget_denied"
            result["error_message"] = "frozen Tier-2 p95 cost exceeds post-Tier-1 remaining slack"
            result["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
            return result
    result["tier2_attempted"] = True; result["tier2_admitted"] = True
    candidate_id = f"phase20c-ephemeral-{sid}-{time.time_ns()}"
    ephemeral = build_pstp_spec(f"phase20c-ephemeral-txn-{sid}", [], [],
                                VerifyDecision.CANCELLED, args.block_size,
                                failure_reason="Tier-2 candidate is ephemeral", shadow_work=True)
    upsert_registry_spec(args.registry, candidate_id, ephemeral)
    candidate = request_chat(args.base_url, args.model, candidate_id, candidate_messages,
                             args.max_tokens, args.timeout)
    result["tier2_candidate_request_id"] = candidate_id
    result["tier2_candidate_ms"] = candidate["elapsed_ms"]
    result["candidate_finish_reason"] = candidate["finish_reason"]
    result["candidate_output"] = candidate["text"]
    contract = evaluate_contract(str(sample.get("dataset")), str(sample.get("task")),
                                 str(raw.get("text", "")), candidate["text"])
    contract_pass = bool(raw_complete and candidate["success"]
                         and candidate["finish_reason"] != "length" and contract.equivalent)
    result.update({f"contract_{key}": value for key, value in contract.as_dict().items()})
    result["tier2_contract_pass"] = contract_pass
    if not frozen_path:
        probe = probe_promotion_cost(args, sid, prefix_messages, candidate_messages)
        result["promotion_cost_probe_request_id"] = probe["request_id"]
        result["promotion_cost_probe_ms"] = probe["elapsed_ms"]
    else:
        result["promotion_cost_probe_ms"] = 0.0
    if contract_pass:
        promotion = promote_prefix(args, sid, prefix_messages, candidate_messages)
        result["tier2_promotion_request_id"] = promotion["request_id"]
        result["tier2_promotion_ms"] = promotion["elapsed_ms"]
        result["tier2_promoted"] = bool(promotion["success"])
        result["stable_prefix_tokens"] = promotion["stable_prefix_tokens"]
    result["tier2_total_ms"] = result["tier2_candidate_ms"] + result["tier2_promotion_ms"]
    result["certificate_issued"] = bool(result["tier2_promoted"])
    result["certificate_tier"] = "tier2" if result["tier2_promoted"] else "none"
    result["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--registry", type=Path, required=True); parser.add_argument("--policy-hash", required=True)
    parser.add_argument("--frozen-policy", type=Path)
    parser.add_argument("--load-tier", default="phase20-development")
    parser.add_argument("--block-size", type=int, default=16); parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--stable-word-limit", type=int, default=2600); parser.add_argument("--tool-slack-ms", type=float, default=3000)
    parser.add_argument("--timeout", type=float, default=300); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); rows = []
    for sample in load_jsonl(args.sessions):
        row = run_one(args, sample); rows.append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows), encoding="utf-8")
        print(json.dumps({"session_id": row["session_id"], "tier": row["certificate_tier"],
                          "tier2_contract_pass": row["tier2_contract_pass"]}))
    print(json.dumps({"sessions": len(rows), "tier1": sum(r["certificate_tier"] == "tier1" for r in rows),
                      "tier2": sum(r["certificate_tier"] == "tier2" for r in rows),
                      "certified": sum(r["certificate_issued"] for r in rows)}, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
