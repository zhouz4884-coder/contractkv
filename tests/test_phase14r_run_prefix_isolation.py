import unittest

from scripts.phase14r_run_prefix_isolation import join_cell, summarize


class Phase14RPrefixIsolationRunnerTests(unittest.TestCase):
    def test_join_and_summary_use_server_request_id_and_real_metrics(self):
        plan = {"replicate_id": "0", "run_order": "0", "policy": "raw-order"}
        live = [{"request_id": "r1", "trajectory_id": "t", "turn_id": 1, "case_type": "rag", "success": True, "quality_sanity": True, "real_ttft_ms": 100, "real_tpot_ms": 10, "real_latency_ms": 200}]
        metrics = [{"request_id": "r1", "initial_prefill_observation": True, "prompt_tokens": 1000, "prefix_hit_tokens": 0, "new_prefill_tokens_this_iteration": 1000}]
        raw = join_cell(plan, "raw-order", live, metrics, "server.log", "metrics.jsonl")
        plan2 = {"replicate_id": "0", "run_order": "1", "policy": "cache-aware-posc"}
        live2 = [{**live[0], "request_id": "r2", "real_ttft_ms": 50}]
        metrics2 = [{**metrics[0], "request_id": "r2", "prefix_hit_tokens": 800, "new_prefill_tokens_this_iteration": 200}]
        caposc = join_cell(plan2, "cache-aware-posc", live2, metrics2, "server2.log", "metrics2.jsonl")
        summary = {row["policy"]: row for row in summarize(raw + caposc)}
        self.assertTrue(raw[0]["join_success"])
        self.assertEqual(summary["cache-aware-posc"]["ttft_reduction_vs_raw_pct"], 50.0)
        self.assertEqual(summary["cache-aware-posc"]["new_prefill_reduction_vs_raw_pct"], 80.0)


if __name__ == "__main__":
    unittest.main()
