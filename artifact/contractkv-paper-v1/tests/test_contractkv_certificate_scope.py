import unittest

from scripts.contractkv_certificate_scope import (
    CertificateValidityScope,
    RequestValidityContext,
    ScopeMode,
    is_valid,
    validation_errors,
)


def certificate(**changes):
    values = {
        "model_identity": "model-a", "task_family": "retrieval",
        "layout_hash": "layout-a", "stable_prefix_hash": "prefix-a",
        "scope_mode": ScopeMode.OBSERVATION.value,
        "observation_identity": "obs-a", "observation_epoch": 7,
        "policy_hash": "policy-a", "qualification_hash": "",
    }
    values.update(changes)
    return CertificateValidityScope(**values)


def request(**changes):
    values = {
        "model_identity": "model-a", "task_family": "retrieval",
        "layout_hash": "layout-a", "stable_prefix_hash": "prefix-a",
        "observation_identity": "obs-a", "observation_epoch": 7,
        "policy_hash": "policy-a", "qualification_hash": "",
    }
    values.update(changes)
    return RequestValidityContext(**values)


class ScopedCertificateTests(unittest.TestCase):
    def test_exact_observation_scope_match_is_valid(self):
        self.assertTrue(is_valid(certificate(), request()))

    def test_observation_change_invalidates_certificate(self):
        errors = validation_errors(certificate(), request(observation_identity="obs-b", observation_epoch=8))
        self.assertIn("observation_identity_mismatch", errors)
        self.assertIn("observation_epoch_mismatch", errors)

    def test_identity_mismatches_fail_closed(self):
        for field in ("model_identity", "task_family", "layout_hash", "stable_prefix_hash", "policy_hash"):
            with self.subTest(field=field):
                errors = validation_errors(certificate(), request(**{field: "different"}))
                self.assertIn(f"{field}_mismatch", errors)

    def test_qualified_session_requires_matching_frozen_qualification(self):
        cert = certificate(
            scope_mode=ScopeMode.QUALIFIED_SESSION.value,
            qualification_hash="qualification-a",
        )
        self.assertTrue(is_valid(cert, request(
            observation_identity="future-observation", observation_epoch=99,
            qualification_hash="qualification-a")))
        self.assertFalse(is_valid(cert, request(qualification_hash="qualification-b")))

    def test_unknown_or_incomplete_scope_fails_closed(self):
        errors = validation_errors(certificate(scope_mode="forever", policy_hash=""), request())
        self.assertIn("unknown_scope_mode", errors)
        self.assertIn("missing_policy_hash", errors)


if __name__ == "__main__":
    unittest.main()
