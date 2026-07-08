import unittest

from scripts.build_phase5_inputs import (
    ACTIONS,
    COST_FIELDS,
    RISK_SUMMARY_FIELDS,
    build_cost_rows,
    build_risk_summary,
)


class Phase5InputTests(unittest.TestCase):
    def test_risk_summary_aggregates_quality_drop(self):
        rows = [
            {
                "dataset": "RULER",
                "task": "niah",
                "segment_type": "USER_QUERY",
                "action": "segment_eviction",
                "quality_drop": "0.05",
            },
            {
                "dataset": "RULER",
                "task": "niah",
                "segment_type": "USER_QUERY",
                "action": "segment_eviction",
                "quality_drop": "0.01",
            },
        ]

        summary = build_risk_summary(rows)

        self.assertEqual(list(summary[0].keys()), RISK_SUMMARY_FIELDS)
        self.assertEqual(summary[0]["num_records"], 2)
        self.assertAlmostEqual(summary[0]["mean_quality_drop"], 0.03)
        self.assertEqual(summary[0]["risk_level"], "medium")
        self.assertFalse(summary[0]["allowed_under_1pct"])
        self.assertFalse(summary[0]["allowed_under_2pct"])

    def test_cost_table_contains_all_controller_actions(self):
        segment_types = ["SYS_PROMPT", "RAG_CHUNK"]

        rows = build_cost_rows(segment_types, h2d_gbps=13.2, d2h_gbps=13.1, interference_ms=5.3)

        self.assertEqual(set(row["action"] for row in rows), set(ACTIONS))
        self.assertTrue(all(list(row.keys()) == COST_FIELDS for row in rows))
        self.assertTrue(all(row["source"] for row in rows))
        self.assertTrue(any(row["estimated_transfer_mb"] > 0 for row in rows))


if __name__ == "__main__":
    unittest.main()
