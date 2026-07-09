import unittest

from scripts.phase12_concurrent_prefix_cache_replay import (
    aggregate_concurrent_replay,
    build_concurrent_prompt_case,
    select_mixed_workload,
)
from scripts.phase12_task_quality_sanity import (
    aggregate_quality_sanity,
    build_task_quality_prompt_case,
    score_answer,
    select_quality_subset,
)


SAMPLE = {
    "dataset": "LongBench",
    "task": "hotpotqa",
    "sample_id": "0",
    "segments": [
        {"type": "SYS_PROMPT", "text": "Answer from context.", "token_count": 3},
        {"type": "RAG_CHUNK", "text": "Paris is the capital of France. Stable evidence block.", "token_count": 9},
        {"type": "USER_QUERY", "text": "What is the capital of France?", "token_count": 6},
    ],
    "answer": "Paris",
    "metadata": {"evaluation_ready": True},
}


class Phase12ConcurrentReplayTests(unittest.TestCase):
    def test_concurrent_prompt_layout_keeps_stable_context_before_tool_obs_only_for_canonical(self):
        raw = build_concurrent_prompt_case(SAMPLE, "raw-order", repeat_id=1, stable_word_limit=64)
        canonical = build_concurrent_prompt_case(SAMPLE, "canonical-slot", repeat_id=1, stable_word_limit=64)

        raw_turn2 = raw["turn2_messages"][1]["content"]
        canonical_turn2 = canonical["turn2_messages"][1]["content"]

        self.assertLess(raw_turn2.index("[TOOL_OBS_DYNAMIC]"), raw_turn2.index("[STABLE_CONTEXT]"))
        self.assertLess(canonical_turn2.index("[STABLE_CONTEXT]"), canonical_turn2.index("[TOOL_OBS_DYNAMIC]"))
        self.assertIn(raw["expected_answer"], raw_turn2)
        self.assertEqual(raw["expected_answer"], canonical["expected_answer"])

    def test_mixed_workload_selects_ruler_longbench_and_repobench(self):
        samples = [
            {**SAMPLE, "dataset": "RULER", "task": "niah_single_1", "sample_id": "r0"},
            {**SAMPLE, "dataset": "RULER", "task": "niah_single_1", "sample_id": "r1"},
            {**SAMPLE, "dataset": "LongBench", "task": "hotpotqa", "sample_id": "l0"},
            {**SAMPLE, "dataset": "RepoBench", "task": "python_repository_completion", "sample_id": "p0"},
        ]

        selected = select_mixed_workload(samples, cases_per_source=1)

        self.assertEqual([item["dataset"] for item in selected], ["RULER", "LongBench", "RepoBench"])

    def test_concurrent_summary_computes_slo_compliant_requests_per_second(self):
        rows = [
            {"layout": "raw-order", "prefix_cache_enabled": True, "concurrency": 2, "batch_id": "raw-c2", "success": True, "quality_sanity": True, "ttft_ms": 638, "tpot_ms": 5, "total_latency_ms": 700, "batch_wall_time_ms": 1000},
            {"layout": "raw-order", "prefix_cache_enabled": True, "concurrency": 2, "batch_id": "raw-c2", "success": True, "quality_sanity": True, "ttft_ms": 720, "tpot_ms": 5, "total_latency_ms": 790, "batch_wall_time_ms": 1000},
            {"layout": "canonical-slot", "prefix_cache_enabled": True, "concurrency": 2, "batch_id": "canonical-c2", "success": True, "quality_sanity": True, "ttft_ms": 59, "tpot_ms": 5, "total_latency_ms": 120, "batch_wall_time_ms": 500},
            {"layout": "canonical-slot", "prefix_cache_enabled": True, "concurrency": 2, "batch_id": "canonical-c2", "success": True, "quality_sanity": True, "ttft_ms": 80, "tpot_ms": 5, "total_latency_ms": 140, "batch_wall_time_ms": 500},
            {"layout": "cold-raw", "prefix_cache_enabled": False, "concurrency": 2, "batch_id": "cold-c2", "success": True, "quality_sanity": True, "ttft_ms": 650, "tpot_ms": 5, "total_latency_ms": 720, "batch_wall_time_ms": 1100},
        ]

        summary = aggregate_concurrent_replay(rows, slo_buckets_ms=[100, 200, 500, 700, 1000])
        by_key = {(row["layout"], row["prefix_cache_enabled"], row["concurrency"], row["slo_ttft_ms"]): row for row in summary}

        self.assertEqual(by_key[("canonical-slot", True, 2, 100)]["slo_compliant_requests"], 2)
        self.assertEqual(by_key[("canonical-slot", True, 2, 100)]["slo_compliant_req_per_sec"], 4.0)
        self.assertEqual(by_key[("raw-order", True, 2, 100)]["slo_compliant_requests"], 0)
        self.assertEqual(by_key[("raw-order", True, 2, 700)]["slo_compliant_requests"], 1)
        self.assertEqual(by_key[("cold-raw", False, 2, 700)]["completed_requests"], 1)
        self.assertGreater(by_key[("canonical-slot", True, 2, 200)]["ttft_reduction_vs_raw_pct"], 80.0)


