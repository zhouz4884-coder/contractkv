from __future__ import annotations

import unittest

from scripts.summarize_phase15a_fair_replication import summarize


class Phase15AFairReplicationTests(unittest.TestCase):
    def test_summary_requires_matching_content_signatures(self) -> None:
        rows = []
        for policy in ("vllm-raw-order", "static-posc", "contractkv-caposc"):
            rows.append({
                "concurrency": "1", "policy": policy, "_seed": "1", "_cell_path": policy,
                "success": "True", "quality_sanity": "True", "ttft_ms": "100", "tpot_ms": "10",
                "prefix_hit_tokens": "64", "observed_new_prefill_tokens": "32", "compiler_overhead_ms": "1",
                "metric_join_success": "True", "batch_wall_time_ms": "1000", "segment_multiset_sha256": "same",
            })
        self.assertTrue(all(row["fair_content_signature_match"] for row in summarize(rows)))

    def test_summary_detects_policy_content_mismatch(self) -> None:
        rows = []
        for policy, signature in (("vllm-raw-order", "a"), ("static-posc", "b"), ("contractkv-caposc", "a")):
            rows.append({
                "concurrency": "1", "policy": policy, "_seed": "1", "_cell_path": policy,
                "success": "True", "quality_sanity": "True", "ttft_ms": "100", "tpot_ms": "10",
                "prefix_hit_tokens": "64", "observed_new_prefill_tokens": "32", "compiler_overhead_ms": "1",
                "metric_join_success": "True", "batch_wall_time_ms": "1000", "segment_multiset_sha256": signature,
            })
        self.assertFalse(all(row["fair_content_signature_match"] for row in summarize(rows)))


if __name__ == "__main__":
    unittest.main()
