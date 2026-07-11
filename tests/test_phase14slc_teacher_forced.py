from __future__ import annotations

import unittest

from scripts.phase14slc_teacher_forced_verify import summarize


class Phase14SLCTeacherForcedTest(unittest.TestCase):
    def test_summary_reports_unsafe_rejection_and_safe_coverage(self) -> None:
        rows = [
            {"partition": "held", "dataset": "D", "task": "T", "error_type": "none", "unsafe_quality_drop": True, "certificate_issued": False, "token_path_match_rate": .5, "minimum_logit_margin": -1, "verification_ms": 10, "expected_prefix_gain": 100},
            {"partition": "held", "dataset": "D", "task": "T", "error_type": "none", "unsafe_quality_drop": False, "certificate_issued": True, "token_path_match_rate": 1, "minimum_logit_margin": 2, "verification_ms": 20, "expected_prefix_gain": 200},
        ]
        total = next(row for row in summarize(rows) if row["partition"] == "all")
        self.assertEqual(total["unsafe_rejection_rate"], 1.0)
        self.assertEqual(total["safe_certificate_coverage"], 1.0)
        self.assertEqual(total["retained_prefix_gain_fraction"], 1.0)


if __name__ == "__main__":
    unittest.main()
