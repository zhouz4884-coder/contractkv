from __future__ import annotations

import unittest

from scripts.phase14slc_teacher_forced_verify import answer_logit_slice, build_prompt_ids, select_truncated_answer_and_stop_logits, stop_is_consistent, summarize


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

    def test_answer_logits_start_at_final_prompt_position(self) -> None:
        window = answer_logit_slice(12, 4)
        self.assertEqual((window.start, window.stop), (11, 15))

    def test_answer_logit_slice_rejects_empty_sequences(self) -> None:
        with self.assertRaises(ValueError):
            answer_logit_slice(0, 1)

    def test_truncated_logits_keep_exact_answer_and_stop_window(self) -> None:
        class Tensor:
            shape = (1, 4, 9)
            def __getitem__(self, item):
                return item
        answer, stop = select_truncated_answer_and_stop_logits(Tensor(), 3)
        self.assertEqual(answer, (0, slice(None, 3, None), slice(None, None, None)))
        self.assertEqual(stop, (0, 3, slice(None, None, None)))

    def test_truncated_logits_rejects_wrong_shape(self) -> None:
        class Tensor:
            shape = (1, 3, 9)
        with self.assertRaises(ValueError):
            select_truncated_answer_and_stop_logits(Tensor(), 3)

    def test_stop_certificate_accepts_eos_or_explicit_stop_token(self) -> None:
        self.assertTrue(stop_is_consistent("stop", 151645, 151645))
        self.assertTrue(stop_is_consistent("stop", 42, 151645, {42}))

    def test_stop_certificate_rejects_length_unknown_and_token_mismatch(self) -> None:
        self.assertFalse(stop_is_consistent("length", 151645, 151645))
        self.assertFalse(stop_is_consistent("", 151645, 151645))
        self.assertFalse(stop_is_consistent("stop", 7, 151645, {42}))

    def test_prompt_builder_rejects_manifest_identity_mismatch(self) -> None:
        class Tokenizer:
            def encode(self, text, add_special_tokens=False):
                return [1]
            def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True):
                return [1, 2, 3]
        sample = {
            "dataset": "RULER", "task": "niah", "sample_id": "0",
            "segments": [
                {"type": "SYS_PROMPT", "text": "sys"},
                {"type": "RAG_CHUNK", "text": "context"},
                {"type": "USER_QUERY", "text": "query"},
            ],
            "answer": "answer", "metadata": {},
        }
        job = {"topological_order": "[]", "candidate_id": "definitely-wrong"}
        with self.assertRaises(ValueError):
            build_prompt_ids(job, sample, Tokenizer(), 8192, 2600)


if __name__ == "__main__":
    unittest.main()
