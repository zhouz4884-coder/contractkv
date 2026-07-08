import unittest

from scripts.run_trace_controller_eval import POLICIES, aggregate_policy_metrics


class TraceControllerEvalTests(unittest.TestCase):
    def test_all_required_policies_are_registered(self):
        self.assertEqual(
            set(POLICIES),
            {
                "Full-Recompute",
                "Prefix-Reuse-Only",
                "Quantization-Only",
                "Offload-Only",
                "Repair-Only",
                "ContractKV-Indep",
                "ContractKV-Joint",
            },
        )

    def test_aggregate_policy_metrics_reports_violation_rates(self):
        rows = [
            {"admitted": True, "total_estimated_latency_ms": 80, "total_estimated_risk": 0.01, "estimated_memory_saving_mb": 10},
            {"admitted": False, "total_estimated_latency_ms": 140, "total_estimated_risk": 0.04, "estimated_memory_saving_mb": 20},
        ]

        metrics = aggregate_policy_metrics(rows, quality_budget=0.02, slo_budget_ms=100)

        self.assertEqual(metrics["num_traces"], 2)
        self.assertEqual(metrics["admission_rate"], 0.5)
        self.assertEqual(metrics["quality_budget_violation_rate"], 0.5)
        self.assertEqual(metrics["slo_violation_rate"], 0.5)
        self.assertEqual(metrics["estimated_memory_saving_mb"], 15.0)


if __name__ == "__main__":
    unittest.main()
