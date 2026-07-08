import unittest

from scripts.bench_actual_context_scaling import (
    ACTUAL_CONTEXT_RAW_FIELDS,
    ACTUAL_CONTEXT_SUMMARY_FIELDS,
    summarize_runs,
)


class ActualContextScalingSchemaTests(unittest.TestCase):
    def test_raw_schema_is_fixed(self):
        self.assertEqual(
            ACTUAL_CONTEXT_RAW_FIELDS,
            [
                "timestamp",
                "run_id",
                "model",
                "configured_max_model_len",
                "actual_prompt_tokens_after_chat_template",
                "target_tokens",
                "prompt_source",
                "prompt_entropy_type",
                "max_num_seqs",
                "temperature",
                "generation_max_tokens",
                "ttft_ms",
                "tpot_ms",
                "total_latency_ms",
                "prompt_tokens",
                "completion_tokens",
                "peak_gpu_mem_gb",
                "vllm_kv_capacity",
                "startup_success",
                "runtime_success",
                "error_type",
                "error_message",
                "log_path",
                "gpu_monitor_path",
                "commit_hash",
            ],
        )

    def test_summary_schema_is_fixed(self):
        self.assertIn("p95_ttft_ms", ACTUAL_CONTEXT_SUMMARY_FIELDS)
        self.assertIn("p50_tpot_ms", ACTUAL_CONTEXT_SUMMARY_FIELDS)
        self.assertIn("prompt_source", ACTUAL_CONTEXT_SUMMARY_FIELDS)

    def test_summary_computes_mean_p50_and_p95(self):
        rows = [
            {"ttft_ms": "10", "tpot_ms": "1", "error_type": "none"},
            {"ttft_ms": "20", "tpot_ms": "2", "error_type": "none"},
            {"ttft_ms": "30", "tpot_ms": "3", "error_type": "none"},
        ]

        summary = summarize_runs(rows)

        self.assertEqual(summary["avg_ttft_ms"], 20.0)
        self.assertEqual(summary["p50_ttft_ms"], 20.0)
        self.assertEqual(summary["p95_ttft_ms"], 30.0)
        self.assertEqual(summary["avg_tpot_ms"], 2.0)


if __name__ == "__main__":
    unittest.main()
