"""Run the original open-loop service harness with raw-reference attestation."""
from __future__ import annotations
import os
from pathlib import Path
import secrets
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import tsc_real_task_open_loop as service
from scripts.contractkv_pstp import lcp_length
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages
from scripts.phase17_live_common import api_root, digest, generate_raw, post_json, tokenize
from scripts.tsc_service_template_quality_live import scope_record, stable_prefix_order


def raw_reference_template_verify(args, sample, prepared, max_tokens):
    begin = time.perf_counter()
    case = prepared["case"]; candidate_messages = prepared["compiled_messages"]
    order = prepared["compiled_layout"]["topological_order"]
    raw = generate_raw(args.base_url, args.model,
                       args.cell_id + "-raw-reference-" + sample["service_template_id"],
                       prepared["raw_messages"], args.timeout, max_tokens)
    raw_reference_ms = (time.perf_counter() - begin) * 1000
    prefix_messages = quality_messages(case, _ordered_text(stable_prefix_order(case, order), case["segments"]))
    prefix_ids = tokenize(args.base_url, args.model, prefix_messages, False, args.timeout)
    candidate_ids = tokenize(args.base_url, args.model, candidate_messages, True, args.timeout)
    stable_end = lcp_length(prefix_ids, candidate_ids); scope = scope_record(args, sample, prepared)
    payload = {
        "request_id": args.cell_id + "-verify-" + sample["service_template_id"],
        "txn_id": args.cell_id + "-txn-" + sample["service_template_id"],
        "prompt_token_ids": candidate_ids + raw["token_ids"] + [raw["terminal_stop_token_id"]],
        "verify_start_token": len(candidate_ids), "reference_answer_ids": raw["token_ids"],
        "reference_raw_margins": raw["margins"], "terminal_stop_token_id": raw["terminal_stop_token_id"],
        "stable_prefix_end_token": stable_end, "policy_hash": args.policy_hash,
        "policy_version": "tsc-revision-r1-v1", "attestation_mode": "same-backend-teacher-forced-strict-top1",
        "stable_content_hash": digest(prefix_ids), "layout_hash": digest(candidate_ids),
        "dependency_graph_hash": digest([(seg["segment_id"], seg.get("dependencies", [])) for seg in case["segments"]]),
        "timeout_s": args.timeout, "cache_salt": args.policy_hash + ":" + sample["service_template_id"],
    }
    started = time.perf_counter()
    body = post_json(api_root(args.base_url) + "/v1/contractkv/verify", payload, args.timeout)
    return {**body, "verification_ms": (time.perf_counter() - started) * 1000,
            "raw_reference_ms": raw_reference_ms, "complete_registration_ms": (time.perf_counter() - begin) * 1000,
            "reference_prompt": "raw-order", "stable_prefix_tokens": stable_end,
            "scope_record": scope, "scope_digest": digest(scope)}


def main():
    # Keep the frozen service runner and arrival process; replace only its
    # candidate self-reference with the raw-reference attestation requested by R1.
    service.verify_template = raw_reference_template_verify
    os.environ.setdefault("CONTRACTKV_R1_CERTIFICATE_SECRET", secrets.token_hex(32))
    sys.argv.extend(["--certificate-secret", os.environ["CONTRACTKV_R1_CERTIFICATE_SECRET"]])
    return service.main()

if __name__ == "__main__": raise SystemExit(main())
