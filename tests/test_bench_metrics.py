import unittest

from scripts.bench_openai_ttft_tpot import (
    ERROR_TYPES,
    MODEL_FEASIBILITY_FIELDS,
    compute_tpot_ms,
    classify_error,
)


class BenchMetricsTests(unittest.TestCase):
    def test_model_feasibility_schema_is_fixed(self):
        self.assertEqual(
            MODEL_FEASIBILITY_FIELDS,
            [
                "timestamp",
                "phase",
                "model",
                "model_path",
                "backend",
                "gpu_ids",
                "tensor_parallel_size",
                "dtype",
                "max_model_len",
                "max_num_seqs",
                "gpu_memory_utilization",
                "port",
                "startup_success",
                "startup_time_sec",
                "idle_gpu_mem_gb",
                "peak_gpu_mem_gb",
                "ttft_ms",
                "tpot_ms",
                "output_tokens",
                "error_type",
                "error_message",
                "log_path",
                "commit_hash",
            ],
        )

    def test_error_types_are_normalized(self):
        self.assertEqual(
            ERROR_TYPES,
            {
                "none",
                "cuda_unavailable",
                "model_incomplete",
                "oom_startup",
                "oom_runtime",
                "vllm_import_error",
                "api_timeout",
                "bad_output",
                "port_conflict",
            },
        )

    def test_tpot_uses_average_interval_after_first_token(self):
        self.assertEqual(compute_tpot_ms(first_token_time=1.0, end_time=2.2, output_tokens=4), 400.0)
        self.assertIsNone(compute_tpot_ms(first_token_time=1.0, end_time=2.2, output_tokens=1))

    def test_error_classifier_detects_common_failures(self):
        self.assertEqual(classify_error("CUDA initialization failed"), "cuda_unavailable")
        self.assertEqual(classify_error("CUDA out of memory during startup"), "oom_startup")
        self.assertEqual(classify_error("Read timed out"), "api_timeout")
        self.assertEqual(classify_error(""), "none")


if __name__ == "__main__":
    unittest.main()
