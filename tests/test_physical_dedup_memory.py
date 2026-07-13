import tempfile
import unittest
from pathlib import Path

from scripts.summarize_physical_dedup_memory import (
    kv_geometry, mean_initial_prompt_allocations, summarize,
)


class PhysicalDedupMemoryTest(unittest.TestCase):
    def test_qwen_gqa_geometry_and_observed_block_conversion(self):
        config = {"num_hidden_layers": 36, "num_key_value_heads": 8,
                  "num_attention_heads": 32, "hidden_size": 4096, "head_dim": 128}
        self.assertEqual(kv_geometry(config), (36, 8, 128, 147456))
        base = {
            "sessions": "20", "shared_target_tokens": "4096", "completion_rate": "1",
            "quality_sanity_rate": "1", "block_size": "16", "minimum_free_blocks": "100",
            "peak_concurrent_refcount_match_rate": "1", "mean_ttft_ms": "100",
        }
        raw = {**base, "policy": "raw-order", "unique_physical_blocks_effective": "5000",
               "used_block_high_water": "6000", "mean_newly_allocated_blocks": "250",
               "unique_reused_physical_blocks": "0",
               "peak_concurrent_shared_blocks": "10", "peak_concurrent_logical_refs": "20",
               "peak_concurrent_unique_blocks": "10"}
        contract = {**base, "policy": "contractkv-caposc", "unique_physical_blocks_effective": "500",
                    "used_block_high_water": "1500", "mean_newly_allocated_blocks": "25",
                    "unique_reused_physical_blocks": "250",
                    "mean_ttft_ms": "20", "peak_concurrent_shared_blocks": "250",
                    "peak_concurrent_logical_refs": "5000",
                    "peak_concurrent_unique_blocks": "250"}
        row = summarize([raw, contract], "Qwen3-8B", config)[0]
        self.assertEqual(row["observed_physical_blocks_saved"], 4500)
        self.assertEqual(row["peak_used_blocks_saved"], 4500)
        self.assertAlmostEqual(row["kv_mib_per_block"], 2.25)
        self.assertAlmostEqual(row["peak_used_kv_gib_saved"], 4500 * 2.25 / 1024)
        self.assertEqual(row["net_concurrent_reference_blocks_avoided"], 4740)
        self.assertAlmostEqual(row["net_concurrent_kv_gib_saved"], 4740 * 2.25 / 1024)
        self.assertEqual(row["raw_mean_newly_allocated_blocks"], 250)
        self.assertEqual(row["contract_mean_newly_allocated_blocks"], 12.5)

    def test_initial_allocations_ignore_decode_lifetime_maximum(self):
        rows = [{
            "sessions": "10", "unique_physical_blocks_effective": "287",
            "unique_reused_physical_blocks": "257",
            "mean_newly_allocated_blocks": "260",
        }]
        self.assertEqual(mean_initial_prompt_allocations(rows), 3)


if __name__ == "__main__":
    unittest.main()
