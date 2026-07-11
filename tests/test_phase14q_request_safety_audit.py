from __future__ import annotations

import unittest

from scripts.phase14q_request_safety_audit import pareto_prune, summarize, wilson_upper


class Phase14QRequestSafetyAuditTest(unittest.TestCase):
    def test_pareto_prune_removes_strictly_dominated_candidate(self) -> None:
        better = {"candidate_id": "a", "estimated_new_prefill_tokens": 10, "adjacency_preservation": 1, "predicted_risk": .1}
        worse = {"candidate_id": "b", "estimated_new_prefill_tokens": 20, "adjacency_preservation": .5, "predicted_risk": .2}
        self.assertEqual([row["candidate_id"] for row in pareto_prune([better, worse])], ["a"])

    def test_wilson_bound_is_fail_closed_for_no_samples(self) -> None:
        self.assertEqual(wilson_upper(0, 0), 1.0)
        self.assertLess(wilson_upper(0, 200), .03)

    def test_summary_applies_all_four_deployment_gates(self) -> None:
        rows = []
        for index in range(200):
            rows.append({
                "partition": "held_out_quality", "fallback_raw": False,
                "selected_unsafe": False, "selected_safe": True,
                "default_unsafe": index < 10, "unsafe_default_caught": index < 10,
                "oracle_safe_prefix_gain": 10, "retained_prefix_gain": 8,
                "exact_output_match": True,
            })
        held = next(row for row in summarize(rows, .1) if row["partition"] == "held_out_quality")
        self.assertTrue(held["deployment_gate_open"])
        self.assertEqual(held["safe_opportunity_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
