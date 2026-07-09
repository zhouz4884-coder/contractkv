import unittest

from scripts.phase12e_multiturn_trajectory_builder import build_multiturn_trajectories
from scripts.phase13a_compiler_overhead import (
    OVERHEAD_RAW_FIELDS,
    OVERHEAD_SUMMARY_FIELDS,
    REBASE_SUMMARY_FIELDS,
    measure_compile_once,
    summarize_overhead_rows,
    summarize_rebase_rows,
)


class Phase13ACompilerOverheadTests(unittest.TestCase):
    def test_overhead_schema_contains_compile_ledger_candidate_and_rebase_fields(self):
        required_raw = {
            "iteration",
            "trajectory_id",
            "turn_id",
            "compile_ms",
            "ledger_lookup_ms",
            "candidate_eval_ms",
            "candidate_count",
            "selected_policy",
            "rebase_triggered",
            "rebase_hidden_by_slack",
            "rebase_overhead_ms",
        }

        self.assertTrue(required_raw.issubset(set(OVERHEAD_RAW_FIELDS)))
        self.assertIn("compile_ms_p95", OVERHEAD_SUMMARY_FIELDS)
        self.assertIn("rebase_selected_fraction", REBASE_SUMMARY_FIELDS)

    def test_measure_compile_once_returns_candidate_count_and_timing(self):
        case = build_multiturn_trajectories(trajectories_per_type=1, turns=1)[0]
        row, ledger = measure_compile_once(case, iteration=0, ledger=None)

        self.assertGreaterEqual(row["compile_ms"], 0.0)
        self.assertGreaterEqual(row["ledger_lookup_ms"], 0.0)
        self.assertGreaterEqual(row["candidate_eval_ms"], 0.0)
        self.assertEqual(row["candidate_count"], 5)
        self.assertTrue(ledger.entries)

    def test_overhead_summary_reports_mean_and_p95(self):
        rows = [
            {"compile_ms": 1.0, "ledger_lookup_ms": 0.2, "candidate_eval_ms": 0.6, "candidate_count": 5},
            {"compile_ms": 3.0, "ledger_lookup_ms": 0.4, "candidate_eval_ms": 1.0, "candidate_count": 5},
        ]

        summary = summarize_overhead_rows(rows)

        self.assertEqual(summary[0]["compile_ms_mean"], 2.0)
        self.assertGreaterEqual(summary[0]["compile_ms_p95"], 2.0)
        self.assertEqual(summary[0]["candidate_count_mean"], 5.0)

    def test_rebase_summary_reports_trigger_and_hidden_fraction(self):
        rows = [
            {"rebase_triggered": True, "rebase_hidden_by_slack": True, "rebase_overhead_ms": 80.0, "selected_policy": "posc"},
            {"rebase_triggered": False, "rebase_hidden_by_slack": False, "rebase_overhead_ms": 0.0, "selected_policy": "cache-aware-posc"},
        ]

        summary = summarize_rebase_rows(rows)

        self.assertEqual(summary[0]["rebase_triggered_count"], 1)
        self.assertEqual(summary[0]["rebase_hidden_by_slack_count"], 1)
        self.assertEqual(summary[0]["rebase_selected_fraction"], 0.5)


if __name__ == "__main__":
    unittest.main()
