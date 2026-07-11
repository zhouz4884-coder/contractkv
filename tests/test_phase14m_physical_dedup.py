from __future__ import annotations

import argparse
import unittest

from scripts.phase14m_physical_dedup import summarize


class Phase14MPhysicalDedupTest(unittest.TestCase):
    def test_dedup_factor_uses_logical_over_unique_reused_blocks(self) -> None:
        args = argparse.Namespace(experiment="warm", cell_id="x", policy="contractkv-caposc", shared_target_tokens=64, sessions=2)
        rows = [
            {"success": True, "quality_sanity": True, "ttft_ms": 10, "prompt_tokens": 80, "prefix_hit_tokens": 64, "reused_physical_blocks": 4, "newly_allocated_blocks": 1, "physical_block_ids": [1, 2, 3, 4, 8], "used_gpu_blocks": 6, "free_gpu_blocks": 100, "scheduler_wait_ms": 1, "primer": False},
            {"success": True, "quality_sanity": True, "ttft_ms": 20, "prompt_tokens": 80, "prefix_hit_tokens": 64, "reused_physical_blocks": 4, "newly_allocated_blocks": 1, "physical_block_ids": [1, 2, 3, 4, 9], "used_gpu_blocks": 7, "free_gpu_blocks": 99, "scheduler_wait_ms": 2, "primer": False},
        ]
        result = summarize(rows, args, 5.0)
        self.assertEqual(result["logical_reused_prefix_blocks"], 8)
        self.assertEqual(result["unique_reused_physical_blocks"], 4)
        self.assertEqual(result["dedup_factor"], 2.0)
        self.assertAlmostEqual(result["effective_dedup_factor"], 10 / 6)


if __name__ == "__main__":
    unittest.main()
