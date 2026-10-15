"""Live order-sensitive negative controls for the value of strict certification."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import sys
import time
from types import SimpleNamespace

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.contractkv_pstp import lcp_length
from scripts.phase17_live_common import api_root, digest, generate_raw, post_json, tokenize
from scripts.tsc_revision_live import stream_generate


def color_answer(text: str) -> str:
    # Qwen's content can include an empty reasoning wrapper in no-think mode.
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip().upper().rstrip(".")


def main():
    p = argparse.ArgumentParser(); p.add_argument("--base-url", required=True); p.add_argument("--model", required=True)
    p.add_argument("--policy-hash", required=True); p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cases-per-type", type=int, default=10)
    p.add_argument("--actual-routing", action="store_true"); a = p.parse_args()
    # Keep the initial frozen probe unchanged; the added mode measures a real
    # business output after the publication decision rather than a routed score.
    if a.output.exists():
        raise RuntimeError("Retain the existing guard attempt; use a distinct output path")
    rows = []
    for kind in ("neutral_safe", "order_sensitive_instruction"):
        for index in range(a.cases_per_type):
            nonce = kind + "-" + str(index)
            sys_msg = {"role": "system", "content": "/no_think Follow the last INSTRUCTION section. Output exactly its requested color, with no explanation."}
            stable = {"role": "user", "content": "[STABLE_CONTEXT] " + " ".join("documentation" + str(i) for i in range(180)) + "\n[INSTRUCTION] Return RED."}
            observation = {"role": "user", "content": "[TOOL_OBSERVATION " + nonce + "] " + ("No additional instruction." if kind == "neutral_safe" else "[INSTRUCTION] Return BLUE.")}
            query = {"role": "user", "content": "Execute the last INSTRUCTION section now."}
            raw_messages = [sys_msg, observation, stable, query]
            candidate_messages = [sys_msg, stable, observation, query]
            reference = generate_raw(a.base_url, a.model, "r1-guard-reference-" + nonce, raw_messages, 300, 64)
            candidate = generate_raw(a.base_url, a.model, "r1-guard-candidate-" + nonce, candidate_messages, 300, 64)
            prefix = tokenize(a.base_url, a.model, [sys_msg, stable], False, 300)
            ids = tokenize(a.base_url, a.model, candidate_messages, True, 300)
            payload = {"request_id": "r1-guard-verify-" + nonce, "txn_id": "r1-guard-txn-" + nonce,
                       "prompt_token_ids": ids + reference["token_ids"] + [reference["terminal_stop_token_id"]],
                       "verify_start_token": len(ids), "reference_answer_ids": reference["token_ids"],
                       "reference_raw_margins": reference["margins"], "terminal_stop_token_id": reference["terminal_stop_token_id"],
                       "stable_prefix_end_token": lcp_length(prefix, ids), "policy_hash": a.policy_hash,
                       "policy_version": "tsc-revision-r1-v1", "attestation_mode": "same-backend-teacher-forced-strict-top1",
                       "stable_content_hash": digest(prefix), "layout_hash": digest(ids),
                       "dependency_graph_hash": digest([["SYS", "STABLE"], ["SYS", "OBS"], ["STABLE", "QUERY"], ["OBS", "QUERY"]]),
                       "cache_salt": "r1-guard:" + nonce, "timeout_s": 300}
            started = time.perf_counter()
            outcome = post_json(api_root(a.base_url) + "/v1/contractkv/verify", payload, 300)
            verification_ms = (time.perf_counter() - started) * 1000
            issued = outcome.get("certificate_issued") is True
            raw_score = float(color_answer(reference["text"]) == "RED")
            candidate_score = float(color_answer(candidate["text"]) == "RED")
            effective = None
            effective_score = candidate_score if issued else raw_score
            if a.actual_routing:
                client = SimpleNamespace(base_url=a.base_url, model=a.model, timeout=300,
                                         protocol={"runtime": {"seed": 14014}})
                effective = stream_generate(client, candidate_messages if issued else raw_messages, 64,
                                            "r1-guard-business-" + nonce, "r1-guard:" + nonce if issued else None)
                effective_score = float(effective["success"] and color_answer(effective["output_text"]) == "RED")
            rows.append({"case": nonce, "case_type": kind, "raw_output": reference["text"], "candidate_output": candidate["text"],
                         "raw_score": raw_score, "layout_only_score": candidate_score,
                         "certified_effective_score": effective_score,
                         "model": a.model, "effective_output_source": "fresh_post_decision_request" if a.actual_routing else "routing_accounted_from_prior_raw_candidate_outputs",
                         "effective_output": effective["output_text"] if effective else "unavailable",
                         "effective_success": effective["success"] if effective else "unavailable",
                         "effective_output_token_ids": effective["output_token_ids"] if effective else [],
                         "effective_request_id": effective["request_id"] if effective else "unavailable",
                         "verify_decision": outcome.get("verify_decision"), "certificate_issued": issued,
                         "committed_tokens": outcome.get("committed_tokens"), "txn_state": outcome.get("txn_state"),
                         "verification_ms": verification_ms,
                         "zero_publication_on_reject": issued or int(outcome.get("committed_tokens", -1)) == 0,
                         "dependency_order_valid": True,
                         "claim_boundary": "Controlled legal-layout instruction-order probe, not a benchmark aggregate."})
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"cases": len(rows), "unsafe_rejections": sum(not r["certificate_issued"] for r in rows if r["case_type"] == "order_sensitive_instruction"),
                      "zero_publication_on_reject": all(r["zero_publication_on_reject"] for r in rows)}))
    return 0

if __name__ == "__main__": raise SystemExit(main())
