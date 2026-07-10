from __future__ import annotations

import unittest

from scripts.join_phase14b_prefix_metrics import build_join, summarize


class Phase14BPrefixJoinTest(unittest.TestCase):
    def test_joins_server_request_id_and_summarizes_observed_values(self) -> None:
        joined = build_join(
            [{"request_id": "chatcmpl-a", "policy": "caposc", "real_ttft_ms": 20,
              "estimated_lcp_tokens": 64, "estimated_new_prefill_tokens": 36}],
            [{"request_id": "chatcmpl-a", "prompt_tokens": "100", "prefix_hit_tokens": "64",
              "new_prefill_tokens": "36", "reused_physical_blocks": "4", "newly_allocated_blocks": "3",
              "metric_availability": "all_scheduler_observable"}],
        )
        self.assertTrue(joined[0]["join_success"])
        summary = summarize(joined)[0]
        self.assertEqual(summary["joined_requests"], 1)
        self.assertEqual(summary["mean_observed_prefix_hit_tokens"], 64.0)
        self.assertEqual(summary["mean_observed_new_prefill_tokens"], 36.0)

    def test_reports_missing_request_as_unjoined(self) -> None:
        joined = build_join([{"request_id": "missing", "policy": "raw-order"}], [])
        self.assertFalse(joined[0]["join_success"])


if __name__ == "__main__":
    unittest.main()
