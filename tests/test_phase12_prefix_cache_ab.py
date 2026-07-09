import unittest

from scripts.phase12_prefix_cache_ab import (
    build_phase12_prompt_case,
    chunk_delta_content,
    quality_sanity,
    summarize_phase12_rows,
)


class Phase12PrefixCacheABTests(unittest.TestCase):
    def test_prompt_layout_places_tool_observation_before_stable_context_only_in_raw_order(self):
        raw = build_phase12_prompt_case("raw-order", stable_words=32, repeat_index=1)
        canonical = build_phase12_prompt_case("canonical-slot", stable_words=32, repeat_index=1)

        raw_turn2 = raw["turn2_messages"][1]["content"]
        canonical_turn2 = canonical["turn2_messages"][1]["content"]

        self.assertLess(raw_turn2.index("[TOOL_OBS]"), raw_turn2.index("[STABLE_CONTEXT]"))
        self.assertLess(canonical_turn2.index("[STABLE_CONTEXT]"), canonical_turn2.index("[TOOL_OBS]"))
        self.assertIn(raw["answer_marker"], canonical_turn2)
        self.assertEqual(raw["expected_answer"], canonical["expected_answer"])
        self.assertEqual(canonical["position_policy"], "canonical_slot_same_prefix")

    def test_quality_sanity_requires_expected_marker(self):
        self.assertTrue(quality_sanity("The answer is PHASE12_MARKER_7.", "PHASE12_MARKER_7"))
        self.assertFalse(quality_sanity("The answer is something else.", "PHASE12_MARKER_7"))

    def test_usage_only_stream_chunk_has_no_delta_content(self):
        self.assertEqual(chunk_delta_content({"choices": [], "usage": {"prompt_tokens": 10}}), "")

    def test_summary_reports_ttft_delta_without_faking_cached_tokens(self):
        rows = [
            {"layout": "raw-order", "repeat_id": 0, "success": True, "quality_sanity": True, "ttft_ms": 100.0, "tpot_ms": 10.0, "total_latency_ms": 150.0, "prompt_tokens": 1000, "cached_tokens": ""},
            {"layout": "raw-order", "repeat_id": 1, "success": True, "quality_sanity": True, "ttft_ms": 120.0, "tpot_ms": 10.0, "total_latency_ms": 170.0, "prompt_tokens": 1000, "cached_tokens": ""},
            {"layout": "canonical-slot", "repeat_id": 0, "success": True, "quality_sanity": True, "ttft_ms": 80.0, "tpot_ms": 10.0, "total_latency_ms": 130.0, "prompt_tokens": 1000, "cached_tokens": ""},
            {"layout": "canonical-slot", "repeat_id": 1, "success": True, "quality_sanity": True, "ttft_ms": 90.0, "tpot_ms": 10.0, "total_latency_ms": 140.0, "prompt_tokens": 1000, "cached_tokens": ""},
        ]

        summary = summarize_phase12_rows(rows, slo_ttft_ms=110)
        by_layout = {row["layout"]: row for row in summary}

        self.assertEqual(by_layout["raw-order"]["mean_ttft_ms"], 110.0)
        self.assertEqual(by_layout["canonical-slot"]["mean_ttft_ms"], 85.0)
        self.assertEqual(by_layout["canonical-slot"]["ttft_reduction_vs_raw_pct"], 22.727273)
        self.assertEqual(by_layout["canonical-slot"]["cached_tokens_observable"], False)
        self.assertEqual(by_layout["canonical-slot"]["quality_sanity_rate"], 1.0)
        self.assertEqual(by_layout["canonical-slot"]["slo_compliant_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
