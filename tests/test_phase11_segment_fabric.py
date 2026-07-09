import unittest

from scripts.phase11_segment_fabric import (
    build_backend_policy_rows,
    build_canonical_slot_case,
    build_sspp_rows,
)


class Phase11SegmentFabricTests(unittest.TestCase):
    def test_canonical_slots_recover_stable_segment_after_dynamic_insert(self):
        sample = {
            "dataset": "RepoBench",
            "task": "repo_completion",
            "sample_id": "case-1",
            "segments": [
                {"type": "SYS_PROMPT", "text": "system", "token_count": 10},
                {"type": "REPO_CONTEXT", "text": "repo body", "token_count": 1000},
                {"type": "USER_QUERY", "text": "query", "token_count": 10},
            ],
        }

        row = build_canonical_slot_case(sample, tool_observation_tokens=50)

        self.assertEqual(row["raw_prefix_hit_tokens"], 10)
        self.assertEqual(row["canonical_slot_hit_tokens"], 1010)
        self.assertEqual(row["prefill_tokens_saved"], 1000)
        self.assertGreater(row["canonical_segment_cache_hit_rate"], row["raw_prefix_cache_hit_rate"])
        self.assertEqual(row["position_policy"], "same_slot_only")

    def test_sspp_slack_hides_preparation_work_and_tracks_waste(self):
        rows = build_sspp_rows(
            prepare_actions={"prefetch_512mb": 40.0},
            slack_buckets_ms=[0, 50, 100],
            prediction_hit_rates=[1.0, 0.5],
        )
        by_key = {(row["tool_slack_ms"], row["prediction_hit_rate"]): row for row in rows}

        self.assertEqual(by_key[(0, 1.0)]["critical_path_ms"], 40.0)
        self.assertEqual(by_key[(50, 1.0)]["critical_path_ms"], 0.0)
        self.assertEqual(by_key[(50, 1.0)]["hidden_work_ms"], 40.0)
        self.assertEqual(by_key[(50, 0.5)]["wasted_work_ms"], 20.0)
        self.assertEqual(by_key[(100, 1.0)]["hidden_fraction"], 1.0)

    def test_action_conditioned_backend_keeps_high_risk_segments_fp16(self):
        sample = {
            "dataset": "LongBench",
            "task": "hotpotqa",
            "sample_id": "case-2",
            "total_prompt_tokens": 1520,
            "segments": [
                {"type": "SYS_PROMPT", "text": "system", "token_count": 10},
                {"type": "RAG_CHUNK", "text": "evidence", "token_count": 1000},
                {"type": "CHAT_HISTORY", "text": "history", "token_count": 500},
                {"type": "USER_QUERY", "text": "query", "token_count": 10},
            ],
        }

        rows = build_backend_policy_rows([sample], quality_budget=0.03, slack_ms=100)
        by_policy = {row["policy"]: row for row in rows}

        self.assertTrue(by_policy["uniform-int4"]["quality_budget_violation"])
        self.assertFalse(by_policy["contractkv-int4"]["quality_budget_violation"])
        self.assertIn("RAG_CHUNK:keep_fp16", by_policy["contractkv-int4"]["segment_actions"])
        self.assertIn("CHAT_HISTORY:quantize_int4", by_policy["contractkv-int4"]["segment_actions"])
        self.assertGreater(by_policy["contractkv-int4"]["estimated_memory_saving_mb"], 0)
        self.assertLess(
            by_policy["contractkv-int4"]["estimated_memory_saving_mb"],
            by_policy["uniform-int4"]["estimated_memory_saving_mb"],
        )

    def test_real_low_risk_task_can_unlock_context_quantization(self):
        sample = {
            "dataset": "LongBench",
            "task": "lcc",
            "sample_id": "case-3",
            "total_prompt_tokens": 1020,
            "segments": [
                {"type": "SYS_PROMPT", "text": "system", "token_count": 10},
                {"type": "RAG_CHUNK", "text": "low risk context", "token_count": 1000},
                {"type": "USER_QUERY", "text": "query", "token_count": 10},
            ],
        }

        rows = build_backend_policy_rows(
            [sample],
            quality_budget=0.03,
            slack_ms=100,
            task_eviction_risk={("LongBench", "lcc"): 0.0},
        )
        contract = {row["policy"]: row for row in rows}["contractkv-int4"]

        self.assertFalse(contract["quality_budget_violation"])
        self.assertIn("RAG_CHUNK:quantize_int4", contract["segment_actions"])
        self.assertGreater(contract["estimated_memory_saving_mb"], 0)

    def test_high_risk_task_kept_fp16_does_not_count_quantization_risk(self):
        sample = {
            "dataset": "LongBench",
            "task": "hotpotqa",
            "sample_id": "case-4",
            "total_prompt_tokens": 1020,
            "segments": [
                {"type": "SYS_PROMPT", "text": "system", "token_count": 10},
                {"type": "RAG_CHUNK", "text": "high risk context", "token_count": 1000},
                {"type": "USER_QUERY", "text": "query", "token_count": 10},
            ],
        }

        rows = build_backend_policy_rows(
            [sample],
            quality_budget=0.03,
            slack_ms=100,
            task_eviction_risk={("LongBench", "hotpotqa"): 0.5},
        )
        contract = {row["policy"]: row for row in rows}["contractkv-int4"]

        self.assertFalse(contract["quality_budget_violation"])
        self.assertEqual(contract["estimated_quality_risk"], 0.0)
        self.assertIn("RAG_CHUNK:keep_fp16", contract["segment_actions"])


if __name__ == "__main__":
    unittest.main()
