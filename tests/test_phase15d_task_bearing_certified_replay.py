from __future__ import annotations

import unittest

from scripts.phase15d_task_bearing_certified_replay import apply_revoke_policy, output_contract, wilson_upper


class Phase15DTaskBearingTests(unittest.TestCase):
    def test_ruler_contract_requires_answer_on_both_paths(self) -> None:
        self.assertTrue(output_contract("RULER", "niah", "42", "answer 42", "42")[0])
        self.assertFalse(output_contract("RULER", "niah", "42", "41", "42")[0])

    def test_code_contract_uses_ast_equivalence(self) -> None:
        matched, kind = output_contract("RepoBench", "python", "x = 1", "x=1", "")
        self.assertTrue(matched)
        self.assertEqual(kind, "python_ast_equivalence")

    def test_open_document_contract_is_strict(self) -> None:
        self.assertTrue(output_contract("LongBench", "qasper", "The Answer", "the  answer", "")[0])
        self.assertFalse(output_contract("LongBench", "qasper", "a", "b", "")[0])

    def test_zero_failure_wilson_upper_for_300_pairs(self) -> None:
        self.assertLess(wilson_upper(0, 300), 0.013)

    def test_future_mismatch_revokes_subsequent_candidate_use(self) -> None:
        rows = [
            {"session_id": "s", "turn_id": 0, "certificate_issued": True, "output_contract_match": True},
            {"session_id": "s", "turn_id": 1, "certificate_issued": True, "output_contract_match": False},
            {"session_id": "s", "turn_id": 2, "certificate_issued": True, "output_contract_match": True},
        ]
        apply_revoke_policy(rows)
        self.assertEqual([row["deployed_policy"] for row in rows], ["contractkv-caposc", "contractkv-caposc", "raw-order"])
        self.assertTrue(rows[1]["certificate_revoked"])


if __name__ == "__main__":
    unittest.main()
