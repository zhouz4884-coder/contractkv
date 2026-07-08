import tempfile
import unittest
from pathlib import Path

from scripts.build_anchor_residency_plan import (
    choose_anchor_boundary,
    compute_segment_block_span,
    load_risk_by_segment_type,
    make_anchor_residency_record,
)
from scripts.audit_vllm_v1_suffix_free import audit_suffix_free_path
from scripts.build_anchor_recompute_probe_summary import summarize_anchor_probe
from scripts.install_vllm_v1_anchor_recompute_probe import install as install_anchor_probe
from scripts.install_vllm_v1_anchor_recompute_probe import uninstall as uninstall_anchor_probe
from scripts.run_recompute_policy_pressure_eval import aggregate_pressure_metrics


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
        )

        self.assertEqual(decision["residency_decision"], "release_suffix_candidate")
        self.assertEqual(decision["anchor_segment_index"], 1)
        self.assertIn("USER_QUERY", decision["recomputed_segment_types"])
        self.assertNotIn("USER_QUERY", decision["dropped_segment_types"])
        self.assertEqual(decision["boundary_guard_tokens"], 32)
        self.assertEqual(decision["recompute_start_token"], decision["anchor_token_end"] - 32)
        self.assertGreater(decision["anchor_utility"], 0)
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
            "slack_feasible",
            "anchor_utility",
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
            self.assertIn("_contractkv_anchor_recompute_once", patched)
            self.assertIn("anchor_token_end", patched)

            self.assertEqual(uninstall_anchor_probe(scheduler), "uninstalled")
            self.assertEqual(scheduler.read_text(encoding="utf-8"), original)


class Phase105PressureEvalTests(unittest.TestCase):
    def test_aggregate_pressure_metrics_reports_block_headroom_and_deltas(self):
        rows = [
            {
                "policy": "vllm-default",
                "completed": True,
                "slo_violation": False,
                "latency_ms": 100.0,
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
                "blocks_freed": 0,
                "free_gpu_blocks_before": 10,
                "free_gpu_blocks_after": 10,
                "full_recompute_tokens": 4096,
                "anchored_recompute_tokens": 4096,
                "error_type": "capacity_failure",
            },
            {
                "policy": "contractkv-anchored-recompute",
                "completed": True,
                "slo_violation": False,
                "latency_ms": 120.0,
                "blocks_freed": 64,
                "free_gpu_blocks_before": 10,
                "free_gpu_blocks_after": 74,
                "full_recompute_tokens": 4096,
                "anchored_recompute_tokens": 1024,
                "error_type": "none",
            },
            {
                "policy": "contractkv-anchored-recompute",
                "completed": True,
                "slo_violation": False,
                "latency_ms": 130.0,
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

        contract = by_policy["contractkv-anchored-recompute"]
        self.assertEqual(contract["completed_requests"], 2)
        self.assertEqual(contract["slo_compliant_requests"], 2)
        self.assertEqual(contract["total_blocks_freed"], 96)
        self.assertEqual(contract["mean_block_headroom_gain"], 48.0)
        self.assertEqual(contract["total_recompute_tokens_saved_vs_full"], 4096)
        self.assertEqual(contract["completion_lift_vs_default"], 1)
        self.assertEqual(contract["capacity_failure_reduction"], 1)
        self.assertEqual(contract["slo_goodput_delta_vs_default"], 0.5)


if __name__ == "__main__":
    unittest.main()
