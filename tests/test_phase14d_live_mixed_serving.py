import unittest

from scripts.phase14d_live_mixed_serving import POLICIES, summarize


class Phase14DLiveMixedServingTests(unittest.TestCase):
    def test_policy_set_keeps_raw_static_caposc_and_qc(self):
        self.assertEqual(
            POLICIES,
            ["vllm-raw-order", "static-posc", "contractkv-caposc", "qc-caposc-v2"],
        )

    def test_summary_uses_real_batch_wall_and_observed_prefix_metrics(self):
        rows = [
            {
                "arrival_mode": "burst", "concurrency": 2, "policy": "qc-caposc-v2",
                "success": True, "quality_sanity": True, "ttft_ms": 100, "tpot_ms": 10,
                "batch_wall_time_ms": 1000, "compiler_overhead_ms": 1, "qc_fallback": False,
                "predicted_risk": 0.01, "metric_join_success": True,
                "prefix_hit_tokens": 800, "observed_new_prefill_tokens": 200,
            },
            {
                "arrival_mode": "burst", "concurrency": 2, "policy": "qc-caposc-v2",
                "success": True, "quality_sanity": True, "ttft_ms": 200, "tpot_ms": 12,
                "batch_wall_time_ms": 1000, "compiler_overhead_ms": 1, "qc_fallback": True,
                "predicted_risk": 0.04, "metric_join_success": True,
                "prefix_hit_tokens": 700, "observed_new_prefill_tokens": 300,
            },
        ]
        row = summarize(rows, [150])[0]
        self.assertEqual(row["slo_compliant_req_per_sec"], 1.0)
        self.assertEqual(row["qc_fallback_rate"], 0.5)
        self.assertEqual(row["mean_observed_new_prefill_tokens"], 250.0)


if __name__ == "__main__":
    unittest.main()
