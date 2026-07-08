import unittest

from scripts.build_agent_workload_trace import build_trace_record
from scripts.evaluate_slo_goodput import aggregate_goodput
from scripts.run_live_workload_replay import compute_copy_stall, summarize_live_replay


class Phase7WorkloadTests(unittest.TestCase):
    def test_trace_record_contains_agent_workload_fields(self):
        sample = {
            "dataset": "RULER",
            "task": "niah",
            "sample_id": "0",
            "total_prompt_tokens": 100,
            "segments": [{"type": "USER_QUERY", "text": "hello", "token_count": 1}],
        }

        trace = build_trace_record(sample, index=0, slack_ms=50, arrival_time_ms=100)

        self.assertEqual(trace["trace_id"], "RULER-0-0")
        self.assertEqual(trace["tool_slack_ms"], 50)
        self.assertEqual(trace["arrival_time_ms"], 100)
        self.assertEqual(trace["slo_ttft_ms"], 200)
        self.assertTrue(trace["segments"])

    def test_copy_stall_uses_slack_window(self):
        self.assertEqual(compute_copy_stall(copy_ms=20, tool_slack_ms=0, copy_mode="critical_path"), 20)
        self.assertEqual(compute_copy_stall(copy_ms=20, tool_slack_ms=50, copy_mode="slack_window"), 0)
        self.assertEqual(compute_copy_stall(copy_ms=80, tool_slack_ms=50, copy_mode="slack_window"), 30)
        self.assertEqual(compute_copy_stall(copy_ms=80, tool_slack_ms=50, copy_mode="no_copy"), 0)

    def test_live_replay_summary_reports_policy_rates(self):
        rows = [
            {"policy": "ContractKV-Joint", "admitted": True, "slo_violation": False, "quality_budget_violation": False, "ttft_ms": 50, "tpot_ms": 20, "total_latency_ms": 90, "copy_residual_stall_ms": 0},
            {"policy": "ContractKV-Joint", "admitted": False, "slo_violation": True, "quality_budget_violation": True, "ttft_ms": 250, "tpot_ms": 30, "total_latency_ms": 300, "copy_residual_stall_ms": 10},
        ]

        summary = summarize_live_replay(rows)

        self.assertEqual(summary[0]["policy"], "ContractKV-Joint")
        self.assertEqual(summary[0]["num_requests"], 2)
        self.assertEqual(summary[0]["admission_rate"], 0.5)
        self.assertEqual(summary[0]["slo_violation_rate"], 0.5)

    def test_goodput_aggregation_uses_arrival_window(self):
        rows = [
            {"policy": "ContractKV-Joint", "dataset": "RULER", "arrival_time_ms": 0, "total_latency_ms": 100, "admitted": True, "slo_violation": False, "quality_budget_violation": False, "ttft_ms": 50, "tpot_ms": 20, "copy_residual_stall_ms": 0},
            {"policy": "ContractKV-Joint", "dataset": "RULER", "arrival_time_ms": 900, "total_latency_ms": 100, "admitted": True, "slo_violation": True, "quality_budget_violation": False, "ttft_ms": 250, "tpot_ms": 20, "copy_residual_stall_ms": 10},
        ]

        out = aggregate_goodput(rows)

        self.assertEqual(out[0]["policy"], "ContractKV-Joint")
        self.assertEqual(out[0]["admitted_requests_per_sec"], 2.0)
        self.assertEqual(out[0]["slo_compliant_requests_per_sec"], 1.0)


if __name__ == "__main__":
    unittest.main()
