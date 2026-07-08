import tempfile
import unittest
from pathlib import Path

from scripts.build_anchor_residency_plan import (
    choose_anchor_boundary,
    compute_segment_block_span,
    estimate_action_conditioned_risk,
    load_risk_by_segment_type,
    make_anchor_residency_record,
    summarize_residency_plan,
)
from scripts.audit_vllm_v1_suffix_free import audit_suffix_free_path
from scripts.build_anchor_recompute_probe_summary import summarize_anchor_probe
from scripts.install_vllm_v1_anchor_recompute_probe import install as install_anchor_probe
from scripts.install_vllm_v1_anchor_recompute_probe import uninstall as uninstall_anchor_probe
from scripts.run_recompute_policy_pressure_eval import aggregate_pressure_metrics
from scripts.evaluate_recompute_policy_quality import compute_policy_quality_summary
from scripts.send_stream_probe_requests import make_prompt as make_stream_prompt
from scripts.send_stream_probe_requests import parse_stream_chunks
from scripts.build_phase10_5c_tier0_eval import build_policy_row
from scripts.build_phase10_5c_repeat_eval import build_repeat_rows, compute_slo_sweep_rows
from scripts.build_phase10_5c_tier2_eval import aggregate_tier2_rows, build_slo_sweep_rows


