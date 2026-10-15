"""Fresh revision cells with raw-reference attestation and free token evidence."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import urllib.request

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import lcp_length
from scripts.phase13b_fresh_policy_quality_replay import build_case
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase17_live_common import api_root, digest, post_json, tokenize
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins
from scripts.contractkv_verifier import split_terminal_stop_token
from scripts.phase20a_official_quality import standard_score
from scripts.phase22_llama_layout_ladder import expand_stable_segments, layout_for_level


FROZEN_LEVELS = {
    "Qwen3-8B": {"RULER": "L3", "HotpotQA": "L3", "NarrativeQA": "L3", "Qasper": "L3", "RepoBench": "L3"},
    "Mistral-7B-Instruct-v0.3": {"RULER": "L3", "HotpotQA": "L3", "NarrativeQA": "L3", "Qasper": "L0", "RepoBench": "L0"},
    "Llama-3.1-8B-Instruct": {"RULER": "L3", "HotpotQA": "L2", "NarrativeQA": "L2", "Qasper": "L0", "RepoBench": "L0"},
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def generation_payload(model: str, messages: list[dict], budget: int, seed: int) -> dict:
    return {"model": model, "messages": messages, "max_tokens": budget,
            "temperature": 0, "top_p": 1, "seed": seed,
            "return_token_ids": True}


def reference_generate(args, messages: list[dict], budget: int, rid: str) -> dict:
    body = post_json(args.base_url.rstrip("/") + "/chat/completions", {
        **generation_payload(args.model, messages, budget, args.protocol["runtime"]["seed"]),
        "stream": False, "logprobs": True, "top_logprobs": 2, "request_id": rid,
    }, args.timeout)
    ids, margins, finish, token_source = extract_raw_tokens_and_margins(body)
    choice = body["choices"][0]
    return {"full_token_ids": ids, "full_margins": margins,
            "finish_reason": finish, "token_source": token_source,
            "text": str(choice.get("message", {}).get("content") or ""),
            "usage": body.get("usage", {})}


def stream_generate(args, messages: list[dict], budget: int, rid: str,
                    salt: str | None = None) -> dict:
    payload = {**generation_payload(args.model, messages, budget, args.protocol["runtime"]["seed"]),
               "stream": True, "stream_options": {"include_usage": True}, "request_id": rid}
    if salt is not None:
        payload["cache_salt"] = salt
    request = urllib.request.Request(args.base_url.rstrip("/") + "/chat/completions",
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter(); first = last = None; text = []; ids = []; usage = {}; finish = ""; actual_id = rid
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            for line in response:
                value = line.decode(errors="replace").strip()
                if not value.startswith("data:"): continue
                data = value[5:].strip()
                if data == "[DONE]": break
                chunk = json.loads(data); actual_id = chunk.get("id", actual_id)
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta") or {}
                    content = delta.get("content") or ""
                    token_delta = choice.get("token_ids") or []
                    now = time.perf_counter()
                    if content:
                        first = now if first is None else first; last = now; text.append(content)
                    ids.extend(int(token) for token in token_delta)
                    finish = choice.get("finish_reason") or finish
        completed = time.perf_counter()
        count = int(usage.get("completion_tokens", len(ids)) or len(ids))
        return {"success": first is not None, "request_id": actual_id, "output_text": "".join(text),
                "output_token_ids": ids, "token_ids_available": bool(ids), "completion_tokens": count,
                "prompt_tokens": usage.get("prompt_tokens", ""), "finish_reason": finish,
                "ttft_ms": (first - started) * 1000 if first is not None else 0,
                "tpot_ms": (last - first) * 1000 / max(count - 1, 1) if last and first else 0,
                "latency_ms": (completed - started) * 1000,
                "error_type": "none", "error_message": ""}
    except Exception as exc:
        return {"success": False, "request_id": rid, "output_text": "", "output_token_ids": [],
                "token_ids_available": False, "completion_tokens": 0, "finish_reason": "error",
                "ttft_ms": 0, "tpot_ms": 0, "latency_ms": (time.perf_counter() - started) * 1000,
                "error_type": type(exc).__name__, "error_message": str(exc)}


def make_turn(args, sample: dict, turn: int) -> tuple[dict, dict, dict, list[dict], list[dict]]:
    case = expand_stable_segments(build_case(sample, args.protocol["layout"]["stable_word_limit"]),
                                  args.protocol["layout"]["stable_pieces"])
    sid = sample["revision_session_id"]
    if args.experiment != "common-hotpot":
        for seg in case["segments"]:
            if seg["segment_type"] == "USER_QUERY":
                wrappers = ("", "Answer the following question using the context.\n", "Question to answer:\n")
                seg["text"] = wrappers[turn % len(wrappers)] + seg["text"]
    for seg in case["segments"]:
        if seg["segment_type"] == "TOOL_OBS":
            seg["text"] = f"[PRIVATE_TOOL_OBS] revision_session={sid}; turn={turn}; status={['ready','completed','idle'][turn % 3]}; no additional answer evidence."
    level = (args.protocol["layout"]["common_hotpot_level"] if args.experiment == "common-hotpot" else
             FROZEN_LEVELS[args.model_identity][sample["revision_family"]])
    raw = layout_for_level(case, "L0", args.protocol["layout"]["ladder"])
    candidate = layout_for_level(case, level, args.protocol["layout"]["ladder"])
    # The namespace is policy-independent, so layout is the only prompt difference.
    system = f"[TSC-R1:{sid}]\n/no_think Answer using only the provided context. Return the shortest correct answer or code completion."
    render = lambda order: [{"role": "system", "content": system},
                            {"role": "user", "content": _ordered_text(order, case["segments"])}]
    return case, raw, candidate, render(raw["topological_order"]), render(candidate["topological_order"])


def budget_for(args, sample: dict) -> int:
    if args.experiment == "common-hotpot": return args.protocol["common_hotpot"]["output_budget"]
    if args.output_budget: return args.output_budget
    return args.protocol["free_generation"]["budgets"][sample["revision_family"]]


def certify(args, sample: dict, turn_data: tuple, budget: int, salt: str) -> dict:
    case, raw_layout, candidate, raw_messages, candidate_messages = turn_data
    started = time.perf_counter(); verify_ms = 0.0; raw = None
    result = {"certificate_issued": False, "verify_decision": "INCOMPLETE", "txn_state": "ABORTED", "committed_tokens": 0}
    try:
        raw = reference_generate(args, raw_messages, budget, args.cell_id + "-reference-" + sample["revision_session_id"])
        answer, margins, stop = split_terminal_stop_token(raw["full_token_ids"], raw["full_margins"], raw["finish_reason"])
        ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
        by_id = {seg["segment_id"]: seg for seg in case["segments"]}
        stable_order = []
        for sid in candidate["topological_order"]:
            if by_id[sid]["segment_type"] in {"TOOL_OBS", "USER_QUERY", "CHAT_HISTORY", "SCRATCHPAD"}:
                break
            stable_order.append(sid)
        prefix_messages = [candidate_messages[0], {"role": "user", "content": _ordered_text(stable_order, case["segments"])}]
        prefix_ids = tokenize(args.base_url, args.model, prefix_messages, False, args.timeout)
        next_candidate = make_turn(args, sample, 1)[4]
        next_ids = tokenize(args.base_url, args.model, next_candidate, True, args.timeout)
        stable_end = min(lcp_length(prefix_ids, ids), lcp_length(ids, next_ids))
        payload = {
            "request_id": args.cell_id + "-verify-" + sample["revision_session_id"],
            "txn_id": args.cell_id + "-txn-" + sample["revision_session_id"],
            "prompt_token_ids": ids + answer + [stop], "verify_start_token": len(ids),
            "reference_answer_ids": answer, "reference_raw_margins": margins,
            "terminal_stop_token_id": stop, "stable_prefix_end_token": stable_end,
            "policy_hash": args.policy_hash, "policy_version": "tsc-revision-r1-v1",
            "attestation_mode": "same-backend-teacher-forced-strict-top1",
            "stable_content_hash": digest(ids[:stable_end]), "layout_hash": digest(candidate["topological_order"]),
            "dependency_graph_hash": digest([(seg["segment_id"], seg.get("dependencies", [])) for seg in case["segments"]]),
            "timeout_s": args.timeout, "cache_salt": salt,
        }
        verify_started = time.perf_counter()
        result = post_json(api_root(args.base_url) + "/v1/contractkv/verify", payload, args.timeout)
        verify_ms = (time.perf_counter() - verify_started) * 1000
        result["stable_prefix_tokens"] = stable_end
        result["stable_prefix_hash"] = digest(ids[:stable_end])
    except Exception as exc:
        result.update({"failure_reason": f"{type(exc).__name__}: {exc}"})
    return {**result, "registration_ms": (time.perf_counter() - started) * 1000,
            "verify_endpoint_ms": verify_ms, "raw_finish_reason": raw["finish_reason"] if raw else "error",
            "reference_output_tokens": len(raw["full_token_ids"]) if raw else 0,
            "reference_prompt": "raw-order", "generation_config_hash": digest(generation_payload(args.model, [], budget, args.protocol["runtime"]["seed"])),
            "output_budget": budget, "reference_text_hash": digest(raw["text"]) if raw else "",
            "reference_token_hash": digest(raw["full_token_ids"]) if raw else ""}


def load_metrics(path: Path) -> dict[str, dict]:
    if not path.exists(): return {}
    return {str(row.get("request_id")): row for row in read_jsonl(path)
            if row.get("event") == "prefix_cache_request_observation" and row.get("initial_prefill_observation")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--experiment", choices=["common-hotpot", "free-generation", "zero-slack"], required=True)
    parser.add_argument("--policy", choices=["raw-order", "layout-only", "contractkv"], required=True)
    parser.add_argument("--model", required=True); parser.add_argument("--model-identity", choices=FROZEN_LEVELS, required=True)
    parser.add_argument("--base-url", required=True); parser.add_argument("--cell-id", required=True)
    parser.add_argument("--repeat", type=int, required=True); parser.add_argument("--policy-hash", required=True)
    parser.add_argument("--output-budget", type=int, default=0); parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--metrics-events", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(); args.protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    samples = read_jsonl(args.sessions); rows = []; certificates = {}; previous_ids = {}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists(): raise RuntimeError("A fresh cell cannot resume or overwrite an existing raw file")
    turns = 10; cell_started = time.perf_counter()
    def append(row):
        rows.append(row)
        with args.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=True) + "\n")
    for cohort_start in range(0, len(samples), args.protocol["runtime"]["concurrency"]):
        cohort = samples[cohort_start:cohort_start + args.protocol["runtime"]["concurrency"]]
        for sample in cohort:
            sid = sample["revision_session_id"]; prepared = make_turn(args, sample, 0); budget = budget_for(args, sample)
            requested_level = prepared[2]["layout_level"]; salt = args.policy_hash + ":" + sid
            if args.policy == "contractkv" and requested_level != "L0":
                cert = certify(args, sample, prepared, budget, salt)
            else:
                cert = {"certificate_issued": False, "verify_decision": "NOT_REQUIRED" if requested_level == "L0" else "NOT_RUN",
                        "txn_state": "NOT_RUN", "committed_tokens": 0, "registration_ms": 0, "verify_endpoint_ms": 0,
                        "output_budget": budget, "reference_prompt": "raw-order"}
            certificates[sid] = cert
            effective = args.policy == "layout-only" and requested_level != "L0" or args.policy == "contractkv" and bool(cert.get("certificate_issued"))
            warm_messages = prepared[4] if effective else prepared[3]
            warm = stream_generate(args, warm_messages, budget, args.cell_id + "-warm-" + sid, salt if effective else None)
            previous_ids[sid] = tokenize(args.base_url, args.model, warm_messages, True, args.timeout)
            append({"row_type": "canary", "model": args.model_identity, "repeat": args.repeat,
                    "session_id": sid, "family": sample["revision_family"], "requested_level": requested_level,
                    "policy": args.policy, "turn_id": 0, **cert, "warm_success": warm["success"]})
        for turn in range(1, turns):
            jobs = []; batch_started = time.perf_counter()
            for sample in cohort:
                sid = sample["revision_session_id"]; prepared = make_turn(args, sample, turn)
                cert = certificates[sid]; budget = budget_for(args, sample)
                issued = bool(cert.get("certificate_issued")); requested_level = prepared[2]["layout_level"]
                effective = args.policy == "layout-only" and requested_level != "L0" or args.policy == "contractkv" and issued
                messages = prepared[4] if effective else prepared[3]
                ids = tokenize(args.base_url, args.model, messages, True, args.timeout)
                scope_ok = not issued or (cert["output_budget"] == budget and
                           digest(ids[:cert["stable_prefix_tokens"]]) == cert["stable_prefix_hash"])
                if not scope_ok:
                    effective = False; messages = prepared[3]
                    ids = tokenize(args.base_url, args.model, messages, True, args.timeout)
                rid = args.cell_id + "-" + sid + "-t" + str(turn)
                order = (prepared[2] if effective else prepared[1])["topological_order"]
                jobs.append((sample, messages, budget, rid, args.policy_hash + ":" + sid if effective else None,
                             ids, effective, scope_ok, requested_level, order))
            with ThreadPoolExecutor(max_workers=args.protocol["runtime"]["concurrency"]) as pool:
                outputs = list(pool.map(lambda job: stream_generate(args, job[1], job[2], job[3], job[4]), jobs))
            wall_ms = (time.perf_counter() - batch_started) * 1000
            for job, output in zip(jobs, outputs):
                sample, messages, budget, rid, salt, ids, effective, scope_ok, level, order = job
                sid = sample["revision_session_id"]
                score, metric, source = standard_score(str(sample["dataset"]), str(sample["task"]), output["output_text"], sample.get("answer", ""))
                append({"row_type": "future", "model": args.model_identity, "repeat": args.repeat,
                        "policy": args.policy, "session_id": sid, "source_group": sample["revision_source_group"],
                        "family": sample["revision_family"], "dataset": sample["dataset"], "task": sample["task"],
                        "turn_id": turn, "requested_level": level, "effective_level": level if effective else "L0",
                        "certificate_issued": bool(certificates[sid].get("certificate_issued")),
                        "scope_check_pass": scope_ok, "scope_invalid_admission": effective and not scope_ok,
                        "exact_prompt_lcp_tokens": lcp_length(previous_ids[sid], ids), "batch_wall_ms": wall_ms,
                        "actual_prompt_tokens": len(ids), "prompt_sha256": digest(ids), "output_budget": budget,
                        "task_score": score, "task_metric": metric, "metric_source": source,
                        "prompt_order": order, **output})
                previous_ids[sid] = ids
            print(json.dumps({"cell": args.cell_id, "cohort": cohort_start, "turn": turn, "future_rows": sum(r["row_type"] == "future" for r in rows)}), flush=True)
    time.sleep(.5); metrics = load_metrics(args.metrics_events)
    for row in rows:
        if row["row_type"] != "future": continue
        metric = metrics.get(row["request_id"], {})
        row["metric_join_success"] = bool(metric)
        for field in ("prefix_hit_tokens", "free_gpu_blocks", "used_gpu_blocks", "reused_physical_blocks", "block_size"):
            row[field] = metric.get(field, "unavailable")
        row["new_prefill_tokens"] = max(0, int(metric["prompt_tokens"]) - int(metric["prefix_hit_tokens"])) if metric else "unavailable"
        row["dynamic_suffix_reuse_tokens"] = max(0, int(metric["prefix_hit_tokens"]) - row["exact_prompt_lcp_tokens"]) if metric else "unavailable"
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=True) + "\n" for row in rows), encoding="utf-8")
    future = [r for r in rows if r["row_type"] == "future"]
    summary = {"schema_version": "tsc-revision-live-cell.v1", "cell_id": args.cell_id, "status": "complete",
               "expected_future_requests": len(samples) * (turns - 1), "future_requests": len(future),
               "successful_future_requests": sum(r["success"] for r in future),
               "token_evidence_requests": sum(r["token_ids_available"] for r in future),
               "metric_join_requests": sum(r["metric_join_success"] for r in future),
               "certified_sessions": sum(bool(c.get("certificate_issued")) for c in certificates.values()),
               "registration_total_ms": sum(float(c.get("registration_ms", 0)) for c in certificates.values()),
               "wall_time_s_including_registration": time.perf_counter() - cell_started,
               "source_file": str(args.output), "source_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
               "claim_boundary": "Fresh live finite-budget greedy generations; all registration work charged to wall time."}
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 0 if len(future) == summary["expected_future_requests"] else 2

if __name__ == "__main__": raise SystemExit(main())
