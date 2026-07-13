import json
import tempfile
import unittest
from pathlib import Path

from scripts.contractkv_task_contracts import evaluate_contract
from scripts.phase20a_official_quality import qa_f1, standard_score
from scripts.phase20b_llama_rejection_audit import first_divergent, hash_ids


class Phase20SubmissionClosureTests(unittest.TestCase):
    def test_online_contracts_never_need_ground_truth(self):
        ruler = evaluate_contract("RULER", "niah_single_1", "Answer: 42", "42")
        self.assertTrue(ruler.supported)
        self.assertTrue(ruler.equivalent)
        qa = evaluate_contract("LongBench", "hotpotqa", "Paris", "Paris.")
        self.assertTrue(qa.equivalent)
        echoed = evaluate_contract(
            "LongBench", "hotpotqa", "Kumbakonam",
            "[Return the shortest answer.]\n\nKumbakonam")
        self.assertTrue(echoed.equivalent)
        lexical_only = evaluate_contract(
            "LongBench", "qasper",
            "Our system achieved an MRR score of 0.6103 in the test batch.",
            "Our system achieved a highest MRR score of 0.6103 in the test batch.")
        self.assertFalse(lexical_only.equivalent)
        changed_number = evaluate_contract(
            "LongBench", "qasper", "MRR was 0.6103.", "MRR was 0.7103.")
        self.assertFalse(changed_number.equivalent)

    def test_repobench_contract_is_ast_or_conservative_exact(self):
        equivalent = evaluate_contract("RepoBench", "python_v1.1", "x=1", "x = 1")
        self.assertTrue(equivalent.equivalent)
        fragment = evaluate_contract("RepoBench", "python_v1.1", "return x +", "return x+")
        self.assertFalse(fragment.equivalent)

    def test_standard_metrics_match_expected_task_families(self):
        score, metric, _ = standard_score("RULER", "niah_single_1", "value 7391", "7391")
        self.assertEqual((score, metric), (1.0, "string_match_part"))
        self.assertAlmostEqual(qa_f1("The answer is Paris", "Paris"), 0.5)
        score, metric, _ = standard_score("RepoBench", "python_v1.1", "x = 1", "x = 1")
        self.assertEqual((score, metric), (1.0, "edit_similarity"))

    def test_rejection_audit_helpers_are_token_exact(self):
        self.assertEqual(first_divergent([1, 2, 3], [1, 9, 3]), 1)
        self.assertEqual(first_divergent([1, 2], [1, 2]), -1)
        self.assertNotEqual(hash_ids([1, 2]), hash_ids([2, 1]))

    def test_phase20_gate_thresholds_are_frozen_in_attachment_plan(self):
        script = (Path(__file__).resolve().parents[1] / "scripts/phase20a_slack_sensitivity.py").read_text(encoding="utf-8")
        self.assertIn(">= .30", script)
        self.assertIn('default="0,500,1000,1500,2000,3000"', script)

    def test_frozen_heldout_gate_and_causality_remain_negative(self):
        root = Path(__file__).resolve().parents[1]
        gate = json.loads(
            (root / "results/cross_model/phase20d_one_shot_gate_v0.json").read_text(
                encoding="utf-8"))
        audit = json.loads(
            (root / "results/cross_model/phase20d_quality_causality_summary_v0.json").read_text(
                encoding="utf-8"))
        self.assertFalse(gate["gate_pass"])
        self.assertTrue(gate["stop_experiments_after_phase20"])
        self.assertFalse(gate["gates"]["unsafe_certified_zero"])
        self.assertFalse(gate["gates"]["promotion_commit_observed"])
        self.assertEqual(audit["affected_session_count"], 3)
        self.assertEqual(
            audit["cause_rows"]["reproducible_future_turn_layout_sensitivity"], 11)
        self.assertTrue(audit["tier1_two_tier_certificate_set_equal"])


if __name__ == "__main__":
    unittest.main()
