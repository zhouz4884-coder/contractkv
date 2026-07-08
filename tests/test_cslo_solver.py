import unittest

from scripts.cslo_solver_v0 import (
    choose_joint_segment_plan,
    evaluate_joint_trace,
    make_risk_lookup,
)


class CsloSolverTests(unittest.TestCase):
    def test_joint_solver_emits_expected_trace_shape(self):
        sample = {
            "dataset": "LongBench",
            "task": "hotpotqa",
            "sample_id": "0",
            "total_prompt_tokens": 1000,
            "segments": [
                {"type": "RAG_CHUNK", "text": "ctx", "token_count": 800},
                {"type": "USER_QUERY", "text": "q", "token_count": 20},
            ],
        }
        risk_lookup = make_risk_lookup(
            [
                {"dataset": "LongBench", "task": "hotpotqa", "segment_type": "RAG_CHUNK", "action": "boundary_corruption", "mean_quality_drop": 0.04},
                {"dataset": "LongBench", "task": "hotpotqa", "segment_type": "RAG_CHUNK", "action": "boundary_repair_proxy", "mean_quality_drop": 0.01},
                {"dataset": "LongBench", "task": "hotpotqa", "segment_type": "USER_QUERY", "action": "boundary_corruption", "mean_quality_drop": 0.05},
            ]
        )
        cost_lookup = {
            ("precision_int4_proxy", "RAG_CHUNK"): {"estimated_latency_ms": 2, "estimated_memory_delta_mb": -24, "estimated_interference_penalty_ms": 0},
            ("precision_int8_proxy", "RAG_CHUNK"): {"estimated_latency_ms": 3, "estimated_memory_delta_mb": -16, "estimated_interference_penalty_ms": 0},
            ("repair_boundary_proxy", "RAG_CHUNK"): {"estimated_latency_ms": 4, "estimated_memory_delta_mb": 0, "estimated_interference_penalty_ms": 0},
            ("reuse_exact", "USER_QUERY"): {"estimated_latency_ms": 1, "estimated_memory_delta_mb": 0, "estimated_interference_penalty_ms": 0},
        }

        decision = evaluate_joint_trace(sample, risk_lookup, cost_lookup, quality_budget=0.02, slo_budget_ms=100)

        self.assertEqual(decision["policy"], "ContractKV-Joint")
        self.assertIn("segments", decision)
        self.assertTrue(all("selected_action" in s for s in decision["segments"]))
        self.assertTrue(decision["total_estimated_risk"] <= 0.02)
        self.assertTrue(decision["admitted"])

    def test_segment_plan_has_reuse_precision_placement_repair(self):
        plan = choose_joint_segment_plan("RAG_CHUNK", 1000, 0.005, quality_budget=0.02)

        self.assertEqual(set(plan.selected_action.keys()), {"reuse", "repair", "precision", "placement"})


if __name__ == "__main__":
    unittest.main()
