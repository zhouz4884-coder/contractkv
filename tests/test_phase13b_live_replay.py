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


if __name__ == "__main__":
    unittest.main()
