import unittest
from unittest.mock import patch

from scripts.phase14d_live_mixed_serving import POLICIES, _run_session, summarize


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

    def test_cell_id_is_not_in_forwarded_prompt(self):
        entry = {
            "case": {"trajectory_id": "t", "turn_id": 0, "expected_answer": "ok", "unsafe_answer": "bad", "segments": []},
            "family": "rag_agent", "source_sample": {"dataset": "LongBench", "task": "hotpotqa"},
        }
        compiled = {"topological_order": [], "selected_policy": "raw-order", "layout_decision": "raw_order", "actual_prompt_tokens": 0, "estimated_lcp_tokens": 0, "estimated_new_prefill_tokens": 0, "violated_edges": []}
        with patch("scripts.phase14d_live_mixed_serving._compile_job", return_value={"compiled": compiled, "predicted_risk": 0.0, "qc_fallback": False, "messages": [{"role": "system", "content": "neutral"}, {"role": "user", "content": "payload"}]}), patch("scripts.phase14d_live_mixed_serving.send_chat_stream", return_value={"success": True, "request_id": "r", "output_text": "ok", "ttft_ms": 1, "tpot_ms": 1, "total_latency_ms": 1, "output_tokens": 1}) as send:
            _run_session([{"entry": entry}], 0.0, 0.0, "http://x", "m", 1, 1.0, "policy-bearing-cell", "vllm-raw-order", 1, "burst", {}, None, 8192)
        forwarded = send.call_args.args[2]
        self.assertNotIn("policy-bearing-cell", str(forwarded))


if __name__ == "__main__":
    unittest.main()
