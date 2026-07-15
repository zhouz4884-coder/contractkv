import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_layout_only_decomposition import coverage
from scripts.summarize_submission_supplement import (
    add_exposure,
    invariance_row,
    sample_metrics,
)


class SubmissionSupplementTests(unittest.TestCase):
    def test_repeat_invariance(self):
        row = invariance_row("m", "s", [0.5, 0.5, 0.5], "note", 100, 50)
        self.assertTrue(row["exact_repeat_invariant"])
        self.assertEqual(row["repeat_range"], 0.0)
        self.assertEqual(row["prefill_work_speedup"], 2.0)

    def test_batch_exposure_is_not_double_counted(self):
        rows = [
            {"batch_id": "b", "batch_wall_ms": 100.0},
            {"batch_id": "b", "batch_wall_ms": 100.0},
        ]
        add_exposure(rows)
        self.assertEqual(sum(row["_exposure_ms"] for row in rows), 100.0)

    def test_conservative_verifier_accounting(self):
        raw = {"s": [{"ttft_ms": 100.0, "_exposure_ms": 100.0}]}
        contract = {"s": [{"ttft_ms": 50.0, "_exposure_ms": 100.0, "certificate_issued": True}]}
        result = sample_metrics(raw, contract, {"s": 10.0}, ["s"], 1000)
        self.assertAlmostEqual(result["net_mean_ttft_reduction"], 0.4)

    def test_layout_coverage_uses_frozen_qualification(self):
        rows = [
            {"row_type": "future", "session_id": "safe", "offline_qualified": True},
            {"row_type": "future", "session_id": "fallback", "offline_qualified": False},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            self.assertEqual(coverage(path, "raw-order"), 0.0)
            self.assertEqual(coverage(path, "offline-frozen-safe-compiled"), 0.5)


if __name__ == "__main__":
    unittest.main()
