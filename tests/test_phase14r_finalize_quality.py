import unittest

from scripts.phase14r_finalize_quality import finalize


class Phase14RFinalizeQualityTests(unittest.TestCase):
    def test_finalize_deduplicates_jobs_and_joins_candidate_identity(self):
        jobs = [{"job_id": "raw"}, {"job_id": "cand"}]
        base = {"sample_key": "D::T::0", "partition": "calibration", "dataset": "D", "task": "T", "sample_id": "0", "success": True, "request_id": "r"}
        raw = {**base, "job_id": "raw", "candidate_id": "raw-id", "policy": "raw-order", "score": 1.0}
        candidate = {**base, "job_id": "cand", "candidate_id": "cand-id", "policy": "posc", "score": 1.0}
        features = [{
            "sample_key": "D::T::0", "candidate_id": "cand-id", "partition": "calibration",
            "dataset": "D", "task": "T", "sample_id": "0", "qc_prelabel_fallback": False,
            "adjacency_preservation": 1, "expected_prefix_gain": 100,
        }]
        final_rows, labels, _, scores, _, combined = finalize(jobs, [[raw, candidate], [candidate]], features, 0.03, 0.5)
        self.assertEqual(len(final_rows), 2)
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["candidate_id"], "cand-id")
        self.assertEqual(len(scores), 1)
        self.assertEqual(combined[0]["duplicate_rows"], 1)


if __name__ == "__main__":
    unittest.main()
