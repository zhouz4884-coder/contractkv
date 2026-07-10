import unittest

from scripts.phase13c_quality_analysis import analyze


class Phase13CQualityAnalysisTests(unittest.TestCase):
    def test_signed_delta_preserves_positive_wins(self):
        rows = [
            {"dataset": "LongBench", "task": "hotpotqa", "sample_id": "0", "policy": "raw-order", "score": 0.1, "success": True, "violated_edges": "[]"},
            {"dataset": "LongBench", "task": "hotpotqa", "sample_id": "0", "policy": "canonical-all", "score": 0.3, "success": True, "violated_edges": "[]"},
            {"dataset": "LongBench", "task": "hotpotqa", "sample_id": "0", "policy": "static-posc", "score": 0.1, "success": True, "violated_edges": "[]"},
            {"dataset": "LongBench", "task": "hotpotqa", "sample_id": "0", "policy": "contractkv-caposc", "score": 0.0, "success": True, "violated_edges": "[]"},
        ]
        _, summary = analyze(rows)
        canonical = next(row for row in summary if row["policy"] == "canonical-all")
        caposc = next(row for row in summary if row["policy"] == "contractkv-caposc")
        self.assertEqual(canonical["mean_signed_quality_delta"], 0.2)
        self.assertEqual(canonical["paired_wins"], 1)
        self.assertEqual(caposc["mean_signed_quality_delta"], -0.1)
        self.assertEqual(caposc["paired_losses"], 1)

    def test_repobench_code_metrics_are_present(self):
        rows = [
            {"dataset": "RepoBench", "task": "python", "sample_id": "0", "policy": "raw-order", "score": 1.0, "success": True, "violated_edges": "[]", "output_text": "x = 1", "answer": "x = 1"},
            {"dataset": "RepoBench", "task": "python", "sample_id": "0", "policy": "canonical-all", "score": 1.0, "success": True, "violated_edges": "[[\"a\",\"b\"]]", "output_text": "x = 2", "answer": "x = 1"},
        ]
        enriched, _ = analyze(rows)
        self.assertTrue(any(row["python_parse_success"] is True for row in enriched))
        self.assertTrue(any(float(row["edit_similarity"]) < 1.0 for row in enriched if row["policy"] == "canonical-all"))


if __name__ == "__main__":
    unittest.main()
