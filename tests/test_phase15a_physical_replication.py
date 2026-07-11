from __future__ import annotations

import unittest

from scripts.summarize_phase15a_physical_replication import summarize


class Phase15APhysicalReplicationTests(unittest.TestCase):
    def test_summary_uses_concurrent_refcount_evidence(self) -> None:
        raw = [{
            "shared_target_tokens": "4096", "sessions": "2", "policy": "contractkv-caposc", "_seed": "1",
            "success": "True", "ttft_ms": "10", "prefix_hit_tokens": "4000", "content_multiset_sha256": "a",
        }, {
            "shared_target_tokens": "4096", "sessions": "2", "policy": "contractkv-caposc", "_seed": "1",
            "success": "True", "ttft_ms": "20", "prefix_hit_tokens": "4000", "content_multiset_sha256": "b",
        }]
        cells = [{
            "shared_target_tokens": "4096", "sessions": "2", "policy": "contractkv-caposc", "_seed": "1",
            "completed_requests": "2", "completion_rate": "1", "quality_sanity_rate": "1", "dedup_factor": "2",
            "effective_dedup_factor": "2", "peak_concurrent_dedup_factor": "2", "peak_concurrent_refcount_match_rate": "1",
            "used_block_high_water": "10", "minimum_free_blocks": "90",
        }]
        row = summarize(raw, cells)[0]
        self.assertEqual(row["peak_concurrent_dedup_factor"], 2.0)
        self.assertEqual(row["min_concurrent_refcount_match_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
