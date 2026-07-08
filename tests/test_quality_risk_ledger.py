import unittest

from scripts.build_quality_risk_ledger_v0 import build_ledger, proxy_drop, risk_class


class QualityRiskLedgerTests(unittest.TestCase):
    def test_proxy_drop_keeps_baseline_zero(self):
        self.assertEqual(proxy_drop("fp16_baseline", "USER_QUERY", 10, 100), 0.0)

    def test_risk_class_thresholds(self):
        self.assertEqual(risk_class(0.1), "low")
        self.assertEqual(risk_class(0.25), "medium")
        self.assertEqual(risk_class(0.5), "high")

    def test_build_ledger_emits_all_actions(self):
        rows = build_ledger(
            [
                {
                    "dataset": "RULER",
                    "task": "niah",
                    "sample_id": "0",
                    "total_prompt_tokens": 100,
                    "segments": [{"type": "USER_QUERY", "text": "q", "token_count": 10}],
                    "metadata": {"evaluation_ready": True},
                }
            ],
            max_samples_per_dataset=20,
        )
        self.assertEqual(len(rows), 6)
        self.assertEqual({r["action"] for r in rows}, {
            "fp16_baseline",
            "segment_eviction",
            "context_truncation",
            "shifted_position_proxy",
            "boundary_corruption",
            "boundary_repair_proxy",
        })
        self.assertTrue(all(r["evidence_type"] == "proxy_heuristic_v0" for r in rows))


if __name__ == "__main__":
    unittest.main()
