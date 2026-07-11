from __future__ import annotations

import unittest

from scripts.phase14slc_epoch_transfer import summarize


class Phase14SLCEpochTransferTest(unittest.TestCase):
    def test_summary_keeps_zero_failure_wilson_bound_explicit(self) -> None:
        rows = []
        for turn in range(6):
            rows.append({
                "tool_slack_ms": 500.0, "trajectory_id": "session-a",
                "turn_id": turn, "certificate_issued": True,
                "exact_output_match": True, "shadow_hidden_by_slack": True,
                "shadow_runtime_ms": 350.0,
            })
        row = next(item for item in summarize(rows, [5]) if item["horizon_turns"] == 5)
        self.assertEqual(row["future_pairs"], 5)
        self.assertEqual(row["future_mismatch_rate"], 0.0)
        self.assertGreater(row["future_match_wilson95_upper"], 0.0)


if __name__ == "__main__":
    unittest.main()