class Phase105AnchorPlannerTests(unittest.TestCase):
    def sample_segments(self):
        return [
            {"type": "SYS_PROMPT", "text": "system", "token_count": 64},
            {"type": "RAG_CHUNK", "text": "evidence", "token_count": 896},
            {"type": "CHAT_HISTORY", "text": "history", "token_count": 2048},
            {"type": "SCRATCHPAD", "text": "scratch", "token_count": 1024},
            {"type": "USER_QUERY", "text": "question", "token_count": 64},
        ]

    def test_compute_segment_block_span_uses_block_size_16(self):
        span = compute_segment_block_span(token_start=64, token_count=32, block_size=16)

        self.assertEqual(span["logical_block_start"], 4)
        self.assertEqual(span["logical_block_end"], 6)
        self.assertEqual(span["block_count"], 2)

    def test_user_query_can_be_in_recompute_suffix_but_not_dropped(self):
        decision = choose_anchor_boundary(
            segments=self.sample_segments(),
            risk_by_segment_type={
                "SYS_PROMPT": 1.0,
                "RAG_CHUNK": 0.45,
                "CHAT_HISTORY": 0.02,
                "SCRATCHPAD": 0.01,
                "USER_QUERY": 1.0,
            },
            block_size=16,
            risk_threshold=0.05,
            min_suffix_blocks=64,
            slack_ms=100,
            slo_margin_ms=180,
            recompute_ms_per_token=0.005,
            boundary_guard_blocks=2,
            planner_mode="rar_exact",
        )

        self.assertEqual(decision["residency_decision"], "release_suffix_candidate")
        self.assertEqual(decision["anchor_segment_index"], 0)
        self.assertIn("RAG_CHUNK", decision["recomputed_segment_types"])
        self.assertIn("USER_QUERY", decision["recomputed_segment_types"])
        self.assertNotIn("USER_QUERY", decision["dropped_segment_types"])
        self.assertEqual(decision["boundary_guard_tokens"], 32)
        self.assertEqual(decision["recompute_start_token"], decision["anchor_token_end"] - 32)
        self.assertGreater(decision["anchor_utility"], 0)
        self.assertTrue(decision["slack_feasible"])

    def test_action_conditioned_risk_separates_drop_from_exact_recompute(self):
        segment = {"type": "RAG_CHUNK", "token_count": 2048}
        risks = {"RAG_CHUNK": 0.8}

        drop_risk = estimate_action_conditioned_risk(segment, risks, "drop")
        truncate_risk = estimate_action_conditioned_risk(segment, risks, "truncate")
        recompute_risk = estimate_action_conditioned_risk(segment, risks, "exact_recompute")
        offload_risk = estimate_action_conditioned_risk(segment, risks, "offload")

        self.assertEqual(drop_risk, 0.8)
        self.assertEqual(truncate_risk, 0.8)
        self.assertLessEqual(recompute_risk, 0.01)
        self.assertEqual(offload_risk, 0.0)

    def test_eviction_strict_keeps_high_risk_suffix_fail_closed(self):
        segments = [
            {"type": "SYS_PROMPT", "text": "system", "token_count": 64},
            {"type": "RAG_CHUNK", "text": "evidence", "token_count": 2048},
            {"type": "USER_QUERY", "text": "question", "token_count": 64},
        ]

        decision = choose_anchor_boundary(
            segments=segments,
            risk_by_segment_type={"RAG_CHUNK": 0.8, "USER_QUERY": 1.0},
            block_size=16,
            risk_threshold=0.05,
            min_suffix_blocks=64,
            planner_mode="eviction_strict",
            slack_ms=200,
            slo_margin_ms=200,
        )

        self.assertEqual(decision["residency_decision"], "keep_full_request")
        self.assertEqual(decision["decision_reason"], "no_safe_recompute_suffix")

    def test_rar_exact_releases_high_eviction_risk_suffix_when_recompute_feasible(self):
        segments = [
            {"type": "SYS_PROMPT", "text": "system", "token_count": 64},
            {"type": "RAG_CHUNK", "text": "evidence", "token_count": 2048},
            {"type": "USER_QUERY", "text": "question", "token_count": 64},
        ]

        decision = choose_anchor_boundary(
            segments=segments,
            risk_by_segment_type={"RAG_CHUNK": 0.8, "USER_QUERY": 1.0},
            block_size=16,
            risk_threshold=0.05,
            min_suffix_blocks=64,
            planner_mode="rar_exact",
            slack_ms=200,
            slo_margin_ms=200,
            recompute_ms_per_token=0.005,
        )

        self.assertEqual(decision["residency_decision"], "release_suffix_candidate")
        self.assertEqual(decision["action_type"], "exact_recompute")
        self.assertEqual(decision["anchor_segment_index"], 0)
        self.assertIn("RAG_CHUNK", decision["recomputed_segment_types"])
        self.assertIn("USER_QUERY", decision["recomputed_segment_types"])
        self.assertEqual(decision["dropped_segment_types"], [])
        self.assertLessEqual(decision["estimated_quality_risk"], 0.01)
        self.assertTrue(decision["recompute_feasible"])
        self.assertTrue(decision["slack_feasible"])

    def test_anchor_boundary_keeps_full_request_when_no_reclaimable_suffix(self):
        segments = [
            {"type": "SYS_PROMPT", "text": "system", "token_count": 64},
            {"type": "TOOL_SCHEMA", "text": "schema", "token_count": 64},
        ]
        decision = choose_anchor_boundary(
            segments=segments,
            risk_by_segment_type={"SYS_PROMPT": 1.0, "TOOL_SCHEMA": 1.0},
            block_size=16,
            min_suffix_blocks=8,
        )

        self.assertEqual(decision["residency_decision"], "keep_full_request")
        self.assertEqual(decision["reclaimed_blocks"], 0)
        self.assertEqual(decision["recomputed_segment_types"], [])

    def test_anchor_residency_record_has_rar_fields(self):
        record = make_anchor_residency_record(
            trace_id="trace-1",
            request_id="req-1",
            dataset="LongBench",
            task="hotpotqa",
            segments=self.sample_segments(),
            risk_by_segment_type={
                "SYS_PROMPT": 1.0,
                "RAG_CHUNK": 0.5,
                "CHAT_HISTORY": 0.01,
                "SCRATCHPAD": 0.01,
                "USER_QUERY": 1.0,
            },
            block_size=16,
            tool_slack_ms=100,
            slo_margin_ms=180,
            boundary_guard_blocks=2,
            planner_mode="rar_exact",
        )

        for field in [
            "trace_id",
            "request_id",
            "dataset",
            "task",
            "block_size",
            "candidate_anchor_id",
            "anchor_token_end",
            "anchor_block_end",
            "reclaimed_blocks",
            "estimated_recompute_tokens",
            "estimated_recompute_ms",
            "slack_ms",
            "slo_margin_ms",
            "recompute_feasible",
            "slack_feasible",
            "anchor_utility",
            "action_type",
            "planner_mode",
            "boundary_guard_tokens",
            "recompute_start_token",
            "decision_reason",
            "recomputed_segment_types",
            "dropped_segment_types",
            "segments",
        ]:
            self.assertIn(field, record)
        self.assertGreater(len(record["segments"]), 0)
        self.assertEqual(record["dropped_segment_types"], [])

    def test_load_risk_by_segment_type_maps_real_risk_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "risk.csv"
            path.write_text(
                "dataset,task,condition,mean_quality_drop\n"
                "LongBench,hotpotqa,segment_eviction,0.5\n"
                "RepoBench,python_repository_completion,context_truncation,0.2\n"
                "RULER,niah_single_1,segment_eviction,1.0\n",
                encoding="utf-8",
            )

            risks = load_risk_by_segment_type(path)

        self.assertEqual(risks["RAG_CHUNK"], 0.5)
        self.assertEqual(risks["REPO_CONTEXT"], 0.2)
        self.assertEqual(risks["SYNTHETIC_CONTEXT"], 1.0)

    def test_summarize_residency_plan_reports_candidate_coverage(self):
        rows = [
            {
                "planner_mode": "rar_exact",
                "dataset": "RULER",
                "residency_decision": "release_suffix_candidate",
                "reclaimed_blocks": 64,
                "anchor_token_end": 1024,
                "boundary_guard_tokens": 32,
            },
            {
                "planner_mode": "rar_exact",
                "dataset": "LongBench",
                "residency_decision": "keep_full_request",
                "reclaimed_blocks": 0,
                "anchor_token_end": 0,
                "boundary_guard_tokens": 32,
            },
        ]

        summary = summarize_residency_plan(rows, "rar_exact")

        self.assertEqual(summary["planner_mode"], "rar_exact")
        self.assertEqual(summary["total_traces"], 2)
        self.assertEqual(summary["release_candidates"], 1)
        self.assertEqual(summary["keep_full_request"], 1)
        self.assertEqual(summary["candidate_coverage"], 0.5)
        self.assertEqual(summary["release_by_dataset"], "RULER:1")
        self.assertEqual(summary["estimated_recompute_tokens_saved_vs_full"], 992)


