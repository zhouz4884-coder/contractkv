import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_submission_repeats import bootstrap_ci, summarize_cell


class SubmissionRepeatTests(unittest.TestCase):
    def test_bootstrap_ci_is_deterministic_and_contains_mean(self):
        low, high = bootstrap_ci([0.30, 0.35, 0.40])
        self.assertLessEqual(low, 0.35)
        self.assertGreaterEqual(high, 0.35)
        self.assertEqual((low, high), bootstrap_ci([0.30, 0.35, 0.40]))

    def test_cell_summary_uses_future_rows_and_batch_wall(self):
        rows = [
            {"row_type": "canary", "unhidden_verifier_ms": 20},
            {"row_type": "future", "success": True, "ttft_ms": 100, "tpot_ms": 10,
             "new_prefill_tokens": 1000, "prefix_hit_tokens": 200, "batch_id": "b",
             "batch_wall_ms": 200, "certificate_issued": True, "certificate_scope_valid": True},
            {"row_type": "future", "success": True, "ttft_ms": 200, "tpot_ms": 20,
             "new_prefill_tokens": 800, "prefix_hit_tokens": 400, "batch_id": "b",
             "batch_wall_ms": 200, "certificate_issued": True, "certificate_scope_valid": True},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cell.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = summarize_cell("m", 1, "contractkv-full", path, 150)
        self.assertEqual(result["completed_requests"], 2)
        self.assertEqual(result["mean_ttft_ms"], 150)
        self.assertEqual(result["mean_new_prefill_tokens"], 900)
        self.assertEqual(result["unhidden_verifier_ms_per_request"], 10)
        self.assertEqual(result["slo_compliant_req_per_sec"], 5)
        self.assertEqual(result["certificate_scope_invalid_admitted_requests"], 0)


if __name__ == "__main__":
    unittest.main()
