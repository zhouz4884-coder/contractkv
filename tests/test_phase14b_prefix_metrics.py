from __future__ import annotations

import unittest

from scripts.summarize_vllm_prefix_metrics import summarize


class Phase14BPrefixMetricsTest(unittest.TestCase):
    def test_aggregates_initial_hit_and_chunked_prefill(self) -> None:
        rows = summarize([
            {
                "event": "prefix_cache_request_observation", "request_id": "req-a",
                "initial_prefill_observation": True, "prompt_tokens": 100,
                "prefix_lookup_tokens": 100, "prefix_hit_tokens": 64,
                "new_prefill_tokens_this_iteration": 20, "reused_physical_blocks": 4,
                "newly_allocated_blocks": 2, "scheduler_wait_ms": 7.5,
                "prefix_cache_evictions": None, "prefill_gpu_ms": None, "decode_gpu_ms": None,
            },
            {
                "event": "prefix_cache_request_observation", "request_id": "req-a",
                "initial_prefill_observation": False, "prompt_tokens": 100,
                "prefix_lookup_tokens": None, "prefix_hit_tokens": None,
                "new_prefill_tokens_this_iteration": 16, "reused_physical_blocks": None,
                "newly_allocated_blocks": 3, "scheduler_wait_ms": None,
                "prefix_cache_evictions": None, "prefill_gpu_ms": None, "decode_gpu_ms": None,
            },
        ])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["prefix_hit_tokens"], 64)
        self.assertEqual(row["new_prefill_tokens"], 36)
        self.assertEqual(row["newly_allocated_blocks"], 3)
        self.assertIn("prefill_gpu_ms", row["metric_availability"])

    def test_ignores_non_observation_events(self) -> None:
        self.assertEqual(summarize([{"event": "prefix_cache_probe_error"}]), [])


if __name__ == "__main__":
    unittest.main()
