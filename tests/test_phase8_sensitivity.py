import unittest

from scripts.compute_slo_sensitivity import recompute_slo_rows
from scripts.compute_tool_slack_sensitivity import residual_stall, sweep_tool_slack


class Phase8SensitivityTests(unittest.TestCase):
    def test_slo_sensitivity_recomputes_violation_against_new_budget(self):
        rows = [
            {
                "policy": "ContractKV-Joint",
                "dataset": "RULER",
                "arrival_time_ms": "0",
                "total_latency_ms": "100",
                "ttft_ms": "250",
                "tpot_ms": "20",
                "admitted": "True",
                "quality_budget_violation": "False",
                "copy_residual_stall_ms": "0",
                "controller_overhead_ms": "1",
            }
        ]

        out = recompute_slo_rows(rows, slo_buckets=[200, 300])

        by_slo = {row["slo_budget_ms"]: row for row in out}
        self.assertEqual(by_slo[200]["slo_violation_rate"], 1.0)
        self.assertEqual(by_slo[300]["slo_violation_rate"], 0.0)
        self.assertEqual(by_slo[300]["quality_violation_rate"], 0.0)

    def test_residual_stall_decreases_with_slack(self):
        self.assertEqual(residual_stall(copy_ms=40, slack_ms=0, mode="Slack-Window-Copy"), 40)
        self.assertEqual(residual_stall(copy_ms=40, slack_ms=50, mode="Slack-Window-Copy"), 0)
        self.assertEqual(residual_stall(copy_ms=40, slack_ms=50, mode="Critical-Path-Copy"), 40)

    def test_tool_slack_sweep_contains_joint_selected_copy(self):
        rows = sweep_tool_slack(copy_sizes_ms={128: 10.0}, slack_buckets=[0, 50])
        policies = {row["copy_policy"] for row in rows}

        self.assertEqual(policies, {"Critical-Path-Copy", "Slack-Window-Copy", "Joint-Selected-Copy"})
        joint = [row for row in rows if row["copy_policy"] == "Joint-Selected-Copy" and row["tool_slack_ms"] == 50][0]
        self.assertEqual(joint["residual_stall_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
