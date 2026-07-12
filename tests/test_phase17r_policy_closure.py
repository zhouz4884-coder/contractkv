from __future__ import annotations

import unittest

from scripts.contractkv_frozen_policy import FrozenVerifierPolicy, RuntimeIdentity, policy_hash, validate_policy_runtime
from scripts.phase17r_incomplete_taxonomy import IncompleteClass, classify_incomplete


class Phase17RPolicyTests(unittest.TestCase):
    def policy(self) -> FrozenVerifierPolicy:
        return FrozenVerifierPolicy(
            schema_version="v", policy_version="p", attestation_mode="a", model_id="m", model_revision="r",
            tokenizer_hash="t", chat_template_hash="c", vllm_version="0.10.2", terminal_protocol_version="e",
            verifier_code_commit="commit", tau_raw=-1e9, tau_abs=-1e9, tau_drop=1e9,
            calibration_manifest_hash="cm", calibration_split_hash="cs", decode_config_hash="d",
        )

    def test_policy_hash_is_deterministic_and_runtime_mismatch_is_explicit(self) -> None:
        policy = self.policy()
        self.assertEqual(policy_hash(policy), policy_hash(policy))
        runtime = RuntimeIdentity("m", "r", "t", "c", "0.10.2", "e", "d")
        self.assertEqual(validate_policy_runtime(policy, runtime), [])
        changed = RuntimeIdentity("m", "different", "t", "c", "0.10.2", "e", "d")
        self.assertEqual(len(validate_policy_runtime(policy, changed)), 1)

    def test_incomplete_taxonomy_keeps_protocol_and_workload_paths_separate(self) -> None:
        self.assertEqual(classify_incomplete("VerificationIncomplete", "target token 1 absent", ""), IncompleteClass.TARGET_TOKEN_ABSENT)
        self.assertEqual(classify_incomplete("raw_attestation_missing", "", ""), IncompleteClass.RAW_ATTESTATION_MISSING)
        self.assertEqual(classify_incomplete("VerificationIncomplete", "raw finish_reason=length", ""), IncompleteClass.FINISH_REASON_LENGTH)


if __name__ == "__main__":
    unittest.main()
