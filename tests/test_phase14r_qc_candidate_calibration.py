import unittest

from scripts.phase14r_qc_candidate_calibration import calibrate


class Phase14RQCCandidateCalibrationTests(unittest.TestCase):
    def test_calibration_outputs_scores_summary_and_model(self):
        features = [
            {
                "sample_key": "LongBench::hotpotqa::0",
                "candidate_id": "c0",
                "partition": "calibration",
                "dataset": "LongBench",
                "task": "hotpotqa",
                "sample_id": "0",
                "violated_edge_count": "0",
                "adjacency_preservation": "1.0",
                "relative_order_edit_distance": "0",
                "moved_segment_count": "0",
                "ordered_discourse_signal": "false",
                "low_adjacency_signal": "false",
                "cross_reference_signal": "0",
                "expected_prefix_gain": "100",
                "context_segment_tokens": "1000",
            },
            {
                "sample_key": "LongBench::qasper::1",
                "candidate_id": "c1",
                "partition": "calibration",
                "dataset": "LongBench",
                "task": "qasper",
                "sample_id": "1",
                "violated_edge_count": "1",
                "adjacency_preservation": "0.2",
                "relative_order_edit_distance": "3",
                "moved_segment_count": "3",
                "ordered_discourse_signal": "true",
                "low_adjacency_signal": "true",
                "cross_reference_signal": "2",
                "expected_prefix_gain": "800",
                "context_segment_tokens": "2000",
            },
        ]
        labels = [
            {"sample_key": "LongBench::hotpotqa::0", "candidate_id": "c0", "partition": "calibration", "unsafe_quality_drop": False, "quality_drop_vs_raw": "0.0"},
            {"sample_key": "LongBench::qasper::1", "candidate_id": "c1", "partition": "calibration", "unsafe_quality_drop": True, "quality_drop_vs_raw": "0.1"},
        ]
        scores, summary, model = calibrate(features, labels, target_false_safe=0.02)
        self.assertEqual(len(scores), 2)
        self.assertIn("threshold", model)
        self.assertEqual(model["threshold_objective"], "maximize_safe_expected_prefix_gain_subject_to_wilson95_upper")
        self.assertTrue(summary)
        self.assertIn("false_safe_wilson95_upper", summary[0])


if __name__ == "__main__":
    unittest.main()
