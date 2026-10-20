"""Independent descriptive audit of all bounded optional-study evidence."""
import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
frozen_source = Path(__file__).resolve().parents[1]/"results/tsc_exploratory_mechanisms_20261020/freeze_v2/source_snapshot"
if frozen_source.is_dir():
    sys.path.insert(0, str(frozen_source))
from scripts.phase20a_official_quality import standard_score
from scripts.phase17_live_common import digest

REL = Path("results/tsc_exploratory_mechanisms_20261020")
PARENT = Path("results/tsc_behavior_scope_repair_20261020")


def read(p): return json.loads(p.read_text(encoding="utf-8"))
def lines(p): return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def pairkey(r): return r["source_group"], r["tenant"], r["turn"], r["access"]


def analyze(root, output, partial=False):
    study = root/REL
    jobs = read(study/"jobs_v1.json")["jobs"]
    state = read(study/"execution_state_v2.json")
    if not partial: assert state["status"] == "COMPLETE_PENDING_ANALYSIS"
    samples = {s["revision_source_group"]: s for s in lines(root/PARENT/"inputs_validation_v1/sessions_v1.jsonl")}
    indexed, cells, controls, scopes = {}, [], [], []
    capacity, evictions = [], []
    input_files = []
    for job in jobs:
        cell = study/"runs"/job["id"]/"attempt1"
        if not (cell/"summary_v1.json").exists():
            if partial: continue
            raise RuntimeError("Missing cell: "+job["id"])
        ss = read(cell/"summary_v1.json")
        if not partial: assert read(cell/"completion_v1.json")["summary_sha256"] == sha(cell/"summary_v1.json")
        assert ss["raw_file_sha256"] == sha(cell/"responses.jsonl")
        assert ss["successful"] == ss["offered"] == job["expected_business"]
        assert read(cell/"measured_backend_drain_v1.json")["backend_request_counters_drained"]
        records = lines(cell/"responses.jsonl")
        rows = [r for r in records if r["row_type"] == "business"]
        regs = [r for r in records if r["row_type"] == "registration"]
        rpc = [r for r in records if r["row_type"] == "verification_request"]
        replies = {r["request_id"]: r for r in records if r["row_type"] == "verification_response"}
        native = {r["request_id"]: r for r in lines(cell/"metrics.jsonl")
                  if r.get("event") == "prefix_cache_request_observation" and r.get("initial_prefill_observation")}
        trace = lines(cell/"mechanism_trace.jsonl")
        trajectories = {r["request_id"]: r for r in trace if r["event"] == "fused_actual_trajectory"}
        assert len(rpc) == len(replies) == ss["actual_verification_RPCs"]
        kinds = {}
        intervals = []
        for r in records:
            if r["row_type"] in {"business", "reference_generation"}:
                result = r["result"]
                assert result["success"] and digest(result["prompt_token_ids"]) == result["prompt_ids_sha256"]
                event = native[result["request_id"]]
                assert event["prompt_tokens"] == len(result["prompt_token_ids"])
                kinds[result["request_id"]] = r["row_type"]
                start = result["first_time"] - result["ttft_ms"] / 1000
                intervals.append((start, result["end_time"], r["row_type"], r.get("source_group")))
            elif r["row_type"] == "verification_request":
                rid = r["request_id"]
                event = native[rid]
                expected = r["payload"]["verify_start_token"] if job["arm"].startswith("Fused") else len(r["payload"]["prompt_token_ids"])
                assert event["prompt_tokens"] == expected
                kinds[rid] = "verification"
                intervals.append((r["record_monotonic_s"], replies[rid]["record_monotonic_s"], "verification", None))
                response = replies[rid]["response"]
                if not response["certificate_issued"]: assert response["committed_tokens"] == 0
                if job["arm"].startswith("Fused"):
                    trajectory = trajectories[rid]
                    assert response["fused_output_ids"] == trajectory["actual_output_token_ids"]
                    assert response["fused_prompt_ids"] == trajectory["prompt_token_ids"]
                    if response["certificate_issued"]:
                        assert trajectory["actual_status"] == "FINISHED_STOPPED"
                        assert trajectory["actual_output_token_ids"] == trajectory["reference_output_token_ids"]
                        assert response["minimum_margin_guard_passed"] and response["candidate_margin_min"] >= .125
                        assert response["terminal_stop_margin"] >= .125
        assert all(native[rid]["total_gpu_blocks"] == job["pool_blocks"] for rid in kinds)
        prefill = Counter()
        for rid, kind in kinds.items():
            prefill[kind] += native[rid]["prompt_tokens"] - native[rid]["prefix_hit_tokens"]
        assert sum(prefill.values()) == ss["native_total_new_prefill"]
        physical = Counter()
        registered = {(r["source_group"], r["tenant"], r["turn"]): r for r in regs}
        for r in rows:
            result = r["result"]
            sample = samples[r["source_group"]]
            score, _, _ = standard_score(sample["dataset"], sample["task"], result["output_text"], sample.get("answer", ""))
            assert score == r["task_score"] and not r["scope_binding_errors"]
            assert abs(r["ready_ttft_ms"] - (result["first_time"] - r["planned_ready_time"]) * 1000) < 1e-6
            key = job["model"], job["arm"], *pairkey(r)
            assert key not in indexed
            indexed[key] = r
            if r["compiled"]:
                reg = registered[r["source_group"], r["tenant"], r["turn"]]
                n = native[result["request_id"]]["prefix_hit_tokens"]
                physical["full" if n >= reg["certificate"]["committed_tokens"] else "partial" if n else "zero"] += 1
        for r in regs:
            raw = next(x for x in rows if x["access"] == 0 and (x["source_group"], x["tenant"], x["turn"]) == (r["source_group"], r["tenant"], r["turn"]))
            scopes.append(dict(model=job["model"], arm=job["arm"], source=r["source_group"], tenant=r["tenant"], turn=r["turn"],
                PASS=r["certificate"]["certificate_issued"], reason=r["certificate"].get("failure_reason", ""),
                raw_margin_min=min(raw["result"].get("reference_margins", [-1])),
                raw_output_ids=raw["result"]["output_token_ids"], full_controller_ms=r["full_controller_ms"],
                stable_blocks=r["plan"]["stable_full_blocks"], commit_blocks=r["certificate"]["committed_tokens"]//16))
        groups = {r["source_group"]: r["certificate"]["committed_tokens"]//16 for r in regs if r["certificate"]["certificate_issued"]}
        capacity.append(dict(model=job["model"], arm=job["arm"], actual_pool=job["pool_blocks"],
            authorized_stable_working_set_blocks=sum(groups.values()), stable_groups=groups,
            maximum_observed_prompt_blocks=max((len(r["result"]["prompt_token_ids"])+15)//16 for r in rows),
            note="Stable set size alone does not include simultaneously active Raw/private/verification/decode blocks."))
        by_cause = Counter()
        for e in trace:
            if e["event"] != "allocate" or not e["evicted_hashes"]: continue
            if not ss["service_begin_time"] <= e["monotonic_s"] <= ss["service_end_time"]: continue
            cause = next(((kind, source) for start, end, kind, source in intervals if start <= e["monotonic_s"] <= end), ("auxiliary_or_unassigned", None))
            by_cause[cause[0]] += len(e["evicted_hashes"])
        evictions.append(dict(model=job["model"], arm=job["arm"], actual_cached_blocks_reclaimed_by_HTTP_kind=dict(by_cause),
            priority_skips=sum(e.get("skipped_priority", 0) for e in trace),
            priority_evictions=sum(e.get("priority_evictions", 0) for e in trace),
            priority_groups=[e for e in trace if e["event"] == "priority_group"],
            note="Counts are observed physical block reclamations; repeated hash copies/events are not independent evictions or model forwards."))
        cells.append(dict(**ss, physical_hits=dict(physical), native_new_prefill_by_kind=dict(prefill)))
        aux = cell/"auxiliary_controls_v2/summary_v2.json"
        if aux.exists():
            a = read(aux)
            if a["status"] == "COMPLETE_PENDING_NATIVE_AUDIT":
                rr = lines(aux.parent/"responses.jsonl")
                probes = []
                for r in rr:
                    if r["row_type"] != "aux_read_probe": continue
                    e = native[r["result"]["request_id"]]
                    probes.append(dict(condition=r["condition"], repeat=r["repeat"], prefix_hit_tokens=e["prefix_hit_tokens"],
                                       actual_prompt_tokens=e["prompt_tokens"]))
                releases = [e for e in trace if e["event"] == "native_candidate_release" and "-aux-" in e["request_id"]]
                assert len(probes) == 8
                a.update(model=job["model"], probes=probes, native_releases=releases,
                         cold_post_failure_all_zero=all(p["prefix_hit_tokens"] == 0 for p in probes if p["repeat"] == 0),
                         own_repeat_hits=all(p["prefix_hit_tokens"] > 0 for p in probes if p["repeat"] == 1),
                         all_observed_aborts_uncached=all(e["cached_blocks_before_release"] == 0 for e in releases if "ABORT" in e["actual_status"]))
                aborts = [e for e in releases if "ABORT" in e["actual_status"]]
                a["actual_abort_release_events"] = len(aborts)
                a["timeout_and_cancel_observed_at_native_release"] = {e["request_id"].split("-aux-",1)[1] for e in aborts} == {"timeout", "cancel"}
                a["all_observed_aborts_uncached"] = bool(aborts) and all(e["cached_blocks_before_release"] == 0 for e in aborts)
                passes = [r["body"] for r in rr if r["row_type"] == "aux_RPC" and "-aux-duplicate" in r["request_id"] and r.get("body",{}).get("certificate_issued")]
                a["repeated_valid_commit_same_certificate_identity"] = len(passes) == 2 and passes[0]["certificate_hash"] == passes[1]["certificate_hash"]
                a["physical_copy_deduplication_claimed"] = False
            controls.append(a)
        for name in ("responses.jsonl", "summary_v1.json", "metrics.jsonl", "mechanism_trace.jsonl"):
            input_files.append(dict(path=(cell/name).relative_to(root).as_posix(), sha256=sha(cell/name)))
    pairs = []
    for key, r in indexed.items():
        model, arm, source, tenant, turn, access = key
        if arm == "Raw" or (model, "Raw", source, tenant, turn, access) not in indexed: continue
        raw = indexed[model, "Raw", source, tenant, turn, access]
        same = (r["result"]["output_token_ids"], r["result"]["finish_reason"]) == (raw["result"]["output_token_ids"], raw["result"]["finish_reason"])
        delta = r["task_score"]-raw["task_score"]
        own = indexed[model, arm, source, tenant, turn, 0]
        own_same = (r["result"]["output_token_ids"], r["result"]["finish_reason"]) == (own["result"]["output_token_ids"], own["result"]["finish_reason"])
        pairs.append(dict(model=model, arm=arm, source=source, tenant=tenant, turn=turn, access=access,
                          compiled=r["compiled"], paired_Raw_IDs_EOS_equal=same,
                          own_Raw_witness_IDs_EOS_equal=own_same, Raw_score=raw["task_score"], score=r["task_score"],
                          delta=delta, down=delta < -.03, up=delta > .03))
    for cell in cells:
        model, arm = cell["job"]["model"], cell["job"]["arm"]
        raw_cell = next((x for x in cells if x["job"]["model"] == model and x["job"]["arm"] == "Raw"), None)
        if raw_cell: cell["Raw_wall_ratio"] = raw_cell["wall_s"]/cell["wall_s"]
        pp = [r for r in pairs if r["model"] == model and r["arm"] == arm]
        cc = [r for r in pp if r["compiled"]]
        cell["quality"] = dict(compiled=len(cc), compiled_vs_Raw_ID_or_EOS_changes=sum(not r["paired_Raw_IDs_EOS_equal"] for r in cc),
            compiled_vs_own_witness_changes=sum(not r["own_Raw_witness_IDs_EOS_equal"] for r in cc),
            compiled_score_drops=sum(r["down"] for r in cc), allroute_score_drops=sum(r["down"] for r in pp), allroute_score_ups=sum(r["up"] for r in pp),
            allroute_ID_or_EOS_changes=sum(not r["paired_Raw_IDs_EOS_equal"] for r in pp),
            compiled_positive_Raw_score_pairs=sum(r["Raw_score"]>0 for r in cc))
    if not partial: assert len(cells) == 12 and sum(c["offered"] for c in cells) == 384
    value = dict(status="PARTIAL" if partial else "COMPLETE", cells=cells, paired_business=pairs,
                 all_scope_decisions=scopes, capacity=capacity, allocation_evidence=evictions,
                 auxiliary_publication_controls=controls, original_files_hashed=input_files,
                 statistical_claim="Descriptive known-source development only; no CI or independent performance claim",
                 analysis_sha256=sha(Path(__file__)), new_GPU_requests=0)
    with output.open("x", encoding="utf-8") as f: json.dump(value, f, indent=2, ensure_ascii=False); f.write("\n")
    print(json.dumps(dict(status=value["status"], cells=len(cells), business=sum(c["offered"] for c in cells))))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--partial", action="store_true")
    a = p.parse_args(); analyze(a.root, a.output, a.partial)
