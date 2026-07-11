from __future__ import annotations

import unittest

from scripts.summarize_vllm_residency_validator import summarize


class ResidencySummaryTest(unittest.TestCase):
    def test_gate_uses_accuracy_and_p95_overhead(self) -> None:
        events = [{
            "event": "prefix_residency_validation", "request_id": str(i),
            "expected_hit_blocks": 10, "actual_hit_blocks": 10,
            "probe_ms": .01, "prediction_ms": .02, "validation_ms": .03,
        } for i in range(20)]
        rows, summary = summarize(events)
        self.assertEqual(len(rows), 20)
        self.assertTrue(summary[0]["phase14rc_gate_open"])


if __name__ == "__main__":
    unittest.main()
