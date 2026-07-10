import unittest

from scripts.phase13_heterogeneous_serving import build_phase13_workload
from scripts.phase13b_live_replay import (
    PHASE13B_POLICIES,
    PHASE13B_RAW_FIELDS,
    PHASE13B_SUMMARY_FIELDS,
    build_live_jobs,
    mock_live_sender,
    run_phase13b_live_replay,
    summarize_phase13b_rows,
)


class Phase13BLiveReplayTests(unittest.TestCase):
    def test_policy_set_keeps_phase13_main_four(self):
        self.assertEqual(
            PHASE13B_POLICIES,
            [
                "vllm-raw-order",
                "contractkv-caposc",
                "contractkv-caposc-sspp",
                "contractkv-caposc-sspp-rar",
            ],
        )

    def test_schema_contains_live_system_and_quality_fields(self):
        required_raw = {
            "phase13b_tier",
            "policy",
            "sspp_mode",
            "concurrency",
            "request_id",
            "success",
            "real_ttft_ms",
            "real_tpot_ms",
            "real_latency_ms",
            "batch_wall_time_ms",
            "quality_sanity",
            "quality_score",
            "compiler_overhead_ms",
            "sspp_prepare_ms",
            "sspp_hidden_fraction",
            "rar_trigger_reason",
            "rar_events",
            "blocks_freed",
            "free_block_delta",
            "recompute_tokens_saved",
            "error_type",
        }
        required_summary = {
            "phase13b_tier",
            "policy",
            "sspp_mode",
            "concurrency",
            "slo_ttft_ms",
            "completion_rate",
            "quality_sanity_rate",
            "slo_compliant_req_per_sec",
            "mean_real_ttft_ms",
            "p95_real_ttft_ms",
            "capacity_failures",
            "rar_events",
        }

        self.assertTrue(required_raw.issubset(set(PHASE13B_RAW_FIELDS)))
        self.assertTrue(required_summary.issubset(set(PHASE13B_SUMMARY_FIELDS)))

    def test_build_live_jobs_maps_sspp_modes(self):
        workload = build_phase13_workload(trajectories_per_type=1, turns=1)
        jobs = build_live_jobs(workload, concurrency=1, sspp_mode="real_lightweight")
        modes = {job["policy"]: job["sspp_mode"] for job in jobs}

        self.assertEqual(modes["vllm-raw-order"], "disabled")
        self.assertEqual(modes["contractkv-caposc"], "disabled")
        self.assertEqual(modes["contractkv-caposc-sspp"], "real_lightweight")
        self.assertEqual(modes["contractkv-caposc-sspp-rar"], "real_lightweight")

    def test_live_jobs_isolate_vllm_prefix_cache_between_experiment_cells(self):
        workload = build_phase13_workload(trajectories_per_type=1, turns=2)
        jobs_c1 = build_live_jobs(workload, concurrency=1, sspp_mode="real_lightweight", run_id="final-a")
        jobs_c2 = build_live_jobs(workload, concurrency=2, sspp_mode="real_lightweight", run_id="final-a")

        namespaces_c1 = {
            job["policy"]: job["cache_namespace"]
            for job in jobs_c1
        }
        self.assertEqual(len(set(namespaces_c1.values())), len(PHASE13B_POLICIES))
        self.assertTrue(all(namespace.startswith("final-a-") and namespace.endswith("-c1") for namespace in namespaces_c1.values()))
        self.assertTrue(all(job["cache_namespace"].endswith("-c2") for job in jobs_c2))
        self.assertTrue(
            all(job["cache_namespace"] in job["messages"][0]["content"] for job in jobs_c1 + jobs_c2)
        )

    def test_live_replay_records_batch_wall_time_for_goodput(self):
        workload = build_phase13_workload(trajectories_per_type=1, turns=1)
        rows = run_phase13b_live_replay(
            workload,
            concurrencies=[2],
            slo_buckets_ms=[500],
            sspp_mode="real_lightweight",
            sender=mock_live_sender,
            base_url="mock://vllm",
            model="mock-model",
            policies=["vllm-raw-order"],
            run_id="wall-clock-test",
        )

        self.assertTrue(all(float(row["batch_wall_time_ms"]) > 0 for row in rows))
        summary = summarize_phase13b_rows(rows)
        expected = int(summary[0]["slo_compliant_requests"]) / (float(rows[0]["batch_wall_time_ms"]) / 1000.0)
        self.assertAlmostEqual(float(summary[0]["slo_compliant_req_per_sec"]), expected, places=5)

    def test_mock_live_replay_produces_rows_for_light_and_pressure_tiers(self):
        workload = build_phase13_workload(trajectories_per_type=1, turns=1)
        rows = run_phase13b_live_replay(
            workload,
            concurrencies=[1, 6],
            slo_buckets_ms=[300, 500],
            sspp_mode="real_lightweight",
            sender=mock_live_sender,
            base_url="mock://vllm",
            model="mock-model",
        )

        tiers = {row["phase13b_tier"] for row in rows}
        self.assertEqual(tiers, {"B-1-live-serving", "B-2-live-pressure"})
        self.assertTrue(any(row["policy"] == "contractkv-caposc-sspp-rar" and int(row["rar_events"]) >= 0 for row in rows))
        self.assertTrue(all(row["quality_sanity"] for row in rows if row["success"]))

    def test_summary_keeps_slo_buckets_and_capacity_failures(self):
        workload = build_phase13_workload(trajectories_per_type=1, turns=1)
        rows = run_phase13b_live_replay(
            workload,
            concurrencies=[1, 6],
            slo_buckets_ms=[300, 500],
            sspp_mode="accounting",
            sender=mock_live_sender,
            base_url="mock://vllm",
            model="mock-model",
        )
        summary = summarize_phase13b_rows(rows)

        self.assertEqual({float(row["slo_ttft_ms"]) for row in summary}, {300.0, 500.0})
        self.assertTrue(any(int(row["capacity_failures"]) >= 0 for row in summary))

    def test_policy_filter_runs_only_selected_live_cells(self):
        workload = build_phase13_workload(trajectories_per_type=1, turns=1)
        rows = run_phase13b_live_replay(
            workload,
            concurrencies=[6],
            slo_buckets_ms=[500],
            sspp_mode="real_lightweight",
            sender=mock_live_sender,
            base_url="mock://vllm",
            model="mock-model",
            policies=["contractkv-caposc-sspp-rar"],
        )

        self.assertEqual({row["policy"] for row in rows}, {"contractkv-caposc-sspp-rar"})


if __name__ == "__main__":
    unittest.main()
