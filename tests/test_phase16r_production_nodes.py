from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.contractkv_pstp import (
    PSTPSpec,
    VerifyDecision,
    aligned_commit_tokens,
    build_pstp_spec,
    lookup_pstp_spec,
    write_registry,
)
from scripts.contractkv_quiescence import collision_backoff_ms, decide_shadow_admission
from scripts.contractkv_verifier import (
    RawAttestation,
    VerificationIncomplete,
    VerifyThresholds,
    make_verify_report,
    target_rank_and_margin,
)


class PSTPTests(unittest.TestCase):
    def test_lcp_and_full_block_alignment(self) -> None:
        spec = build_pstp_spec(
            "txn", [1, 2, 3, 4, 5], [1, 2, 3, 9], VerifyDecision.PASS, 2,
        )
        self.assertEqual(spec.stable_prefix_end_token, 3)
        self.assertEqual(spec.tokenization_glue_loss, 2)
        self.assertEqual(aligned_commit_tokens(3, 9, 2), 2)

    def test_full_block_glue_loss_fails_closed(self) -> None:
        spec = build_pstp_spec(
            "txn", list(range(20)), [0, 1, 2], VerifyDecision.PASS, 16,
        )
        self.assertEqual(spec.verify_decision, VerifyDecision.INCOMPLETE)
        self.assertEqual(spec.glue_status, "severe_drift")

    def test_registry_uses_explicit_spec_not_request_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            spec = PSTPSpec("txn", 32, VerifyDecision.FAIL)
            write_registry(path, {"plain-id": spec})
            self.assertEqual(lookup_pstp_spec("chatcmpl-plain-id", path), spec)
            self.assertIsNone(lookup_pstp_spec("plain-id-commit", path))


class VerifierTests(unittest.TestCase):
    def test_strongest_competitor_and_missing_target(self) -> None:
        entry = {
            "11": {"logprob": -0.2, "rank": 1},
            "12": {"logprob": -0.8, "rank": 2},
            "13": {"logprob": -1.2, "rank": 3},
        }
        rank, margin = target_rank_and_margin(entry, 11)
        self.assertEqual(rank, 1)
        self.assertAlmostEqual(margin, 0.6)
        with self.assertRaises(VerificationIncomplete):
            target_rank_and_margin(entry, 99)

    def test_robustness_reserve_and_fail_closed_length(self) -> None:
        raw = RawAttestation(
            token_ids=(1, 2), token_margins=(2.0, 1.0), finish_reason="stop",
            stop_token_ids=(9,), model_hash="m", tokenizer_hash="t", chat_template_hash="c",
        )
        report = make_verify_report(raw, [1, 2], [1.5, .8], [1, 1], 9, VerifyThresholds(0, 0, 1))
        self.assertEqual(report.decision, VerifyDecision.PASS)
        self.assertGreaterEqual(report.robustness_reserve, 0)
        length = RawAttestation(**{**raw.__dict__, "finish_reason": "length"})
        self.assertEqual(
            make_verify_report(length, [1, 2], [1.5, .8], [1, 1], 9, VerifyThresholds()).decision,
            VerifyDecision.INCOMPLETE,
        )


class QuiescenceTests(unittest.TestCase):
    def test_priority_and_hysteresis_reasons(self) -> None:
        common = dict(
            foreground_running=False, in_collision_backoff=False,
            idle_age_ms=5, idle_grace_ms=10, free_blocks=100,
            block_watermark=20, collision_count=0, current_backoff_ms=0,
            chunk_tokens=32,
        )
        waiting = decide_shadow_admission(foreground_waiting=True, **common)
        self.assertEqual(waiting.reason, "foreground_waiting")
        idle = decide_shadow_admission(foreground_waiting=False, **common)
        self.assertEqual(idle.reason, "idle_hysteresis")
        self.assertFalse(idle.admitted)

    def test_backoff_caps_at_eight_ms(self) -> None:
        self.assertEqual(collision_backoff_ms(1), 1.0)
        self.assertEqual(collision_backoff_ms(5), 8.0)


if __name__ == "__main__":
    unittest.main()
