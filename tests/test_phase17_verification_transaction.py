from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.contractkv_pstp import VerifyDecision
from scripts.contractkv_transaction import (
    PSTPPlan,
    PSTPRuntime,
    TxnState,
    lookup_runtime,
    write_runtime_registry,
)
from scripts.contractkv_verifier import (
    RawAttestation,
    VerifyThresholds,
    make_verify_report,
    split_terminal_stop_token,
)
from scripts.phase17_calibrate_thresholds import metrics


class Phase17TransactionTests(unittest.TestCase):
    def test_runtime_starts_pending_and_normalizes_completion_index(self) -> None:
        runtime = PSTPRuntime(PSTPPlan(
            txn_id="txn", stable_prefix_end_token=32, expected_stable_tokens=32,
            tokenization_glue_loss=0, glue_status="exact", stable_content_hash="stable",
            layout_hash="layout", dependency_graph_hash="dag",
        ))
        self.assertEqual(runtime.verify_decision, VerifyDecision.PENDING)
        self.assertEqual(runtime.txn_state, TxnState.OPEN)
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "runtime.json"
            write_runtime_registry(registry, {"phase17-candidate-a": runtime})
            self.assertEqual(lookup_runtime("cmpl-phase17-candidate-a-0", registry).plan, runtime.plan)
            self.assertIsNone(lookup_runtime("cmpl-unrelated-0", registry))

    def test_terminal_stop_is_teacher_forced_exactly_once(self) -> None:
        answer, margins, terminal = split_terminal_stop_token(
            [11, 12, 151645], [2.0, 1.5, 3.0], "stop")
        self.assertEqual(answer, [11, 12])
        self.assertEqual(margins, [2.0, 1.5])
        self.assertEqual(terminal, 151645)

    def test_missing_candidate_stop_is_fail_not_metric_erasure(self) -> None:
        raw = RawAttestation(
            token_ids=(11, 12), token_margins=(2.0, 1.0), finish_reason="stop",
            stop_token_ids=(151645,), model_hash="m", tokenizer_hash="t", chat_template_hash="c",
        )
        report = make_verify_report(
            raw, [11, 12], [1.5, .8], [1, 1], None, VerifyThresholds(0, 0, 1e9))
        self.assertEqual(report.decision, VerifyDecision.FAIL)
        self.assertEqual(report.failure_reason, "stop_mismatch")
        self.assertEqual(report.answer_tokens, 2)
        self.assertAlmostEqual(report.raw_margin_q05, 1.05)

    def test_calibration_metrics_respect_intrinsic_stop_gate(self) -> None:
        base = {
            "error_type": "none", "raw_finish_reason": "stop", "answer_tokens": "2",
            "top1_matches": "2", "raw_margin_q05": "1", "candidate_margin_q05": "1",
            "degradation_q95": "0", "expected_prefix_gain": "100",
        }
        rows = [
            {**base, "unsafe_quality_drop": "false", "stop_consistent": "true"},
            {**base, "unsafe_quality_drop": "true", "stop_consistent": "false"},
        ]
        result = metrics(rows, (-1e9, -1e9, 1e9))
        self.assertEqual(result["safe_certified"], 1)
        self.assertEqual(result["unsafe_certified"], 0)


if __name__ == "__main__":
    unittest.main()
