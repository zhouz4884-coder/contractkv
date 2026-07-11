from __future__ import annotations

import unittest

from scripts.phase15c_cache_state_conflict import choose_layout, predicted_common_prefix_blocks, summarize


class Phase15CCacheConflictTests(unittest.TestCase):
    def test_physical_policy_follows_confirmed_residency(self) -> None:
        self.assertEqual(choose_layout("physical-residency-caposc", True), "a-first")
        self.assertEqual(choose_layout("physical-residency-caposc", False), "b-first")
        self.assertEqual(choose_layout("static-posc", True), "b-first")

    def test_summary_reports_real_prefix_metrics(self) -> None:
        rows = [{"success": True, "quality_sanity": True, "ttft_ms": 10, "prefix_hit_tokens": 2048, "new_prefill_tokens": 32, "used_gpu_blocks": 20, "physical_feedback_available": True, "residency_error_blocks": 0}]
        result = summarize(rows, 1, "physical-residency-caposc")
        self.assertEqual(result["mean_prefix_hit_tokens"], 2048)
        self.assertEqual(result["within_one_block_rate"], 1.0)

    def test_prediction_uses_chat_template_common_prefix(self) -> None:
        class Tokenizer:
            def apply_chat_template(self, messages, tokenize, add_generation_prompt):
                return messages[0]["ids"]
        warm = [{"ids": list(range(40)) + [99]}]
        candidate = [{"ids": list(range(40)) + [100]}]
        self.assertEqual(predicted_common_prefix_blocks(Tokenizer(), warm, candidate, 16), 2)


if __name__ == "__main__":
    unittest.main()
