import unittest

from scripts.tsc_revision_diagnostics import certificate_audit, cost_decomposition, raw_controls


class RevisionDiagnosticTests(unittest.TestCase):
    def rows(self, cost=90, accepted=True):
        return [dict(row_type="canary", session_id="s", family="F", requested_level="L3",
                     certificate_issued=accepted, registration_ms=cost, verify_endpoint_ms=20,
                     committed_tokens=16 if accepted else 0, stable_prefix_tokens=17,
                     raw_finish_reason="stop", verify_decision="PASS" if accepted else "FAIL"),
                dict(row_type="future", session_id="s", turn_id=1, family="F", success=True,
                     scope_invalid_admission=False, ttft_ms=10, prompt_sha256="p", output_text="x",
                     output_token_ids=[1, 2], task_score=1)]

    def test_full_rejected_cost_is_retained(self):
        raw = self.rows(0, False); raw[1]["ttft_ms"] = 100
        candidate = self.rows(90, False)
        cells = {("e", "m", 1, 0, "raw-order"): raw, ("e", "m", 1, 0, "contractkv"): candidate}
        row = next(r for r in cost_decomposition(cells) if r["family"] == "ALL" and r["request_class"] == "ALL" and r["slack_ms"] == 0)
        self.assertEqual(row["net_mean_ttft_ms"], 100)
        self.assertEqual(row["registration_total_ms"], 90)

    def test_publication_must_stay_within_stable_boundary(self):
        rows = self.rows(); rows[0]["committed_tokens"] = 32
        audit, _, _ = certificate_audit({("e", "m", 1, 0, "contractkv"): rows})
        self.assertEqual(audit[0]["commit_past_stable_boundary"], 1)

    def test_raw_repeat_control_records_actual_prompt_mismatch(self):
        left, right = self.rows(), self.rows()
        right[1]["prompt_sha256"] = "other"
        pairs, summary = raw_controls({("e", "m", 1, 0, "raw-order"): left,
                                      ("e", "m", 2, 0, "raw-order"): right})
        self.assertFalse(pairs[0]["prompt_identical"])
        self.assertEqual(summary[0]["prompt_identity_mismatches"], 1)


if __name__ == "__main__": unittest.main()