class Phase12TaskQualityTests(unittest.TestCase):
    def test_quality_prompt_layout_preserves_query_and_changes_only_dynamic_position(self):
        raw = build_task_quality_prompt_case(SAMPLE, "raw-order", stable_word_limit=64)
        canonical = build_task_quality_prompt_case(SAMPLE, "canonical-slot", stable_word_limit=64)

        raw_turn2 = raw["turn2_messages"][1]["content"]
        canonical_turn2 = canonical["turn2_messages"][1]["content"]

        self.assertIn("What is the capital of France?", raw_turn2)
        self.assertIn("What is the capital of France?", canonical_turn2)
        self.assertLess(raw_turn2.index("[TOOL_OBS_DYNAMIC]"), raw_turn2.index("[STABLE_CONTEXT]"))
        self.assertLess(canonical_turn2.index("[STABLE_CONTEXT]"), canonical_turn2.index("[TOOL_OBS_DYNAMIC]"))

    def test_select_quality_subset_caps_each_task(self):
        samples = [
            {**SAMPLE, "task": "hotpotqa", "sample_id": "0"},
            {**SAMPLE, "task": "hotpotqa", "sample_id": "1"},
            {**SAMPLE, "task": "qasper", "sample_id": "2"},
        ]
        selected = select_quality_subset(samples, tasks=["hotpotqa", "qasper"], samples_per_task=1)

        self.assertEqual([item["sample_id"] for item in selected], ["0", "2"])

    def test_score_answer_uses_contains_or_token_f1(self):
        self.assertEqual(score_answer("The answer is Paris.", "Paris", "LongBench")["score"], 1.0)
        self.assertGreater(score_answer("capital france paris", "Paris France", "LongBench")["token_f1"], 0.0)

    def test_quality_summary_reports_canonical_drop_vs_raw(self):
        rows = [
            {"dataset": "LongBench", "task": "hotpotqa", "layout": "raw-order", "success": True, "score": 1.0, "ttft_ms": 600, "total_latency_ms": 700},
            {"dataset": "LongBench", "task": "hotpotqa", "layout": "canonical-slot", "success": True, "score": 0.98, "ttft_ms": 60, "total_latency_ms": 120},
        ]

        summary = aggregate_quality_sanity(rows)
        by_layout = {(row["task"], row["layout"]): row for row in summary}

        self.assertEqual(by_layout[("hotpotqa", "canonical-slot")]["quality_drop_vs_raw"], 0.02)
        self.assertGreater(by_layout[("hotpotqa", "canonical-slot")]["ttft_reduction_vs_raw_pct"], 80.0)


if __name__ == "__main__":
    unittest.main()
