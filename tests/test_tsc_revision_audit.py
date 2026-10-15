import unittest
from unittest.mock import patch
from argparse import Namespace

from scripts.tsc_revision_offline_audit import cost_table, archived_divergence
from scripts.tsc_revision_live import certify
from scripts.tsc_revision_summarize import first_divergence
from scripts.tsc_revision_registration_audit import registration_errors, signature
from scripts.tsc_revision_guard_probe import color_answer


class HistoricalCostAuditTests(unittest.TestCase):
    def test_full_registration_includes_reference_generation_and_failed_verification(self):
        raw = [dict(row_type="future", session_id=sid, turn_id=1, success=True,
                    ttft_ms=1000, output_text="answer") for sid in ("accepted", "rejected")]
        contract = [
            dict(row_type="canary", session_id="accepted", latency_ms=600, verification_ms=100),
            dict(row_type="canary", session_id="rejected", latency_ms=800, verification_ms=200),
            dict(row_type="future", session_id="accepted", turn_id=1, success=True,
                 certificate_issued=True, ttft_ms=100, output_text="answer"),
            dict(row_type="future", session_id="rejected", turn_id=1, success=True,
                 certificate_issued=False, ttft_ms=1000, output_text="answer"),
        ]
        all_rows = next(row for row in cost_table(raw, contract, "model", 1, 0)
                        if row["request_class"] == "ALL")
        self.assertEqual(all_rows["requests"], 2)
        self.assertEqual(all_rows["full_registration_ms_per_future"], 700)
        self.assertEqual(all_rows["net_mean_ttft_ms"], 1250)
        self.assertEqual(all_rows["endpoint_only_ms"], 300)

    def test_success_filter_does_not_remove_failed_requests_from_denominator(self):
        raw = [dict(row_type="future", session_id="s", turn_id=1, success=True, ttft_ms=10)]
        contract = [dict(row_type="future", session_id="s", turn_id=1, success=False)]
        all_rows = next(row for row in cost_table(raw, contract, "model", 1, 0)
                        if row["request_class"] == "ALL")
        self.assertEqual(all_rows["requests"], 1)
        self.assertEqual(all_rows["completion_rate"], 0)

    def test_missing_token_ids_are_not_inferred_from_equal_text(self):
        raw = [dict(row_type="future", session_id="s", turn_id=1,
                    success=True, output_text="same")]
        candidate = [dict(raw[0], certificate_issued=True)]
        row = archived_divergence(raw, candidate, "model", 1, {})[0]
        self.assertTrue(row["text_identical"])
        self.assertEqual(row["token_identical"], "unavailable")

    def test_missing_full_timing_stays_unavailable(self):
        raw = [dict(row_type="future", session_id="s", turn_id=1, success=True, ttft_ms=100)]
        candidate = [dict(row_type="canary", session_id="s", verification_ms=20),
                     dict(raw[0], certificate_issued=True)]
        row = next(r for r in cost_table(raw, candidate, "m", 1, 0) if r["request_class"] == "ALL")
        self.assertFalse(row["full_registration_timing_available"])
        self.assertEqual(row["full_cost_net_mean_ttft_ms"], "unavailable")


class RevisionCertificateTests(unittest.TestCase):
    def test_guard_metric_ignores_reasoning_wrapper_not_conflicting_answer(self):
        self.assertEqual(color_answer("<think>ignored</think>\nRED."), "RED")
        self.assertNotEqual(color_answer("RED and BLUE"), "RED")

    def test_publication_boundary_excludes_unchanged_private_observation_prefix(self):
        args = Namespace(base_url="http://test/v1", model="m", timeout=1, cell_id="cell", policy_hash="p", protocol={"runtime": {"seed": 1}})
        sample = {"revision_session_id": "s"}
        case = {"segments": [
            {"segment_id": "sys", "segment_type": "SYS_PROMPT", "text": "system"},
            {"segment_id": "stable", "segment_type": "RAG_CHUNK", "text": "stable"},
            {"segment_id": "obs", "segment_type": "TOOL_OBS", "text": "private common prefix"},
        ]}
        candidate = {"topological_order": ["sys", "stable", "obs"]}
        prepared = (case, {}, candidate, [{"role": "user", "content": "raw"}],
                    [{"role": "system", "content": "system"}, {"role": "user", "content": "candidate"}])
        captured = {}
        def post(url, payload, timeout):
            captured.update(payload)
            return {"certificate_issued": True, "verify_decision": "PASS"}
        with patch("scripts.tsc_revision_live.reference_generate", return_value={"full_token_ids": [7, 8], "full_margins": [1, 1], "finish_reason": "stop", "text": "answer"}), \
             patch("scripts.tsc_revision_live.tokenize", side_effect=[[1, 2, 3, 4], [1, 2, 9], [1, 2, 3, 5]]), \
             patch("scripts.tsc_revision_live.make_turn", return_value=(None, None, None, None, [])), \
             patch("scripts.tsc_revision_live.post_json", side_effect=post):
            result = certify(args, sample, prepared, 128, "salt")
        self.assertEqual(captured["stable_prefix_end_token"], 2)
        self.assertEqual(result["stable_prefix_tokens"], 2)

    def test_length_stop_never_calls_publish_endpoint(self):
        args = Namespace(base_url="http://test/v1", model="m", timeout=1, cell_id="cell", policy_hash="p", protocol={"runtime": {"seed": 1}})
        sample = {"revision_session_id": "s"}
        prepared = ({}, {}, {}, [], [])
        with patch("scripts.tsc_revision_live.reference_generate", return_value={"full_token_ids": [7, 8], "full_margins": [1, 1], "finish_reason": "length", "text": "partial"}), \
             patch("scripts.tsc_revision_live.post_json") as endpoint:
            result = certify(args, sample, prepared, 128, "salt")
        endpoint.assert_not_called()
        self.assertFalse(result["certificate_issued"])
        self.assertEqual(result["committed_tokens"], 0)

    def test_token_prefix_match_does_not_hide_longer_output_divergence(self):
        self.assertEqual(first_divergence([1, 2], [1, 2, 3]), 2)
        self.assertEqual(first_divergence([1, 2], [1, 4]), 1)


class ManifestTrustBoundaryTests(unittest.TestCase):
    def test_valid_signature_does_not_infer_semantic_confidentiality(self):
        import hashlib
        secret = b"unit-test-key"
        text = "synthetic private canary"
        manifest = {"issuer": "operator", "template_version": "v1", "authorization_domain": "domain",
                    "segments": [{"id": "s", "text": text, "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                                  "stable": True, "visibility": "domain_shared", "publish": True}]}
        tag = signature(manifest, secret)
        self.assertEqual(registration_errors(manifest, tag, secret, "operator", "operator"), [])
        self.assertIn("client_cannot_register_shared_state", registration_errors(manifest, tag, secret, "operator", "tenant"))


if __name__ == "__main__":
    unittest.main()
