from __future__ import annotations

import unittest

from scripts.phase14c_full_pool_qc_inputs import (
    adjacency_preservation,
    build_feature,
    build_jobs,
    summarize,
)


SAMPLE = {
    "dataset": "LongBench",
    "task": "hotpotqa",
    "sample_id": "7",
    "answer": ["answer"],
    "metadata": {"phase14_partition": "calibration"},
    "segments": [
        {"type": "SYS_PROMPT", "text": "system", "token_count": 1},
        {"type": "RAG_CHUNK", "text": "Introduction\nThis paper proposes a cache-aware method.", "token_count": 8},
        {"type": "USER_QUERY", "text": "What is proposed?", "token_count": 3},
    ],
}


class Phase14CFullPoolQCInputsTests(unittest.TestCase):
    def test_adjacency_preservation_counts_raw_pairs_kept(self):
        self.assertEqual(adjacency_preservation(["a", "b", "c"], ["a", "b", "c"]), 1.0)
        self.assertEqual(adjacency_preservation(["a", "b", "c"], ["a", "c", "b"]), 0.0)

    def test_feature_uses_partition_and_structural_signals_without_labels(self):
        feature = build_feature(SAMPLE, stable_word_limit=64)
        self.assertEqual(feature["partition"], "calibration")
        self.assertEqual(feature["dataset"], "LongBench")
        self.assertEqual(feature["task"], "hotpotqa")
        self.assertIn(feature["risk_bucket"], {"needs_label_low_structure", "structural_fallback_candidate"})
        self.assertTrue(feature["needs_fresh_quality_label"])
        self.assertIn("RAG_CHUNK", feature["segment_type_signature"])

    def test_jobs_do_not_embed_prompt_text(self):
        feature = build_feature(SAMPLE, stable_word_limit=64)
        jobs = build_jobs([feature], ["raw-order", "contractkv-caposc"], "qwen3-8b", "/large/full.jsonl", "features.csv")
        self.assertEqual(len(jobs), 2)
        self.assertEqual({job["policy"] for job in jobs}, {"raw-order", "contractkv-caposc"})
        self.assertNotIn("prompt", jobs[0])
        self.assertEqual(jobs[0]["full_pool_file"], "/large/full.jsonl")

    def test_summary_counts_jobs_per_partition_and_task(self):
        feature = build_feature(SAMPLE, stable_word_limit=64)
        rows = summarize([feature], ["raw-order", "contractkv-caposc"])
        self.assertEqual(rows[0]["samples"], 1)
        self.assertEqual(rows[0]["fresh_quality_jobs"], 2)
        self.assertIn("not a calibrated final gate", rows[0]["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
