import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.vllm_metadata_hook_proxy import build_metadata_record, write_metadata_logs
from scripts.vllm_observer_stats import OBSERVER_FIELDS, build_observer_row, join_metadata_observer
from scripts.vllm_prefetch_orchestrator_proxy import choose_copy_strategy, estimate_transfer_size_mb, run_orchestrator_replay
from scripts.run_phase9_metadata_observer_replay import aggregate_phase9_replay, build_replay_row


class Phase9MetadataHookTests(unittest.TestCase):
    def sample_trace(self):
        return {
            "trace_id": "RULER-0-0",
            "dataset": "RULER",
            "task": "niah",
            "sample_id": "0",
            "prompt_tokens": 1131,
            "tool_slack_ms": 50,
            "slo_ttft_ms": 200,
            "segments": [
                {"type": "SYS_PROMPT", "text": "sys", "token_count": 2},
                {"type": "SYNTHETIC_CONTEXT", "text": "ctx", "token_count": 1024},
                {"type": "USER_QUERY", "text": "query", "token_count": 5},
            ],
        }

    def sample_decision(self):
        return {
            "policy": "ContractKV-Joint",
            "admitted": True,
            "total_estimated_risk": 0.01,
            "quality_budget": 0.02,
            "slo_budget_ms": 200,
            "segments": [
                {"segment_id": "s0", "type": "SYS_PROMPT", "placement": "gpu_keep", "action": "reuse"},
                {"segment_id": "s1", "type": "SYNTHETIC_CONTEXT", "placement": "host_offload", "action": "reuse"},
            ],
        }

    def test_metadata_record_carries_request_lifecycle_fields(self):
        row = build_metadata_record(self.sample_trace(), self.sample_decision(), "ContractKV-Joint", request_index=3)

        self.assertEqual(row["request_id"], "ContractKV-Joint-RULER-0-0")
        self.assertEqual(row["trace_id"], "RULER-0-0")
        self.assertEqual(row["segment_token_counts"], [2, 1024, 5])
        self.assertEqual(row["risk_budget"], 0.02)
        self.assertEqual(row["slo_budget_ms"], 200)
        self.assertEqual(row["tool_slack_ms"], 50)
        self.assertIn("decision_plan", row)
        self.assertGreaterEqual(row["metadata_build_ms"], 0.0)

    def test_metadata_logs_are_jsonl_and_align_with_request_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "metadata.jsonl"
            rows = [build_metadata_record(self.sample_trace(), self.sample_decision(), "ContractKV-Joint", 0)]

            write_metadata_logs(out, rows)

            loaded = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(loaded[0]["request_id"], rows[0]["request_id"])
            self.assertEqual(loaded[0]["openai_response_format"], "unchanged")

    def test_observer_row_marks_block_stats_unavailable_without_faking(self):
        metadata = build_metadata_record(self.sample_trace(), self.sample_decision(), "ContractKV-Joint", 0)

        row = build_observer_row(metadata, ttft_ms=123.4, tpot_ms=12.3, gpu_memory_used_mb=2048)

        self.assertEqual(set(OBSERVER_FIELDS), set(row.keys()))
        self.assertEqual(row["request_id"], metadata["request_id"])
        self.assertEqual(row["prompt_tokens"], 1131)
        self.assertEqual(row["block_stats_available"], False)
        self.assertEqual(row["block_stats_source"], "unavailable_vllm_openai_observer")

    def test_metadata_observer_join_uses_request_id(self):
        metadata = build_metadata_record(self.sample_trace(), self.sample_decision(), "ContractKV-Joint", 0)
        observer = build_observer_row(metadata, ttft_ms=100, tpot_ms=10, gpu_memory_used_mb=1000)

        joined = join_metadata_observer([metadata], [observer])

        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0]["observer_join_success"], True)
        self.assertEqual(joined[0]["request_id"], metadata["request_id"])

    def test_orchestrator_selects_strategy_from_slack_and_transfer_size(self):
        self.assertEqual(choose_copy_strategy(tool_slack_ms=0, transfer_size_mb=512), "copy_now")
        self.assertEqual(choose_copy_strategy(tool_slack_ms=50, transfer_size_mb=512), "defer_to_slack")
        self.assertEqual(choose_copy_strategy(tool_slack_ms=10, transfer_size_mb=1024), "skip")
        self.assertEqual(estimate_transfer_size_mb(self.sample_trace()), 512)

    def test_orchestrator_replay_records_residual_stall(self):
        traces = [self.sample_trace()]
        rows = run_orchestrator_replay(traces, copy_ms_by_size={512: 40.0})

        self.assertEqual(rows[0]["request_id"], "ContractKV-Joint-RULER-0-0")
        self.assertEqual(rows[0]["copy_strategy"], "defer_to_slack")
        self.assertEqual(rows[0]["residual_stall_ms"], 0.0)
        self.assertFalse(rows[0]["real_kv_cache_movement"])

    def test_phase9_replay_row_combines_metadata_observer_and_orchestrator(self):
        metadata = build_metadata_record(self.sample_trace(), self.sample_decision(), "ContractKV-Joint", 0)
        observer = build_observer_row(metadata, ttft_ms=120, tpot_ms=11, gpu_memory_used_mb=1000)
        orchestrator = run_orchestrator_replay([self.sample_trace()], copy_ms_by_size={512: 40.0})[0]

        row = build_replay_row(metadata, observer, orchestrator)

        self.assertTrue(row["metadata_success"])
        self.assertTrue(row["observer_join_success"])
        self.assertEqual(row["policy"], "ContractKV-Joint")
        self.assertEqual(row["quality_violation_rate"], 0.0)
        self.assertEqual(row["residual_stall_ms"], 0.0)

    def test_phase9_aggregate_reports_rates(self):
        rows = [
            {"policy": "ContractKV-Joint", "metadata_success": True, "observer_join_success": True, "quality_violation_rate": 0.0, "slo_violation": False, "admitted": True, "controller_overhead_ms": 1.0, "observed_ttft_ms": 100, "observed_tpot_ms": 10, "residual_stall_ms": 0},
            {"policy": "ContractKV-Joint", "metadata_success": True, "observer_join_success": False, "quality_violation_rate": 0.0, "slo_violation": True, "admitted": True, "controller_overhead_ms": 2.0, "observed_ttft_ms": 250, "observed_tpot_ms": 12, "residual_stall_ms": 10},
        ]

        out = aggregate_phase9_replay(rows)

        self.assertEqual(out[0]["policy"], "ContractKV-Joint")
        self.assertEqual(out[0]["metadata_success_rate"], 1.0)
        self.assertEqual(out[0]["observer_join_success_rate"], 0.5)
        self.assertEqual(out[0]["quality_violation_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
