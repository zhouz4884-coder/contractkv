import unittest

from scripts.phase12_posc_layout_compiler import (
    add_structural_anchors,
    canonical_all_order,
    compile_layout,
    expected_prefix_gain_tokens,
    validate_topological_order,
)
from scripts.phase12d_mixed_agent_task_builder import build_mixed_agent_cases
from scripts.phase12d_guarded_layout_replay import aggregate_phase12d_results


def mixed_code_segments():
    return [
        {"segment_id": "sys", "segment_type": "SYS_PROMPT", "text": "System", "token_count": 8, "dependencies": [], "volatility": 0.0, "cache_stability": 1.0},
        {"segment_id": "tool", "segment_type": "TOOL_OBS", "text": "Dynamic tool observation", "token_count": 16, "dependencies": ["sys"], "volatility": 1.0, "cache_stability": 0.0},
        {"segment_id": "repo_import", "segment_type": "REPO_IMPORT", "text": "import base", "token_count": 64, "dependencies": ["sys"], "volatility": 0.0, "cache_stability": 1.0},
        {"segment_id": "repo_class", "segment_type": "REPO_CLASS", "text": "class body", "token_count": 96, "dependencies": ["repo_import"], "volatility": 0.0, "cache_stability": 1.0},
        {"segment_id": "query", "segment_type": "USER_QUERY", "text": "query", "token_count": 8, "dependencies": ["tool", "repo_class"], "volatility": 0.2, "cache_stability": 0.0},
    ]


class POSCLayoutCompilerTests(unittest.TestCase):
    def test_posc_topological_sort_moves_stable_code_component_before_dynamic_tool_obs(self):
        result = compile_layout(mixed_code_segments(), policy="posc")

        self.assertEqual(result["layout_decision"], "partial_canonical")
        self.assertEqual(result["violated_edges"], [])
        self.assertLess(result["topological_order"].index("repo_import"), result["topological_order"].index("repo_class"))
        self.assertLess(result["topological_order"].index("repo_class"), result["topological_order"].index("tool"))
        self.assertLess(result["topological_order"].index("tool"), result["topological_order"].index("query"))
        self.assertGreater(result["expected_prefix_gain_tokens"], 0)

    def test_canonical_all_can_violate_dependency_edges(self):
        order = canonical_all_order(mixed_code_segments())
        violations = validate_topological_order(order, mixed_code_segments())

        self.assertIn(["repo_import", "repo_class"], violations)

    def test_structural_anchors_are_deterministic_and_counted(self):
        anchored = add_structural_anchors(mixed_code_segments())
        anchored_again = add_structural_anchors(mixed_code_segments())

        self.assertEqual([s["text"] for s in anchored], [s["text"] for s in anchored_again])
        self.assertTrue(all("[SEGMENT" in segment["text"] for segment in anchored))
        self.assertGreater(sum(segment["token_count"] for segment in anchored), sum(segment["token_count"] for segment in mixed_code_segments()))

    def test_expected_prefix_gain_stops_at_first_volatile_segment(self):
        order = ["sys", "repo_import", "repo_class", "tool", "query"]

        self.assertEqual(expected_prefix_gain_tokens(order, mixed_code_segments()), 168)

    def test_mixed_agent_builder_emits_dependency_order_sensitive_cases(self):
        cases = build_mixed_agent_cases(cases_per_type=1)
        case = next(item for item in cases if item["case_type"] == "code_tool")
        edges = case["dependency_edges"]

        self.assertIn(["repo_import", "repo_class"], edges)
        self.assertIn(["repo_class", "repo_function"], edges)
        self.assertEqual(case["expected_answer"], "MIXED_CODE_0")

    def test_phase12d_aggregation_shows_posc_beats_boolean_guard_on_mixed_case(self):
        rows = [
            {"workload": "Mixed-Agent", "policy": "raw-order", "layout_decision": "raw_order", "success": True, "quality_score": 1.0, "ttft_ms": 950, "total_latency_ms": 1050, "slo_ttft_ms": 700, "canonicalized_tokens": 0},
            {"workload": "Mixed-Agent", "policy": "boolean-guarded", "layout_decision": "raw_order", "success": True, "quality_score": 1.0, "ttft_ms": 900, "total_latency_ms": 1000, "slo_ttft_ms": 700, "canonicalized_tokens": 0},
            {"workload": "Mixed-Agent", "policy": "posc", "layout_decision": "partial_canonical", "success": True, "quality_score": 1.0, "ttft_ms": 120, "total_latency_ms": 240, "slo_ttft_ms": 700, "canonicalized_tokens": 4096},
            {"workload": "Mixed-Agent", "policy": "canonical-all", "layout_decision": "unsafe_canonical", "success": True, "quality_score": 0.0, "ttft_ms": 80, "total_latency_ms": 200, "slo_ttft_ms": 700, "canonicalized_tokens": 4096},
        ]

        summary = aggregate_phase12d_results(rows, slo_buckets_ms=[700])
        by_policy = {row["policy"]: row for row in summary}

        self.assertEqual(by_policy["posc"]["quality_drop_vs_raw"], 0.0)
        self.assertGreater(by_policy["posc"]["mean_canonicalized_tokens"], by_policy["boolean-guarded"]["mean_canonicalized_tokens"])
        self.assertGreater(by_policy["posc"]["slo_compliant_req_per_sec"], by_policy["boolean-guarded"]["slo_compliant_req_per_sec"])
        self.assertGreater(by_policy["canonical-all"]["quality_drop_vs_raw"], 0.5)


if __name__ == "__main__":
    unittest.main()
