from __future__ import annotations

import unittest

from scripts.phase14c_full_pool_qc_inputs import (
    adjacency_preservation,
    build_candidate_features,
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
    class FakeTokenizer:
        def encode(self, text, add_special_tokens=False):
            return str(text).split()

        def decode(self, ids, skip_special_tokens=True):
            return " ".join(ids)

        def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True):
            return (" ".join(message["content"] for message in messages)).split() + ["template"] * 8

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
        features = build_candidate_features(SAMPLE, stable_word_limit=64)
        jobs = build_jobs(features, None, "qwen3-8b", "/large/full.jsonl", "features.csv")
        self.assertEqual(len(jobs), 2)
        self.assertEqual(len({job["candidate_id"] for job in jobs}), 2)
        self.assertEqual(len({job["prompt_hash"] for job in jobs}), 2)
        self.assertNotIn("prompt", jobs[0])
        self.assertEqual(jobs[0]["full_pool_file"], "/large/full.jsonl")

    def test_summary_counts_jobs_per_partition_and_task(self):
        feature = build_feature(SAMPLE, stable_word_limit=64)
        jobs = build_jobs(build_candidate_features(SAMPLE, stable_word_limit=64), None, "qwen3-8b", "pool", "features")
        rows = summarize([feature], jobs)
        self.assertEqual(rows[0]["samples"], 1)
        self.assertEqual(rows[0]["fresh_quality_jobs"], 2)
        self.assertIn("not a calibrated final gate", rows[0]["claim_boundary"])

    def test_real_token_budget_truncates_before_manifest_identity(self):
        sample = {**SAMPLE, "segments": [dict(item) for item in SAMPLE["segments"]]}
        sample["segments"][1]["text"] = "context " * 300
        features = build_candidate_features(sample, stable_word_limit=0, tokenizer=self.FakeTokenizer(), max_model_len=300)
        self.assertTrue(all(feature["context_truncated"] for feature in features))
        self.assertTrue(all(int(feature["actual_prompt_tokens_after_chat_template"]) <= 300 - 128 for feature in features))


if __name__ == "__main__":
    unittest.main()
