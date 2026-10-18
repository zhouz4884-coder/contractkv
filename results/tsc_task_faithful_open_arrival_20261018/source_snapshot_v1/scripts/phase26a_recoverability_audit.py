#!/usr/bin/env python3
"""Run the preregistered Phase 26A DeepSeek recoverability audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_verifier import VerificationIncomplete, split_terminal_stop_token, target_rank_and_margin
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.phase17_live_common import api_root, digest, post_json, tokenize
from scripts.phase19b_end_to_end_live import load_jsonl, messages, turn_case
from scripts.phase20a_official_quality import standard_score
from scripts.phase22_llama_layout_ladder import expand_stable_segments, family_key, layout_for_level
from scripts.phase26_recoverability_common import classify_recoverability, freeze_budget, regret_statistics
from scripts.phase26_typed_behavior_contracts import contract_manifest, evaluate_typed_contract


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def request(args: argparse.Namespace, endpoint: str, payload: dict[str, Any],
            timeout_s: float | None = None,
            retry_count: int | None = None) -> dict[str, Any]:
    last: Exception | None = None
    retries = args.retries if retry_count is None else retry_count
    timeout = args.timeout if timeout_s is None else timeout_s
    for attempt in range(retries + 1):
        try:
            return post_json(args.base_url.rstrip("/") + endpoint, payload, timeout)
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(2.0 * (attempt + 1))
    assert last is not None
    raise last


def free_decode(args: argparse.Namespace, request_id: str,
                prompt_messages: list[dict[str, str]], max_tokens: int,
                cache_salt: str | None = None,
                request_timeout_s: float | None = None,
                retry_count: int | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    payload = {
        "model": args.model, "messages": prompt_messages, "max_tokens": max_tokens,
        "temperature": 0, "top_p": 1, "stream": False, "logprobs": True,
        "top_logprobs": 2, "return_token_ids": True, "request_id": request_id,
    }
    if cache_salt is not None:
        payload["cache_salt"] = cache_salt
    response = request(args, "/chat/completions", payload,
                       timeout_s=request_timeout_s, retry_count=retry_count)
    latency_ms = (time.perf_counter() - started) * 1000.0
    choice = (response.get("choices") or [{}])[0]
    token_ids, margins, finish_reason, token_source = extract_raw_tokens_and_margins(response)
    answer_ids = [int(value) for value in token_ids]
    answer_margins = [float(value) for value in margins]
    terminal: int | None = None
    complete = finish_reason == "stop"
    if complete:
        try:
            answer_ids, answer_margins, terminal = split_terminal_stop_token(
                token_ids, margins, finish_reason)
        except VerificationIncomplete:
            complete = False
    return {
        "request_id": request_id,
        "output_text": str((choice.get("message") or {}).get("content") or ""),
        "token_ids": answer_ids,
        "margins": answer_margins,
        "terminal_stop_token_id": terminal,
        "finish_reason": finish_reason,
        "complete": complete,
        "output_tokens": len(answer_ids),
        "latency_ms": latency_ms,
        "token_source": token_source,
    }


def teacher_forced_regret(args: argparse.Namespace, request_id: str,
                          candidate_prompt_ids: list[int], raw: dict[str, Any]) -> dict[str, Any]:
    raw_ids = [int(value) for value in raw["token_ids"]]
    terminal = raw.get("terminal_stop_token_id")
    if not raw.get("complete") or terminal is None:
        return {"available": False, "failure_reason": "raw_generation_incomplete"}
    forced = candidate_prompt_ids + raw_ids + [int(terminal)]
    started = time.perf_counter()
    response = request(args, "/completions", {
        "model": args.model, "prompt": forced, "max_tokens": 1,
        "temperature": 0, "prompt_logprobs": 2, "return_token_ids": True,
        "request_id": request_id,
    })
    latency_ms = (time.perf_counter() - started) * 1000.0
    choice = (response.get("choices") or [{}])[0]
    returned = [int(value) for value in (choice.get("prompt_token_ids") or [])]
    if returned != forced:
        raise VerificationIncomplete("vLLM changed teacher-forced token-ID prompt")
    logprobs = choice.get("prompt_logprobs") or []
    ranks: list[int] = []
    margins: list[float] = []
    for offset, target in enumerate(raw_ids, start=len(candidate_prompt_ids)):
        rank, margin = target_rank_and_margin(logprobs[offset], target)
        ranks.append(rank); margins.append(margin)
    stop_rank, stop_margin = target_rank_and_margin(
        logprobs[len(candidate_prompt_ids) + len(raw_ids)], int(terminal))
    return {
        "available": True, "failure_reason": "", "latency_ms": latency_ms,
        "ranks": ranks, "margins": margins,
        "stop_rank": stop_rank, "stop_margin": stop_margin,
    }


def context_text(case: dict[str, Any]) -> str:
    return "\n".join(
        str(segment.get("text", "")) for segment in case["segments"]
        if segment.get("segment_type") not in {"SYS_PROMPT", "TOOL_OBS", "USER_QUERY"}
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-key", choices=["chat", "coder"], required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    runtime = protocol["runtime"]
    budget_config = protocol["budget_profile"]
    samples = load_jsonl(args.sessions)
    diagnostics = load_jsonl(args.diagnostics)
    by_session = {str(row["phase19b_session_id"]): row for row in samples}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_cache_path = args.output_dir / "raw_budget_profile_v0.jsonl"
    audit_path = args.output_dir / "strict_failure_recoverability_v0.jsonl"
    budget_path = args.output_dir / "frozen_task_output_budgets_v0.json"
    provenance_path = args.output_dir / "audit_provenance_v0.json"
    existing_raw = {str(row["session_id"]): row for row in load_jsonl(raw_cache_path)} if args.resume and raw_cache_path.exists() else {}
    if not args.resume:
        raw_cache_path.unlink(missing_ok=True); audit_path.unlink(missing_ok=True)

    cases: dict[str, dict[str, Any]] = {}
    raw_layouts: dict[str, dict[str, Any]] = {}
    for sample in samples:
        sid = str(sample["phase19b_session_id"])
        case = expand_stable_segments(
            turn_case(sample, 0, int(runtime["stable_word_limit"])), 4)
        cases[sid] = case
        raw_layouts[sid] = layout_for_level(case, "L0")

    for index, sample in enumerate(samples, 1):
        sid = str(sample["phase19b_session_id"])
        if sid in existing_raw:
            continue
        try:
            raw = free_decode(
                args, f"phase26a-{args.model_key}-profile-{sid}",
                messages(cases[sid], raw_layouts[sid]["topological_order"]),
                int(budget_config["profile_max_tokens"]),
            )
            score, metric, source = standard_score(
                str(sample["dataset"]), str(sample["task"]), raw["output_text"], sample.get("answer", ""))
            row = {"model": args.model, "model_key": args.model_key,
                   "session_id": sid, "family": family_key(sample),
                   "dataset": sample["dataset"], "task": sample["task"],
                   "sample_id": str(sample["sample_id"]), **raw,
                   "task_score": score, "metric": metric, "metric_source": source,
                   "error_type": "none", "error_message": ""}
        except Exception as exc:
            row = {"model": args.model, "model_key": args.model_key,
                   "session_id": sid, "family": family_key(sample),
                   "dataset": sample["dataset"], "task": sample["task"],
                   "sample_id": str(sample["sample_id"]), "complete": False,
                   "finish_reason": "", "output_tokens": 0, "output_text": "",
                   "error_type": type(exc).__name__, "error_message": str(exc)}
        append_jsonl(raw_cache_path, row); existing_raw[sid] = row
        print(f"profile {args.model_key} {index}/{len(samples)} {sid} {row.get('finish_reason')}", flush=True)

    family_lengths: dict[str, list[int]] = {}
    for row in existing_raw.values():
        family_lengths.setdefault(str(row["family"]), []).append(int(row.get("output_tokens", 0)))
    budgets = {
        family: freeze_budget(
            lengths, q=float(budget_config["quantile"]),
            delta=int(budget_config["safety_delta_tokens"]),
            alignment=int(budget_config["alignment_tokens"]),
            minimum=int(budget_config["minimum_tokens"]),
            maximum=int(budget_config["maximum_tokens"]),
        ) for family, lengths in sorted(family_lengths.items())
    }
    budget_record = {
        "schema_version": "contractkv.phase26.frozen-task-output-budgets.v0",
        "model": args.model, "budgets": budgets,
        "lengths": {family: sorted(values) for family, values in sorted(family_lengths.items())},
        "profile_max_tokens": budget_config["profile_max_tokens"],
        "rule": "align_up(P99(raw_output_tokens)+32,32), clipped to [128,1024]",
        "development_only": True,
    }
    budget_path.write_text(json.dumps(budget_record, indent=2) + "\n", encoding="utf-8")

    completed_keys = set()
    if args.resume and audit_path.exists():
        completed_keys = {(str(row["session_id"]), str(row["level"])) for row in load_jsonl(audit_path)}
    for index, diagnostic in enumerate(diagnostics, 1):
        sid = str(diagnostic["session_id"]); level = str(diagnostic["level"])
        if (sid, level) in completed_keys:
            continue
        sample = by_session[sid]; case = cases[sid]; raw = existing_raw[sid]
        layout = layout_for_level(case, level)
        candidate_messages = messages(case, layout["topological_order"])
        prompt_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
        family = family_key(sample); budget = budgets[family]
        exact_pass = diagnostic.get("decision") == "PASS"
        base = {
            "model": args.model, "model_key": args.model_key,
            "session_id": sid, "family": family, "dataset": sample["dataset"],
            "task": sample["task"], "sample_id": str(sample["sample_id"]),
            "level": level, "exact_decision": diagnostic.get("decision", ""),
            "exact_failure_reason": diagnostic.get("failure_reason", ""),
            "moved_stable_tokens": int(layout.get("moved_stable_tokens", 0)),
            "candidate_prompt_tokens": len(prompt_ids), "frozen_output_budget": budget,
            "raw_finish_reason": raw.get("finish_reason", ""),
            "raw_complete": bool(raw.get("complete")),
            "raw_output_tokens": int(raw.get("output_tokens", 0)),
            "raw_output_text": raw.get("output_text", ""),
            "raw_task_score": raw.get("task_score", ""),
        }
        if exact_pass:
            row = {**base, "candidate_finish_reason": "not_run_exact_pass",
                   "candidate_complete": True, "candidate_output_tokens": raw.get("output_tokens", 0),
                   "candidate_output_text": raw.get("output_text", ""),
                   "candidate_task_score": raw.get("task_score", ""), "quality_drop": 0.0,
                   "typed_contract": {"decision": "PASS", "contract_type": "exact_path",
                                      "ground_truth_used": False},
                   "recoverability_class": "exact_pass", "teacher_forced_regret": {"available": True,
                                      "regret_max": 0.0, "regret_q95": 0.0, "regret_mean": 0.0},
                   "candidate_decode_ms": 0.0, "teacher_force_ms": 0.0,
                   "error_type": "none", "error_message": ""}
        else:
            try:
                candidate = free_decode(
                    args, f"phase26a-{args.model_key}-{sid}-{level}-candidate",
                    candidate_messages, budget)
                candidate_score, metric, source = standard_score(
                    str(sample["dataset"]), str(sample["task"]),
                    candidate["output_text"], sample.get("answer", ""))
                raw_score = float(raw.get("task_score", 0.0))
                drop = max(0.0, raw_score - candidate_score)
                typed = evaluate_typed_contract(
                    str(sample["dataset"]), str(sample["task"]),
                    str(raw.get("output_text", "")), candidate["output_text"], context_text(case))
                try:
                    forced = teacher_forced_regret(
                        args, f"phase26a-{args.model_key}-{sid}-{level}-regret", prompt_ids, raw)
                    stats = regret_statistics(
                        forced.get("margins", []), forced.get("ranks", []),
                        list(raw.get("token_ids", [])), candidate["token_ids"])
                    regret = {**forced, **stats}
                except Exception as exc:
                    regret = {"available": False, "failure_reason": f"{type(exc).__name__}: {exc}"}
                classification = classify_recoverability(
                    raw_complete=bool(raw.get("complete")),
                    candidate_complete=bool(candidate.get("complete")), quality_drop=drop,
                    typed_decision=typed.decision, exact_pass=False,
                    epsilon=float(protocol["quality_epsilon"]),
                )
                row = {**base,
                       "candidate_finish_reason": candidate["finish_reason"],
                       "candidate_complete": candidate["complete"],
                       "candidate_output_tokens": candidate["output_tokens"],
                       "candidate_output_text": candidate["output_text"],
                       "candidate_task_score": candidate_score,
                       "metric": metric, "metric_source": source, "quality_drop": drop,
                       "typed_contract": typed.as_dict(),
                       "recoverability_class": classification,
                       "teacher_forced_regret": regret,
                       "candidate_decode_ms": candidate["latency_ms"],
                       "teacher_force_ms": regret.get("latency_ms", 0.0),
                       "error_type": "none", "error_message": ""}
            except Exception as exc:
                row = {**base, "candidate_complete": False,
                       "recoverability_class": "protocol_unavailable",
                       "typed_contract": {"decision": "UNKNOWN", "ground_truth_used": False},
                       "teacher_forced_regret": {"available": False},
                       "error_type": type(exc).__name__, "error_message": str(exc)}
        append_jsonl(audit_path, row)
        print(f"audit {args.model_key} {index}/{len(diagnostics)} {sid} {level} {row['recoverability_class']}", flush=True)

    provenance = {
        "schema_version": "contractkv.phase26.audit-provenance.v0",
        "model": args.model, "model_path": str(args.model_path),
        "protocol_sha256": hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
        "sessions_sha256": hashlib.sha256(args.sessions.read_bytes()).hexdigest(),
        "diagnostics_sha256": hashlib.sha256(args.diagnostics.read_bytes()).hexdigest(),
        "typed_contract_manifest": contract_manifest(),
        "ground_truth_used_for_offline_diagnosis_only": True,
        "heldout_opened": False,
    }
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model": args.model, "budgets": budgets,
                      "audit_rows": len(load_jsonl(audit_path))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
