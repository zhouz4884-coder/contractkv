import unittest

from scripts.phase13c_capacity_analysis import analyze


class Phase13CCapacityAnalysisTests(unittest.TestCase):
    def test_joins_event_by_request_id(self):
        rows = [{"policy": "contractkv-caposc-sspp-rar", "concurrency": "8", "request_id": "r1", "success": "True", "capacity_failure": "False", "ttft_ms": "100", "tpot_ms": "10", "batch_wall_time_sec": "1"}]
        events = [{"request_id": "r1", "free_gpu_blocks_delta": 12, "suffix_blocks_freed": 12, "actuator_latency_ms": 0.1}]
        enriched, summary = analyze(rows, events, 3000)
        self.assertTrue(enriched[0]["event_joined"])
        self.assertEqual(summary[0]["positive_free_block_event_rows"], 1)
        self.assertEqual(summary[0]["sum_observed_free_block_delta"], 12.0)

    def test_unmatched_event_does_not_become_success(self):
        rows = [{"policy": "contractkv-caposc-sspp", "concurrency": "8", "request_id": "r1", "success": "False", "capacity_failure": "True", "ttft_ms": "0", "tpot_ms": "0", "batch_wall_time_sec": "1"}]
        enriched, summary = analyze(rows, [{"request_id": "other", "free_gpu_blocks_delta": 20}], 3000)
        self.assertFalse(enriched[0]["event_joined"])
        self.assertEqual(summary[0]["completed_requests"], 0)
        self.assertEqual(summary[0]["capacity_failures"], 1)


if __name__ == "__main__":
    unittest.main()
