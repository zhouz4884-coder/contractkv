import unittest

from scripts.phase12f_real_vllm_caposc_replay import (
    REAL_RAW_FIELDS,
    REAL_SUMMARY_FIELDS,
    build_oracle_rows,
    compute_correlation_rows,
    score_real_output,
    summarize_real_replay_rows,
)


class Phase12FRealVllmCaposcTests(unittest.TestCase):
    def test_real_raw_schema_has_timing_lcp_quality_and_oracle_fields(self):
        required = {
            "trajectory_id",
            "turn_id",
            "policy",
            "selected_policy",
            "success",
            "quality_sanity",
            "real_ttft_ms",
            "real_tpot_ms",
            "real_latency_ms",
            "estimated_lcp_tokens",
            "estimated_new_prefill_tokens",
            "violated_edges",
            "oracle_source_policy",
        }

        self.assertTrue(required.issubset(set(REAL_RAW_FIELDS)))
        self.assertIn("mean_real_ttft_ms", REAL_SUMMARY_FIELDS)

    def test_score_real_output_requires_marker_and_no_unsafe_answer(self):
        ok, score = score_real_output("The answer is CAPOSC_CODE_0.", "CAPOSC_CODE_0", "ORDER_ERROR", [])
        bad, bad_score = score_real_output("ORDER_ERROR", "CAPOSC_CODE_0", "ORDER_ERROR", [])
        violated, violated_score = score_real_output("CAPOSC_CODE_0", "CAPOSC_CODE_0", "ORDER_ERROR", [["a", "b"]])

        self.assertTrue(ok)
        self.assertEqual(score, 1.0)
        self.assertFalse(bad)
        self.assertEqual(bad_score, 0.0)
        self.assertFalse(violated)
        self.assertEqual(violated_score, 0.0)

    def test_oracle_rows_select_lowest_quality_safe_ttft_per_turn(self):
        rows = [
            {"trajectory_id": "t", "turn_id": 0, "case_type": "code", "policy": "boolean-guarded", "success": True, "quality_sanity": True, "quality_score": 1.0, "real_ttft_ms": 120, "real_tpot_ms": 5, "real_latency_ms": 200, "estimated_lcp_tokens": 10, "estimated_new_prefill_tokens": 90},
            {"trajectory_id": "t", "turn_id": 0, "case_type": "code", "policy": "posc", "success": True, "quality_sanity": False, "quality_score": 0.0, "real_ttft_ms": 40, "real_tpot_ms": 5, "real_latency_ms": 200, "estimated_lcp_tokens": 80, "estimated_new_prefill_tokens": 20},
            {"trajectory_id": "t", "turn_id": 0, "case_type": "code", "policy": "cache-aware-posc", "success": True, "quality_sanity": True, "quality_score": 1.0, "real_ttft_ms": 70, "real_tpot_ms": 5, "real_latency_ms": 200, "estimated_lcp_tokens": 70, "estimated_new_prefill_tokens": 30},
        ]

        oracle = build_oracle_rows(rows)

        self.assertEqual(len(oracle), 1)
        self.assertEqual(oracle[0]["policy"], "oracle-best-layout")
        self.assertEqual(oracle[0]["oracle_source_policy"], "cache-aware-posc")
        self.assertEqual(oracle[0]["real_ttft_ms"], 70)

    def test_correlation_reports_lcp_negative_and_new_prefill_positive(self):
        rows = [
            {"policy": "cache-aware-posc", "success": True, "estimated_lcp_tokens": 300, "estimated_new_prefill_tokens": 100, "real_ttft_ms": 50},
            {"policy": "cache-aware-posc", "success": True, "estimated_lcp_tokens": 200, "estimated_new_prefill_tokens": 200, "real_ttft_ms": 80},
            {"policy": "cache-aware-posc", "success": True, "estimated_lcp_tokens": 100, "estimated_new_prefill_tokens": 300, "real_ttft_ms": 110},
        ]

        corr = compute_correlation_rows(rows)
        by_metric = {(row["policy"], row["x_metric"], row["y_metric"]): row for row in corr}

        self.assertLess(by_metric[("cache-aware-posc", "estimated_lcp_tokens", "real_ttft_ms")]["pearson_r"], 0)
        self.assertGreater(by_metric[("cache-aware-posc", "estimated_new_prefill_tokens", "real_ttft_ms")]["pearson_r"], 0)

    def test_summary_uses_real_timing_and_quality_rates(self):
        rows = [
            {"policy": "boolean-guarded", "success": True, "quality_sanity": True, "quality_score": 1.0, "real_ttft_ms": 100, "real_tpot_ms": 4, "real_latency_ms": 160, "estimated_lcp_tokens": 10, "estimated_new_prefill_tokens": 90},
            {"policy": "boolean-guarded", "success": True, "quality_sanity": True, "quality_score": 1.0, "real_ttft_ms": 200, "real_tpot_ms": 5, "real_latency_ms": 260, "estimated_lcp_tokens": 20, "estimated_new_prefill_tokens": 80},
        ]

        summary = summarize_real_replay_rows(rows, slo_buckets_ms=[150])

        self.assertEqual(summary[0]["completed_requests"], 2)
        self.assertEqual(summary[0]["quality_sanity_rate"], 1.0)
        self.assertEqual(summary[0]["slo_compliant_requests"], 1)
        self.assertEqual(summary[0]["mean_real_ttft_ms"], 150)


if __name__ == "__main__":
    unittest.main()
