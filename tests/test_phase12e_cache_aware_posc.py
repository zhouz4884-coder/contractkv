import unittest

from scripts.phase12e_cache_aware_posc import (
    SegmentPrefixLedger,
    aggregate_phase12e_results,
    cache_aware_posc_compile,
    estimate_lcp_tokens,
    layout_rebase_decision,
)
from scripts.phase12e_multiturn_trajectory_builder import build_multiturn_trajectories


def code_turn_segments(turn_id: int):
    segments = [
        {"segment_id": "sys", "segment_type": "SYS_PROMPT", "text": "system", "token_count": 8, "dependencies": [], "volatility": 0.0, "cache_stability": 1.0},
        {"segment_id": "repo_import", "segment_type": "REPO_IMPORT", "text": "import base", "token_count": 64, "dependencies": ["sys"], "volatility": 0.0, "cache_stability": 1.0},
        {"segment_id": "repo_class", "segment_type": "REPO_CLASS", "text": "class body", "token_count": 96, "dependencies": ["repo_import"], "volatility": 0.0, "cache_stability": 1.0},
        {"segment_id": "tool_obs_1", "segment_type": "TOOL_OBS", "text": "observation one", "token_count": 16, "dependencies": ["sys"], "volatility": 1.0, "cache_stability": 0.0},
    ]
    if turn_id >= 2:
        segments.append({"segment_id": "repo_function_2", "segment_type": "REPO_FUNCTION", "text": "new function", "token_count": 128, "dependencies": ["repo_class"], "volatility": 0.0, "cache_stability": 1.0})
    segments.append({"segment_id": "query", "segment_type": "USER_QUERY", "text": f"query {turn_id}", "token_count": 8, "dependencies": ["tool_obs_1"] + (["repo_function_2"] if turn_id >= 2 else ["repo_class"]), "volatility": 0.1, "cache_stability": 0.0})
    return segments


class CacheAwarePOSCTests(unittest.TestCase):
    def test_lcp_uses_segment_hash_and_stops_on_changed_segment(self):
        ledger = SegmentPrefixLedger()
        ledger.update("s1", 1, code_turn_segments(1), ["sys", "repo_import", "repo_class", "tool_obs_1", "query"])

        changed = code_turn_segments(1)
        changed[2] = dict(changed[2], text="class body changed")
        lcp = estimate_lcp_tokens(["sys", "repo_import", "repo_class", "tool_obs_1", "query"], changed, ledger)

        self.assertEqual(lcp["matched_tokens"], 72)
        self.assertEqual(lcp["matched_segment_ids"], ["sys", "repo_import"])

    def test_cache_aware_posc_keeps_boolean_lcp_when_static_posc_would_break_it(self):
        ledger = SegmentPrefixLedger()
        turn1 = code_turn_segments(1)
        ledger.update("s1", 1, turn1, ["sys", "repo_import", "repo_class", "tool_obs_1", "query"])

        result = cache_aware_posc_compile(code_turn_segments(2), ledger, session_id="s1", turn_id=2)
        boolean = next(item for item in result["candidates"] if item["policy"] == "boolean-guarded")

        self.assertEqual(result["violated_edges"], [])
        self.assertLessEqual(result["estimated_new_prefill_tokens"], boolean["estimated_new_prefill_tokens"])
        self.assertGreaterEqual(result["estimated_lcp_tokens"], boolean["estimated_lcp_tokens"])
        self.assertIn(result["selected_policy"], {"boolean-guarded", "cache-aware-posc"})

    def test_rebase_decision_requires_slack_and_amortized_saving(self):
        positive = layout_rebase_decision(rebase_cost_ms=80, future_saving_ms=30, expected_future_turns=4, tool_slack_ms=100)
        negative = layout_rebase_decision(rebase_cost_ms=80, future_saving_ms=30, expected_future_turns=4, tool_slack_ms=20)

        self.assertTrue(positive["should_rebase"])
        self.assertFalse(negative["should_rebase"])

    def test_multiturn_builder_emits_growth_and_dependencies(self):
        traces = build_multiturn_trajectories(trajectories_per_type=1, turns=6)

        self.assertEqual(len(traces), 18)
        turn6 = next(item for item in traces if item["trajectory_id"] == "code_0" and item["turn_id"] == 5)
        segment_ids = [segment["segment_id"] for segment in turn6["segments"]]
        self.assertIn("repo_function_5", segment_ids)
        self.assertIn(["repo_function_4", "repo_function_5"], turn6["dependency_edges"])

    def test_phase12e_aggregation_reports_lcp_and_rebase(self):
        rows = [
            {"policy": "boolean-guarded", "success": True, "quality_score": 1.0, "ttft_ms": 100.0, "total_latency_ms": 200.0, "estimated_lcp_tokens": 100, "actual_prompt_tokens": 300, "estimated_new_prefill_tokens": 200, "rebase_performed": False, "slo_ttft_ms": 150},
            {"policy": "cache-aware-posc", "success": True, "quality_score": 1.0, "ttft_ms": 70.0, "total_latency_ms": 150.0, "estimated_lcp_tokens": 180, "actual_prompt_tokens": 300, "estimated_new_prefill_tokens": 120, "rebase_performed": True, "slo_ttft_ms": 150},
        ]

        summary = aggregate_phase12e_results(rows, slo_buckets_ms=[150])
        by_policy = {row["policy"]: row for row in summary}

        self.assertGreater(by_policy["cache-aware-posc"]["mean_estimated_lcp_tokens"], by_policy["boolean-guarded"]["mean_estimated_lcp_tokens"])
        self.assertEqual(by_policy["cache-aware-posc"]["rebase_count"], 1)
        self.assertGreater(by_policy["cache-aware-posc"]["slo_compliant_req_per_sec"], 0)


if __name__ == "__main__":
    unittest.main()
