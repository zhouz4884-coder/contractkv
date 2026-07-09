import unittest

from scripts.phase13_heterogeneous_serving import (
    PHASE13_POLICIES,
    PHASE13_RAW_FIELDS,
    PHASE13_SUMMARY_FIELDS,
    build_phase13_workload,
    run_phase13_ledger_replay,
    summarize_phase13_rows,
)


class Phase13HeterogeneousServingTests(unittest.TestCase):
    def test_workload_contains_five_agent_types(self):
        workload = build_phase13_workload(trajectories_per_type=1, turns=2)
        case_types = {row["case_type"] for row in workload}

        self.assertEqual(
            case_types,
            {
                "code_agent",
                "rag_agent",
                "mixed_agent",
                "tool_call_agent",
                "long_history_agent",
            },
        )

    def test_policy_set_matches_phase13_main_comparison(self):
        self.assertEqual(
            PHASE13_POLICIES,
            [
                "vllm-raw-order",
                "contractkv-caposc",
                "contractkv-caposc-sspp",
                "contractkv-caposc-sspp-rar",
            ],
        )

    def test_raw_and_summary_schema_include_end_to_end_metrics(self):
        required_raw = {
            "policy",
            "case_type",
            "concurrency",
            "slo_ttft_ms",
            "ttft_ms",
            "tpot_ms",
            "completion_success",
            "quality_bad",
            "compiler_overhead_ms",
            "caposc_selected_policy",
            "sspp_hidden_fraction",
            "rar_events",
            "blocks_freed",
            "recompute_tokens_saved",
            "capacity_failure",
        }
        required_summary = {
            "policy",
            "concurrency",
            "slo_ttft_ms",
            "slo_compliant_req_per_sec",
            "p95_ttft_ms",
            "completion_rate",
            "quality_bad_rate",
            "compiler_overhead_ms_mean",
            "sspp_hidden_fraction_mean",
            "rar_events",
            "total_blocks_freed",
            "total_recompute_tokens_saved",
            "capacity_failures",
        }

        self.assertTrue(required_raw.issubset(set(PHASE13_RAW_FIELDS)))
        self.assertTrue(required_summary.issubset(set(PHASE13_SUMMARY_FIELDS)))

    def test_replay_produces_sspp_and_rar_signals_for_combined_policy(self):
        workload = build_phase13_workload(trajectories_per_type=1, turns=2)
        rows = run_phase13_ledger_replay(workload, concurrencies=[1, 4], slo_buckets_ms=[100, 300])
        combined = [row for row in rows if row["policy"] == "contractkv-caposc-sspp-rar"]

        self.assertTrue(combined)
        self.assertTrue(any(float(row["sspp_hidden_fraction"]) > 0.0 for row in combined))
        self.assertTrue(any(int(row["rar_events"]) > 0 for row in combined if int(row["concurrency"]) >= 4))

    def test_summary_reports_policy_concurrency_slo_rows(self):
        workload = build_phase13_workload(trajectories_per_type=1, turns=2)
        rows = run_phase13_ledger_replay(workload, concurrencies=[1], slo_buckets_ms=[100, 300])
        summary = summarize_phase13_rows(rows)

        policies = {row["policy"] for row in summary}
        slos = {float(row["slo_ttft_ms"]) for row in summary}

        self.assertEqual(policies, set(PHASE13_POLICIES))
        self.assertEqual(slos, {100.0, 300.0})


if __name__ == "__main__":
    unittest.main()
