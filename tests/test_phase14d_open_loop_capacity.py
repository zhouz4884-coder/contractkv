from __future__ import annotations

import argparse
import unittest

from scripts.phase14d_open_loop_capacity import summarize


class Phase14DOpenLoopCapacityTest(unittest.TestCase):
    def test_capacity_requires_completion_slo_and_queue_stability(self) -> None:
        args = argparse.Namespace(cell_id="x", policy="contractkv-caposc", arrival_rate_rps=4.0, seed=1, measurement_seconds=10.0, offered_requests=10, slo_ttft_ms=2000.0)
        rows = [{"success": True, "quality_sanity": True, "ttft_ms": 100, "tpot_ms": 1, "latency_ms": 110, "arrival_offset_ms": i * 1000, "scheduler_wait_ms": 2, "prefix_hit_tokens": 64, "observed_new_prefill_tokens": 10, "used_gpu_blocks": 5, "free_gpu_blocks": 99} for i in range(10)]
        self.assertTrue(summarize(rows, args)["capacity_stable"])
        rows[-1]["success"] = False
        self.assertFalse(summarize(rows, args)["capacity_stable"])


if __name__ == "__main__":
    unittest.main()
