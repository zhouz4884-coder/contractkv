import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_real_quality_risk_summary import (
    aggregate_risk_summary,
    context_overflow_rows,
    is_context_overflow,
)
from scripts.summarize_vllm_runtime_probe import summarize_probe_events
from scripts.build_natural_swap_observation import summarize_natural_observation


class Phase102BAnd103ATests(unittest.TestCase):
    def test_context_overflow_is_detected_from_http_400_message(self):
        row = {
            "error_type": "HTTPError",
            "error_message": "This model's maximum context length is 32768 tokens. However, your request has 46781 input tokens.",
        }

        self.assertTrue(is_context_overflow(row))

    def test_risk_summary_uses_successful_requests_only(self):
        rows = [
            {"dataset": "LongBench", "task": "hotpotqa", "condition": "full_context_baseline", "score": 0.8, "error_type": "none"},
            {"dataset": "LongBench", "task": "hotpotqa", "condition": "segment_eviction", "score": 0.3, "error_type": "none"},
            {"dataset": "LongBench", "task": "hotpotqa", "condition": "segment_eviction", "score": 0.0, "error_type": "HTTPError", "error_message": "maximum context length"},
        ]

        summary = aggregate_risk_summary(rows)
        by_condition = {row["condition"]: row for row in summary}

        self.assertEqual(by_condition["full_context_baseline"]["mean_quality_drop"], 0.0)
        self.assertEqual(by_condition["segment_eviction"]["num_successful_requests"], 1)
        self.assertEqual(by_condition["segment_eviction"]["num_context_overflow"], 1)
        self.assertEqual(by_condition["segment_eviction"]["mean_quality_drop"], 0.5)

    def test_context_overflow_rows_extract_token_counts(self):
        rows = [
            {
                "dataset": "LongBench",
                "task": "narrativeqa",
                "sample_id": "4",
                "condition": "full_context_baseline",
                "error_type": "HTTPError",
                "error_message": "This model's maximum context length is 32768 tokens. However, your request has 46781 input tokens.",
            }
        ]

        overflows = context_overflow_rows(rows)

        self.assertEqual(overflows[0]["max_context_tokens"], 32768)
        self.assertEqual(overflows[0]["actual_input_tokens"], 46781)
        self.assertEqual(overflows[0]["status"], "capacity_failure")

    def test_probe_summary_reports_join_and_block_counter_coverage(self):
        events = [
            {
                "event": "sequence_group_state",
                "request_id": "r0",
                "seq_ids": [1],
                "prompt_token_count": 128,
                "block_size": 16,
                "logical_block_table_length": 8,
                "physical_block_ids": [10, 11, 12],
                "free_gpu_blocks": 100,
                "used_gpu_blocks": 20,
                "free_cpu_blocks": 50,
                "swapped_cpu_blocks": 0,
            },
            {
                "event": "scheduler_output",
                "request_id": "r0",
                "blocks_to_swap_in": [],
                "blocks_to_swap_out": [],
                "num_preempted": 0,
            },
        ]

        rows = summarize_probe_events(events)

        self.assertEqual(rows[0]["request_id"], "r0")
        self.assertTrue(rows[0]["has_block_table"])
        self.assertTrue(rows[0]["has_block_counters"])
        self.assertTrue(rows[0]["probe_join_success"])
        self.assertEqual(rows[0]["phase10_3b_gate"], "open")

    def test_probe_summary_closes_gate_without_block_table_join(self):
        rows = summarize_probe_events([{"event": "sequence_group_state", "request_id": "r0", "seq_ids": [1]}])

        self.assertFalse(rows[0]["has_block_table"])
        self.assertEqual(rows[0]["phase10_3b_gate"], "closed")

    def test_natural_observation_reports_preemption_without_swap(self):
        events = [
            {"event": "scheduler_output", "request_id": "r0", "blocks_to_swap_in": [], "blocks_to_swap_out": [], "num_preempted": 1},
            {"event": "sequence_group_state", "request_id": "r0", "free_gpu_blocks": 10, "used_gpu_blocks": 20},
        ]

        row = summarize_natural_observation(events, {"model": "qwen3-4b"})[0]

        self.assertEqual(row["observed_preemptions"], 1)
        self.assertEqual(row["observed_swap_events"], 0)
        self.assertEqual(row["actual_behavior"], "preemption_or_recompute_without_swap")


if __name__ == "__main__":
    unittest.main()