class Phase105SuffixFreeAuditTests(unittest.TestCase):
    def test_suffix_free_audit_reports_gate_and_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "v1" / "core" / "sched").mkdir(parents=True)
            (root / "v1" / "core").mkdir(exist_ok=True)
            (root / "v1" / "core" / "kv_cache_manager.py").write_text(
                "def get_block_ids(self, request_id): pass\n"
                "def free(self, request): self.coordinator.free(request.request_id)\n"
                "def cache_blocks(self, request, num_computed_tokens): pass\n",
                encoding="utf-8",
            )
            (root / "v1" / "core" / "block_pool.py").write_text(
                "def get_num_free_blocks(self): pass\n"
                "def free_block(self, block): pass\n",
                encoding="utf-8",
            )
            (root / "v1" / "core" / "sched" / "scheduler.py").write_text(
                "request.num_computed_tokens = anchor_token_end\n",
                encoding="utf-8",
            )

            report = audit_suffix_free_path(root)

        self.assertEqual(report["schema_version"], "phase10_5_suffix_free_audit_v0")
        self.assertIn(report["suffix_free_gate"], {"open_for_probe", "blocked"})
        self.assertIn("v1/core/kv_cache_manager.py", report["files"])
        self.assertIn("runtime_invariants", report)
        self.assertIn("prefix_blocks_retained_exact", report["runtime_invariants"])

    def test_anchor_probe_summary_requires_prefix_and_suffix_invariants(self):
        events = [
            {
                "event": "contractkv_anchor_recompute",
                "request_id": "req-1",
                "anchor_token_end": 1024,
                "recompute_start_token": 992,
                "boundary_guard_tokens": 32,
                "before_free_gpu_blocks": 100,
                "after_free_gpu_blocks": 164,
                "free_gpu_blocks_delta": 64,
                "suffix_blocks_freed": 64,
                "prefix_blocks_retained": 64,
                "num_computed_tokens_after": 1024,
                "prefix_blocks_retained_exact": True,
                "suffix_blocks_freed_exact": True,
                "duplicate_block_id_detected": False,
                "block_table_consistency": True,
            }
        ]
        requests = [{"success": True, "latency_ms": 200.0, "response_bytes": 512}]

        row = summarize_anchor_probe(events, requests, "qwen3-4b")

        self.assertTrue(row["anchored_recompute_success"])
        self.assertTrue(row["prefix_blocks_retained_exact"])
        self.assertTrue(row["suffix_blocks_freed_exact"])
        self.assertEqual(row["suffix_blocks_freed"], 64)
        self.assertEqual(row["num_computed_tokens_after"], 1024)

    def test_anchor_probe_installer_is_guarded_and_reversible(self):
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = Path(tmp) / "scheduler.py"
            original = (
                "class Scheduler:\n"
                "    def schedule(self) -> SchedulerOutput:\n"
                "        scheduled_timestamp = time.monotonic()\n"
                "        # First, schedule the RUNNING requests.\n"
                "        return SchedulerOutput()\n"
            )
            scheduler.write_text(original, encoding="utf-8")

            self.assertEqual(install_anchor_probe(scheduler), "installed")
            patched = scheduler.read_text(encoding="utf-8")
            self.assertIn("CONTRACTKV_ANCHOR_RECOMPUTE_PROBE", patched)
            self.assertIn("CONTRACTKV_ANCHOR_RECOMPUTE_MAX_EVENTS", patched)
            self.assertIn("_contractkv_anchor_recompute_seen_request_ids", patched)
            self.assertIn("_contractkv_anchor_recompute_once", patched)
            self.assertIn("anchor_token_end", patched)

            self.assertEqual(uninstall_anchor_probe(scheduler), "uninstalled")
            self.assertEqual(scheduler.read_text(encoding="utf-8"), original)


