import unittest

from scripts.phase12e_multiturn_trajectory_builder import build_multiturn_trajectories
from scripts.phase12g_concurrent_caposc_replay import (
    CONCURRENT_RAW_FIELDS,
    CONCURRENT_SUMMARY_FIELDS,
    build_concurrent_oracle_rows,
    prepare_concurrent_jobs,
    run_concurrent_replay,
    summarize_concurrent_rows,
)
import scripts.phase12g_concurrent_caposc_replay as phase12g


class Phase12GConcurrentCaposcTests(unittest.TestCase):
    def test_concurrent_schema_contains_policy_concurrency_and_wall_time(self):
        self.assertIn("concurrency", CONCURRENT_RAW_FIELDS)
        self.assertIn("replay_wall_time_sec", CONCURRENT_RAW_FIELDS)
        self.assertIn("concurrency", CONCURRENT_SUMMARY_FIELDS)
        self.assertIn("slo_compliant_req_per_sec", CONCURRENT_SUMMARY_FIELDS)

    def test_prepare_jobs_compiles_layouts_and_keeps_policy_ledger(self):
        cases = build_multiturn_trajectories(trajectories_per_type=1, turns=2)
        jobs = prepare_concurrent_jobs(cases, ["boolean-guarded", "cache-aware-posc"], concurrency=2)

        self.assertEqual(len(jobs), 12)
        self.assertTrue(all(job["messages"] for job in jobs))
        self.assertTrue(all("estimated_new_prefill_tokens" in job for job in jobs))
        caposc_jobs = [job for job in jobs if job["policy"] == "cache-aware-posc"]
        self.assertTrue(any(job["selected_policy"] in {"cache-aware-posc", "posc", "boolean-guarded"} for job in caposc_jobs))

    def test_summary_uses_replay_wall_time_for_slo_req_per_sec(self):
        rows = [
            {"concurrency": 2, "policy": "cache-aware-posc", "success": True, "quality_sanity": True, "quality_score": 1.0, "real_ttft_ms": 80, "real_tpot_ms": 5, "real_latency_ms": 150, "replay_wall_time_sec": 1.0, "estimated_lcp_tokens": 10, "estimated_new_prefill_tokens": 90},
            {"concurrency": 2, "policy": "cache-aware-posc", "success": True, "quality_sanity": True, "quality_score": 1.0, "real_ttft_ms": 180, "real_tpot_ms": 5, "real_latency_ms": 250, "replay_wall_time_sec": 1.0, "estimated_lcp_tokens": 20, "estimated_new_prefill_tokens": 80},
        ]

        summary = summarize_concurrent_rows(rows, slo_buckets_ms=[100])

        self.assertEqual(summary[0]["slo_compliant_requests"], 1)
        self.assertEqual(summary[0]["slo_compliant_req_per_sec"], 1.0)

    def test_oracle_is_selected_per_concurrency_and_turn(self):
        rows = [
            {"concurrency": 4, "trajectory_id": "t", "turn_id": 0, "case_type": "code", "policy": "boolean-guarded", "success": True, "quality_sanity": True, "quality_score": 1.0, "real_ttft_ms": 90},
            {"concurrency": 4, "trajectory_id": "t", "turn_id": 0, "case_type": "code", "policy": "cache-aware-posc", "success": True, "quality_sanity": True, "quality_score": 1.0, "real_ttft_ms": 70},
            {"concurrency": 2, "trajectory_id": "t", "turn_id": 0, "case_type": "code", "policy": "cache-aware-posc", "success": True, "quality_sanity": True, "quality_score": 1.0, "real_ttft_ms": 60},
        ]

        oracle = build_concurrent_oracle_rows(rows)

        self.assertEqual(len(oracle), 2)
        by_conc = {row["concurrency"]: row for row in oracle}
        self.assertEqual(by_conc[4]["oracle_source_policy"], "cache-aware-posc")
        self.assertEqual(by_conc[2]["real_ttft_ms"], 60)

    def test_warmup_once_runs_unrecorded_pass_before_measured_rows(self):
        cases = build_multiturn_trajectories(trajectories_per_type=1, turns=1)[:1]
        calls = []
        original = phase12g._run_job

        def fake_run_job(base_url, model, max_tokens, timeout, slo_ttft_ms, job):
            calls.append(job["policy"])
            return {
                "concurrency": job["concurrency"],
                "trajectory_id": job["trajectory_id"],
                "turn_id": job["turn_id"],
                "case_type": job["case_type"],
                "policy": job["policy"],
                "selected_policy": job["selected_policy"],
                "success": True,
                "quality_sanity": True,
                "quality_score": 1.0,
                "real_ttft_ms": 10,
                "real_tpot_ms": 1,
                "real_latency_ms": 20,
                "replay_wall_time_sec": 0,
                "estimated_lcp_tokens": 0,
                "estimated_new_prefill_tokens": 1,
                "error_type": "none",
            }

        try:
            phase12g._run_job = fake_run_job
            rows = run_concurrent_replay(cases, "http://example/v1", "model", ["boolean-guarded"], [1], 1, 1, 100, warmup_once=True, quiet=True)
        finally:
            phase12g._run_job = original

        self.assertEqual(len(calls), 2)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
