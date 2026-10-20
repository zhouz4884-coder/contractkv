"""Bounded mechanism microstudy, retaining exact-input business comparisons."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import time
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tsc_template_task_protocol_v2 import prepared, candidate_plan, budget, ServingAuthority
from scripts.tsc_behavior_scope_protocol_v2 import StrictServingAuthority, actual_prefix_errors
from scripts.contractkv_exact_behavior import digest as exact_digest
from scripts.tsc_revision_r2_candidate_plan import verification_request
from scripts.phase17_live_common import digest, tokenize, post_json, api_root
from scripts.phase20a_official_quality import standard_score
from scripts.tsc_template_task_serving_client_v1 import stats
from scripts.tsc_revision_final_fixed_client_v2 import finish_after_backend_drain
from scripts.tsc_exploratory_native_v1 import MODE


def read(p): return json.loads(p.read_text(encoding="utf-8"))
def lines(p): return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main(args):
    begin = time.perf_counter()
    job = read(args.job)
    arm = job["arm"]
    args.cell_id, args.model_identity = job["id"], job["model"]
    assert not args.output.exists() and not args.summary.exists()
    args.output.touch()
    recorded = []
    def record(row):
        value = dict(record_monotonic_s=time.perf_counter(), **row)
        recorded.append(value)
        with args.output.open("a", encoding="utf-8") as f:
            f.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    parent = args.study.parent / "tsc_behavior_scope_repair_20261020"
    input_dir = parent / ("inputs_" + job["input_set"] + "_v1")
    samples = lines(input_dir / "sessions_v1.jsonl")
    shapes = {(r["source_group"], r["tenant"], r["turn"], r["level"]): r for r in
              lines(input_dir / "CPU_shapes_v1.jsonl") if r["model"] == job["model"]}
    raw_arm = arm.startswith("Raw")
    tf_only = arm == "TF-only"
    fused = arm.startswith("Fused")
    cls = ServingAuthority if raw_arm or tf_only else StrictServingAuthority
    auth = cls(args, read(args.identity), samples, 8, sha(args.study / "protocol_v1.json"))
    certificates = {}
    record(dict(row_type="service_epoch", begin=begin, job=job,
                evidence_protocol="TF-only exploratory comparator" if tf_only else "actual Raw and Candidate generation",
                protocol_sha256=sha(args.study / "protocol_v1.json")))

    def register(sample, tenant, turn, raw):
        started = time.perf_counter()
        source = sample["revision_source_group"]
        plan = candidate_plan(args, sample, tenant, turn)
        cert = dict(certificate_issued=False, committed_tokens=0, attempts=[], failure_reason="",
                    stable_prefix_tokens=plan["stable_prefix_end_token"], stable_prefix_hash=plan["stable_content_hash"])
        bound = behavior = candidate = None
        margins = raw.get("reference_margins", [])
        if (not raw.get("witness_available") or len(margins) != len(raw["output_token_ids"])
                or not all(math.isfinite(x) for x in margins) or min(margins, default=-1) < .0625
                or raw["finish_reason"] != "stop"):
            cert["failure_reason"] = "Raw_margin_or_EOS_ineligible"
        else:
            if not fused and not tf_only:
                candidate = auth.private_generate(sample, plan["messages"], budget(sample),
                    args.cell_id + f"-candidate-{len(certificates)}", False, kind="strict-candidate")
                record(dict(row_type="reference_generation", source_group=source, tenant=tenant, turn=turn,
                            reference_kind="ACTUAL_PRIVATE_CANDIDATE", result=candidate))
                if not candidate["success"] or candidate["finish_reason"] != "stop":
                    cert["failure_reason"] = "candidate_incomplete"
                elif candidate["output_token_ids"] != raw["output_token_ids"]:
                    cert["failure_reason"] = "Raw_candidate_free_generation_differs"
            if not cert["failure_reason"]:
                rid = args.cell_id + f"-verify-{len(certificates)}"
                payload, evidence = verification_request(args, plan, raw, rid,
                    auth.cache.require(auth.cache_identity(sample)), True, "bounded-development-mechanism-v1")
                if fused:
                    payload["attestation_mode"] = MODE
                record(dict(row_type="verification_request", request_id=rid, payload=payload, **evidence))
                t = time.perf_counter()
                response = post_json(api_root(args.base_url) + "/v1/contractkv/verify", payload, args.timeout)
                elapsed = (time.perf_counter() - t) * 1000
                record(dict(row_type="verification_response", request_id=rid, response=response, actual_HTTP_ms=elapsed))
                cert.update(response)
                cert["attempts"] = [dict(request_id=rid, actual_HTTP_ms=elapsed)]
                if fused:
                    candidate = dict(success=response.get("fused_finish") == "stop",
                                     prompt_token_ids=response.get("fused_prompt_ids"),
                                     output_token_ids=response.get("fused_output_ids"),
                                     finish_reason=response.get("fused_finish"),
                                     provenance="actual EngineCore decode rows returned before free")
                    record(dict(row_type="fused_candidate_evidence", source_group=source,
                                tenant=tenant, turn=turn, candidate=candidate))
                if cert["certificate_issued"]:
                    assert cert["minimum_margin_guard_passed"] and cert["raw_margin_min"] >= .0625
                    assert cert["candidate_margin_min"] >= .125 and cert["terminal_stop_margin"] >= .125
                    assert not actual_prefix_errors(plan["prompt_token_ids"], cert)
                    bound = auth.bind(sample, plan, cert)
                    if not tf_only:
                        behavior = auth.behavior.issue(raw, candidate, cert, raw["prompt_token_ids"],
                            plan["prompt_token_ids"], "RAW_QUERY", exact_digest(raw["prompt_token_ids"]))
                else:
                    assert cert["committed_tokens"] == 0
        row = dict(row_type="registration", source_group=source, tenant=tenant, turn=turn,
                   plan=plan, certificate=cert, bound=bound, behavior=behavior,
                   full_controller_ms=(time.perf_counter() - started) * 1000)
        record(row)
        return row

    responses = []
    ready = begin
    for access in range(job["accesses"]):
        for sample in samples:
            source = sample["revision_source_group"]
            for tenant, turn in [(0, 1), (1, 1)]:
                started = time.perf_counter()
                key = source, tenant, turn
                first = key not in certificates
                _, _, raw_messages = prepared(sample, tenant, turn, "L0")
                raw_ids = tokenize(args.base_url, args.model, raw_messages, True, args.timeout)
                assert digest(raw_ids) == shapes[source, tenant, turn, "L0"]["prompt_ids_sha256"]
                saved = certificates.get(key)
                compiled = bool(saved and saved["certificate"]["certificate_issued"])
                errors = []
                messages = raw_messages
                if compiled:
                    plan = candidate_plan(args, sample, tenant, turn)
                    if tf_only:
                        errors = auth.admit(sample, tenant, turn, plan, saved["certificate"], saved["bound"])
                        errors += actual_prefix_errors(plan["prompt_token_ids"], saved["certificate"])
                    else:
                        errors = auth.admit(sample, tenant, turn, plan, saved["certificate"], saved["bound"],
                            raw_ids=raw_ids, candidate_ids=plan["prompt_token_ids"], behavior=saved["behavior"])
                    assert not errors
                    messages = plan["messages"]
                witness = first and not raw_arm and sample["revision_family"] == "HotpotQA"
                result = auth.generate(sample, tenant, messages, budget(sample),
                    args.cell_id + f"-business-{len(responses)}", witness)
                assert result["success"], "Preserve failed whole cell, no auto-retry"
                level = "L3" if compiled else "L0"
                assert result["prompt_ids_sha256"] == shapes[source, tenant, turn, level]["prompt_ids_sha256"]
                score, metric, scorer = standard_score(sample["dataset"], sample["task"], result["output_text"], sample.get("answer", ""))
                row = dict(row_type="business", sequence=len(responses), source_group=source,
                           family=sample["revision_family"], tenant=tenant, turn=turn, access=access,
                           compiled=compiled, level=level, started=started, planned_ready_time=ready,
                           ready_ttft_ms=(result["first_time"] - ready) * 1000, task_score=score,
                           task_metric=metric, metric_source=scorer, result=result, scope_binding_errors=errors)
                record(row)
                responses.append(row)
                ready = result["end_time"]
                if first:
                    certificates[key] = register(sample, tenant, turn, result) if witness else None
    end = finish_after_backend_drain(args)
    events = {r["request_id"]: r for r in lines(args.metrics_events)
              if r.get("event") == "prefix_cache_request_observation" and r.get("initial_prefill_observation")}
    for row in recorded[:]:
        if row["row_type"] in {"business", "reference_generation"}:
            event = events[row["result"]["request_id"]]
            assert event["prompt_tokens"] == len(row["result"]["prompt_token_ids"])
        elif row["row_type"] == "verification_request":
            event = events[row["request_id"]]
            expected = row["payload"]["verify_start_token"] if fused else len(row["payload"]["prompt_token_ids"])
            assert event["prompt_tokens"] == expected
    summary = dict(status="COMPLETE", execution_complete=True, job=job, offered=len(responses),
        successful=len(responses), compiled_business=sum(r["compiled"] for r in responses),
        wall_s=end - begin, service_begin_time=begin, service_end_time=end,
        actual_verification_RPCs=sum(r["row_type"] == "verification_request" for r in recorded),
        full_controller_ms=sum(r["full_controller_ms"] for r in recorded if r["row_type"] == "registration"),
        ready_TTFT_ms=stats([r["ready_ttft_ms"] for r in responses]),
        failed_reasons=dict(Counter(r["certificate"].get("failure_reason", "") for r in recorded
                           if r["row_type"] == "registration" and not r["certificate"]["certificate_issued"])),
        native_initial_events=len(events), native_total_new_prefill=sum(r["prompt_tokens"] - r["prefix_hit_tokens"] for r in events.values()),
        raw_file_sha256=sha(args.output), boundary="One development process per arm/model, no independent efficacy claim")
    assert len(responses) == job["expected_business"]
    with args.summary.open("x", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(summary))
    if arm == "Fused":
        from scripts.tsc_exploratory_controls_v2 import run as auxiliary_controls
        auxiliary_controls(args, auth, samples, recorded)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("study", "job", "identity", "output", "summary", "metrics-events"):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("base-url", "model", "policy-hash"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--timeout", type=float, default=900)
    main(p.parse_args())