class Phase105PressureEvalTests(unittest.TestCase):
    def test_build_policy_row_combines_stream_and_actuator_event(self):
        stream = {
            "success": True,
            "ttft_ms": 100.0,
            "tpot_ms": 10.0,
            "total_latency_ms": 150.0,
            "error_type": "none",
            "error_message": "",
        }
        event = {
            "free_gpu_blocks_delta": 64,
            "suffix_blocks_freed": 64,
            "prefix_blocks_retained": 64,
            "anchor_token_end": 1024,
            "boundary_guard_tokens": 32,
            "before_free_gpu_blocks": 10,
            "after_free_gpu_blocks": 74,
        }

        row = build_policy_row("contractkv-rar-exact", stream, event, "qwen3-8b", 200)

        self.assertTrue(row["completed"])
        self.assertEqual(row["blocks_freed"], 64)
        self.assertEqual(row["full_recompute_tokens"], 2048)
        self.assertEqual(row["anchored_recompute_tokens"], 1024)
        self.assertEqual(row["recompute_tokens_saved_vs_full"], 1024)
        self.assertFalse(row["slo_violation"])

    def test_build_repeat_rows_pairs_stream_rows_with_events(self):
        streams = [
            {"success": True, "ttft_ms": 2100, "tpot_ms": 20, "total_latency_ms": 2300, "error_type": "none"},
            {"success": True, "ttft_ms": 2200, "tpot_ms": 21, "total_latency_ms": 2400, "error_type": "none"},
        ]
        events = [
            {"suffix_blocks_freed": 64, "prefix_blocks_retained": 64, "anchor_token_end": 1024, "boundary_guard_tokens": 32, "block_size": 16, "before_free_gpu_blocks": 10, "after_free_gpu_blocks": 74},
            {"suffix_blocks_freed": 64, "prefix_blocks_retained": 64, "anchor_token_end": 1024, "boundary_guard_tokens": 32, "block_size": 16, "before_free_gpu_blocks": 20, "after_free_gpu_blocks": 84},
        ]

        rows = build_repeat_rows("contractkv-rar-exact", streams, events, "qwen3-8b", 2500)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["run_id"], 0)
        self.assertEqual(rows[1]["blocks_freed"], 64)
        self.assertEqual(rows[1]["recompute_tokens_saved_vs_full"], 1024)
        self.assertFalse(rows[0]["slo_violation"])

    def test_compute_slo_sweep_rows_recomputes_goodput(self):
        raw_rows = [
            {"policy": "vllm-default", "completed": True, "ttft_ms": 1900, "tpot_ms": 20, "blocks_freed": 0, "free_gpu_blocks_before": 0, "free_gpu_blocks_after": 0, "full_recompute_tokens": 0, "anchored_recompute_tokens": 0, "error_type": "none"},
            {"policy": "vllm-default", "completed": True, "ttft_ms": 2600, "tpot_ms": 20, "blocks_freed": 0, "free_gpu_blocks_before": 0, "free_gpu_blocks_after": 0, "full_recompute_tokens": 0, "anchored_recompute_tokens": 0, "error_type": "none"},
        ]

        sweep = compute_slo_sweep_rows(raw_rows, [2000, 3000], duration_sec=2.0)
        by_slo = {row["slo_ttft_ms"]: row for row in sweep if row["policy"] == "vllm-default"}

        self.assertEqual(by_slo[2000]["slo_compliant_requests"], 1)
        self.assertEqual(by_slo[3000]["slo_compliant_requests"], 2)
        self.assertEqual(by_slo[3000]["slo_compliant_req_per_sec"], 1.0)

    def test_aggregate_tier2_rows_keeps_scenario_dimensions(self):
        rows = [
            {"policy": "vllm-default", "concurrent_requests": 2, "completed": True, "slo_violation": False, "ttft_ms": 1000, "tpot_ms": 20, "blocks_freed": 0, "free_gpu_blocks_before": 0, "free_gpu_blocks_after": 0, "full_recompute_tokens": 0, "anchored_recompute_tokens": 0, "error_type": "none"},
            {"policy": "contractkv-rar-exact", "concurrent_requests": 2, "completed": True, "slo_violation": False, "ttft_ms": 1200, "tpot_ms": 20, "blocks_freed": 64, "free_gpu_blocks_before": 10, "free_gpu_blocks_after": 74, "full_recompute_tokens": 2048, "anchored_recompute_tokens": 1024, "error_type": "none"},
            {"policy": "contractkv-rar-exact", "concurrent_requests": 2, "completed": True, "slo_violation": True, "ttft_ms": 2600, "tpot_ms": 20, "blocks_freed": 64, "free_gpu_blocks_before": 10, "free_gpu_blocks_after": 74, "full_recompute_tokens": 2048, "anchored_recompute_tokens": 1024, "error_type": "none"},
        ]

        summary = aggregate_tier2_rows(rows, duration_sec_by_key={("vllm-default", 2): 1.0, ("contractkv-rar-exact", 2): 2.0})
        by_policy = {row["policy"]: row for row in summary}

        self.assertEqual(by_policy["contractkv-rar-exact"]["concurrent_requests"], 2)
        self.assertEqual(by_policy["contractkv-rar-exact"]["completed_requests"], 2)
        self.assertEqual(by_policy["contractkv-rar-exact"]["slo_compliant_requests"], 1)
        self.assertEqual(by_policy["contractkv-rar-exact"]["total_blocks_freed"], 128)
        self.assertEqual(by_policy["contractkv-rar-exact"]["total_recompute_tokens_saved_vs_full"], 2048)

    def test_build_slo_sweep_rows_recomputes_tier2_slo_buckets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase10_5c3_vllm_default_c2_qwen3_8b.jsonl").write_text(
                '{"request_id":"req-default","success":true,"ttft_ms":2100,"tpot_ms":20,"total_latency_ms":2400,"error_type":"none"}\n',
                encoding="utf-8",
            )
            (root / "phase10_5c3_contractkv_rar_exact_c2_qwen3_8b.jsonl").write_text(
                '{"request_id":"req-rar","success":true,"ttft_ms":2600,"tpot_ms":20,"total_latency_ms":3000,"error_type":"none"}\n',
                encoding="utf-8",
            )
            (root / "phase10_5c3_contractkv_rar_exact_c2_qwen3_8b_events.jsonl").write_text(
                '{"request_id":"req-rar","block_size":16,"prefix_blocks_retained":64,"suffix_blocks_freed":64,"anchor_token_end":1024,"before_free_gpu_blocks":10,"after_free_gpu_blocks":74}\n',
                encoding="utf-8",
            )

            sweep = build_slo_sweep_rows(root, "qwen3-8b", 2, [2500, 3000])

        by_key = {(row["slo_ttft_ms"], row["policy"], row["concurrent_requests"]): row for row in sweep}

        self.assertEqual(by_key[(2500, "vllm-default", 2)]["slo_compliant_requests"], 1)
        self.assertEqual(by_key[(2500, "contractkv-rar-exact", 2)]["slo_compliant_requests"], 0)
        self.assertEqual(by_key[(3000, "contractkv-rar-exact", 2)]["slo_compliant_requests"], 1)
        self.assertEqual(by_key[(3000, "contractkv-rar-exact", 2)]["total_recompute_tokens_saved_vs_full"], 1024)

    def test_stream_probe_prompt_scales_with_target_words(self):
        prompt = make_stream_prompt(target_words=128, request_index=3)

        self.assertIn("Pressure request 3", prompt)
        self.assertGreaterEqual(len(prompt.split()), 128)
        self.assertTrue(prompt.endswith("Answer OK."))

    def test_stream_parser_captures_request_id(self):
        chunks = [
            {"id": "chatcmpl-1", "choices": [{"delta": {"content": "O"}}]},
            {"id": "chatcmpl-1", "choices": [{"delta": {"content": "K"}}]},
        ]

        parsed = parse_stream_chunks(chunks, started=1.0, token_times=[1.2, 1.4], ended=1.5)

        self.assertEqual(parsed["request_id"], "chatcmpl-1")
        self.assertEqual(parsed["output_text"], "OK")
        self.assertEqual(parsed["output_tokens"], 2)
        self.assertEqual(parsed["ttft_ms"], 200.0)

    def test_aggregate_pressure_metrics_reports_block_headroom_and_deltas(self):
        rows = [
            {
                "policy": "vllm-default",
                "completed": True,
                "slo_violation": False,
                "latency_ms": 100.0,
                "ttft_ms": 100.0,
                "tpot_ms": 10.0,
                "blocks_freed": 0,
                "free_gpu_blocks_before": 10,
                "free_gpu_blocks_after": 10,
                "full_recompute_tokens": 4096,
                "anchored_recompute_tokens": 4096,
                "error_type": "none",
            },
            {
                "policy": "vllm-default",
                "completed": False,
                "slo_violation": True,
                "latency_ms": 0.0,
                "ttft_ms": 300.0,
                "tpot_ms": 30.0,
                "blocks_freed": 0,
                "free_gpu_blocks_before": 10,
                "free_gpu_blocks_after": 10,
                "full_recompute_tokens": 4096,
                "anchored_recompute_tokens": 4096,
                "error_type": "capacity_failure",
            },
            {
                "policy": "contractkv-rar-exact",
                "completed": True,
                "slo_violation": False,
                "latency_ms": 120.0,
                "ttft_ms": 120.0,
                "tpot_ms": 12.0,
                "blocks_freed": 64,
                "free_gpu_blocks_before": 10,
                "free_gpu_blocks_after": 74,
                "full_recompute_tokens": 4096,
                "anchored_recompute_tokens": 1024,
                "error_type": "none",
            },
            {
                "policy": "contractkv-rar-exact",
                "completed": True,
                "slo_violation": False,
                "latency_ms": 130.0,
                "ttft_ms": 130.0,
                "tpot_ms": 14.0,
                "blocks_freed": 32,
                "free_gpu_blocks_before": 10,
                "free_gpu_blocks_after": 42,
                "full_recompute_tokens": 2048,
                "anchored_recompute_tokens": 1024,
                "error_type": "none",
            },
        ]

        summary = aggregate_pressure_metrics(rows, duration_sec=2.0)
        by_policy = {row["policy"]: row for row in summary}

        contract = by_policy["contractkv-rar-exact"]
        self.assertEqual(contract["completed_requests"], 2)
        self.assertEqual(contract["slo_compliant_requests"], 2)
        self.assertEqual(contract["total_blocks_freed"], 96)
        self.assertEqual(contract["mean_block_headroom_gain"], 48.0)
        self.assertEqual(contract["total_recompute_tokens_saved_vs_full"], 4096)
        self.assertEqual(contract["completion_lift_vs_default"], 1)
        self.assertEqual(contract["capacity_failure_reduction"], 1)
        self.assertEqual(contract["slo_goodput_delta_vs_default"], 0.5)
        self.assertEqual(contract["mean_ttft_ms"], 125.0)
        self.assertEqual(contract["p95_ttft_ms"], 130.0)
        self.assertEqual(contract["mean_tpot_ms"], 13.0)
        self.assertEqual(contract["p95_tpot_ms"], 14.0)


class Phase105QualityEvalTests(unittest.TestCase):
    def test_quality_summary_compares_exact_recompute_to_default(self):
        rows = [
            {"policy": "vllm-default", "dataset": "RULER", "score": 1.0, "error_type": "none"},
            {"policy": "full-recompute", "dataset": "RULER", "score": 0.99, "error_type": "none"},
            {"policy": "contractkv-rar-exact", "dataset": "RULER", "score": 0.98, "error_type": "none"},
            {"policy": "eviction-truncation", "dataset": "RULER", "score": 0.2, "error_type": "none"},
        ]

        summary = compute_policy_quality_summary(rows)
        by_policy = {row["policy"]: row for row in summary}

        self.assertAlmostEqual(by_policy["contractkv-rar-exact"]["quality_drop"], 0.02)
        self.assertAlmostEqual(by_policy["full-recompute"]["quality_drop"], 0.01)
        self.assertAlmostEqual(by_policy["eviction-truncation"]["quality_drop"], 0.8)
        self.assertTrue(by_policy["contractkv-rar-exact"]["quality_close_to_default"])
        self.assertTrue(by_policy["full-recompute"]["quality_close_to_default"])


if __name__ == "__main__":
    unittest.main()
