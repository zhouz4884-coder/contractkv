from __future__ import annotations

import unittest

from scripts.phase15a_postprocess_diagnostics import audit_fairness, summarize_breakdowns


def row(policy: str, signature: str = "same") -> dict[str, str]:
    return {
        "_seed": "1", "concurrency": "1", "session_id": "s", "turn_id": "0",
        "policy": policy, "segment_multiset_sha256": signature, "actual_prompt_tokens": "10",
        "dataset": "D", "task": "T", "workload_family": "rag", "success": "True",
        "ttft_ms": "100", "observed_new_prefill_tokens": "5",
    }


class Phase15APostprocessTests(unittest.TestCase):
    def test_rowwise_audit_requires_all_policies_and_equal_content(self) -> None:
        rows = [row(policy) for policy in ("vllm-raw-order", "static-posc", "contractkv-caposc")]
        self.assertTrue(audit_fairness(rows)[0]["row_fair"])
        rows[-1]["segment_multiset_sha256"] = "different"
        self.assertFalse(audit_fairness(rows)[0]["row_fair"])

    def test_breakdown_marks_turn_zero_cold(self) -> None:
        output = summarize_breakdowns([row("vllm-raw-order")])
        cold = next(item for item in output if item["slice_type"] == "turn_temperature")
        self.assertEqual(cold["slice_value"], "cold")
        self.assertEqual(cold["p99_ttft_ms"], 100.0)


if __name__ == "__main__":
    unittest.main()
