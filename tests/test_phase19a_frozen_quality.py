import csv
import unittest
from pathlib import Path

from scripts.phase19a_freeze_quality_summary import summarize
from scripts.phase19a_rebuild_quality_pool import OUTPUT_FIELDS


ROOT = Path(__file__).resolve().parents[1]


class Phase19AFrozenQualityTests(unittest.TestCase):
    def test_required_provenance_fields_are_frozen(self):
        required = {
            "sample_key", "candidate_id", "partition", "model_revision",
            "tokenizer_hash", "chat_template_hash", "candidate_builder_hash",
            "evaluator_hash", "policy_hash", "raw_prompt_hash",
            "candidate_prompt_hash", "raw_answer_ids_hash",
            "candidate_answer_ids_hash", "raw_stop", "candidate_stop",
            "raw_score", "candidate_score", "quality_drop",
            "fresh_unsafe_label", "verifier_decision",
            "certificate_eligible", "expected_prefix_gain",
        }
        self.assertTrue(required.issubset(OUTPUT_FIELDS))

    def test_summary_separates_incomplete_opportunity_loss(self):
        rows = [
            {"protocol_status": "COMPLETE", "fresh_unsafe_label": "False",
             "certificate_eligible": "True", "expected_prefix_gain": "100",
             "quality_drop": "0.01"},
            {"protocol_status": "COMPLETE", "fresh_unsafe_label": "True",
             "certificate_eligible": "False", "expected_prefix_gain": "80",
             "quality_drop": "0.2"},
            {"protocol_status": "INCOMPLETE", "fresh_unsafe_label": "",
             "certificate_eligible": "False", "expected_prefix_gain": "50",
             "quality_drop": ""},
        ]
        result = summarize("all", rows)
        self.assertEqual(result["safe_candidates"], 1)
        self.assertEqual(result["unsafe_candidates"], 1)
        self.assertEqual(result["unsafe_certified"], 0)
        self.assertEqual(result["retained_prefix_gain_tokens"], 100)
        self.assertEqual(result["incomplete_opportunity_loss_tokens"], 50)

    def test_phase18_gate_columns_are_explicit(self):
        path = ROOT / "results/hard_systems/phase18_c3_c4_source_summary_v0.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = {row["cell"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["C3"]["lifecycle_gate_pass"], "True")
        self.assertEqual(rows["C3"]["pooled_interference_gate_pass"], "True")
        self.assertEqual(rows["C3"]["median_seed_interference_gate_pass"], "False")
        self.assertEqual(rows["C4"]["median_seed_interference_gate_pass"], "True")
        self.assertEqual(rows["C4"]["all_seed_guard_pass"], "False")


if __name__ == "__main__":
    unittest.main()
