import json
import unittest
from pathlib import Path

from scripts.install_vllm_v1_ephemeral_shadow_hook import clean
from scripts.phase16r_verifier_live import extract_raw_tokens_and_margins


class Phase21CertificateScopeMistralTests(unittest.TestCase):
    def test_same_decoded_token_competitor_is_not_discarded(self):
        response = {
            "choices": [{
                "token_ids": [101, 2],
                "finish_reason": "stop",
                "logprobs": {"content": [
                    {"token": "Cl", "logprob": -0.01,
                     "top_logprobs": [
                         {"token": "Cl", "logprob": -0.01},
                         {"token": "Cl", "logprob": -12.0},
                     ]},
                    {"token": "</s>", "logprob": -0.02,
                     "top_logprobs": [
                         {"token": "</s>", "logprob": -0.02},
                         {"token": ".", "logprob": -7.0},
                     ]},
                ]},
            }]
        }
        token_ids, margins, finish_reason, source = extract_raw_tokens_and_margins(response)
        self.assertEqual(token_ids, [101, 2])
        self.assertAlmostEqual(margins[0], 11.99)
        self.assertEqual(finish_reason, "stop")
        self.assertEqual(source, "choice.token_ids")

    def test_ephemeral_clean_removes_all_grant_cap_copies(self):
        cap = (
            "            if _contractkv_shadow_chunk is not None:\n"
            "                num_new_tokens = min(num_new_tokens, "
            "_contractkv_shadow_granted_tokens(request))\n"
        )
        cleaned = clean("before\n" + cap * 4 + "after\n")
        self.assertEqual(cleaned, "before\nafter\n")

    def test_llama_fresh_audit_does_not_pass_a_bad_future_turn(self):
        root = Path(__file__).resolve().parents[1]
        result = json.loads((root / "results/cross_model/phase21a_llama_future_turn_summary_v0.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(result["fresh_pass_with_quality_drop"], 0)
        self.assertEqual(result["conclusion"], "stale_certificate_scope")

    def test_mistral_sealed_gate_and_protocol_pass(self):
        root = Path(__file__).resolve().parents[1]
        gate = json.loads((root / "results/mistral/gate_v0.json").read_text(encoding="utf-8"))
        protocol = json.loads((root / "results/mistral/protocol_audit_summary_v0.json")
                              .read_text(encoding="utf-8"))
        split = json.loads((root / "results/mistral/mistral_split_commitment_v0.json")
                           .read_text(encoding="utf-8"))
        self.assertTrue(gate["gate_pass"])
        self.assertTrue(all(gate["gates"].values()))
        self.assertEqual(protocol["protocol_bug_count"], 0)
        self.assertEqual(split["sample_overlap"], 0)
        self.assertEqual(split["source_group_overlap"], 0)


if __name__ == "__main__":
    unittest.main()
