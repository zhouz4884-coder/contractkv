import unittest

from scripts.analyze_llama_quality_tail import contract_class, first_divergence


class LlamaQualityTailTests(unittest.TestCase):
    def test_execution_classes_are_policy_attribution_boundaries(self):
        self.assertEqual(contract_class({
            "effective_level": "L2", "requested_level": "L2",
            "certificate_issued": True, "certificate_scope_valid": True,
        }), "admitted_compiled")
        self.assertEqual(contract_class({
            "effective_level": "L0", "requested_level": "L0",
            "certificate_issued": False,
        }), "manifest_direct_l0")
        self.assertEqual(contract_class({
            "effective_level": "L0", "requested_level": "L2",
            "certificate_issued": False,
        }), "runtime_fallback")

    def test_token_divergence_reports_first_changed_position(self):
        self.assertEqual(first_divergence([1, 2, 3], [1, 4, 3]), 1)
        self.assertEqual(first_divergence([1, 2], [1, 2, 3]), 2)
        self.assertIsNone(first_divergence([1, 2], [1, 2]))


if __name__ == "__main__":
    unittest.main()
