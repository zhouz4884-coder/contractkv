import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "vllm_025_structural_relevance_audit.py"
)
SPEC = importlib.util.spec_from_file_location("vllm_025_audit", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeTokenizer:
    def encode(self, text, add_special_tokens=False):
        return text.split()

    def decode(self, tokens):
        return " ".join(tokens)


class Vllm025AuditTests(unittest.TestCase):
    def test_prometheus_source_labels_are_separated(self):
        metrics = MODULE.parse_prometheus_metrics(
            """
vllm:prefix_cache_queries_total{engine="0"} 100
vllm:prefix_cache_hits_total{engine="0"} 64
vllm:prompt_tokens_by_source_total{source="local_compute"} 36
vllm:prompt_tokens_by_source_total{source="local_cache_hit"} 64
"""
        )
        self.assertEqual(metrics["vllm:prefix_cache_queries_total"], 100)
        self.assertEqual(
            metrics["vllm:prompt_tokens_by_source_total:local_compute"], 36
        )
        self.assertEqual(
            metrics["vllm:prompt_tokens_by_source_total:local_cache_hit"], 64
        )

    def test_context_trim_keeps_answer_when_present(self):
        tokenizer = FakeTokenizer()
        context = " ".join(f"w{i}" for i in range(100))
        trimmed = MODULE.trim_context_around_answer(
            tokenizer, context, "w70", target_tokens=20
        )
        self.assertIn("w70", trimmed.split())
        self.assertEqual(len(trimmed.split()), 20)

    def test_list_answer_uses_real_reference(self):
        self.assertAlmostEqual(
            MODULE.quality_score(
                "LongBench", "The answer is Miller v. California.", ["Miller v. California"]
            ),
            2 / 3,
        )
        self.assertEqual(
            MODULE.answer_references(["Miller v. California"]),
            ["Miller v. California"],
        )

    def test_summary_reports_compiled_reduction(self):
        rows = []
        for repeat in (1, 2, 3):
            rows.extend(
                [
                    {
                        "runtime_version": "0.25.1",
                        "fresh_repeat": repeat,
                        "dataset": "RULER",
                        "task": "niah",
                        "sample_id": "0",
                        "layout": "raw",
                        "success": True,
                        "quality_pass": True,
                        "quality_score": 1,
                        "ttft_ms": 100,
                        "tpot_ms": 10,
                        "total_latency_ms": 150,
                        "prompt_tokens": 1000,
                        "metric_prefix_hits": 100,
                        "observed_new_prefill_tokens": 900,
                        "prefix_hit_ratio": 0.1,
                        "output_text": "answer",
                    },
                    {
                        "runtime_version": "0.25.1",
                        "fresh_repeat": repeat,
                        "dataset": "RULER",
                        "task": "niah",
                        "sample_id": "0",
                        "layout": "compiled",
                        "success": True,
                        "quality_pass": True,
                        "quality_score": 1,
                        "ttft_ms": 40,
                        "tpot_ms": 10,
                        "total_latency_ms": 90,
                        "prompt_tokens": 1000,
                        "metric_prefix_hits": 700,
                        "observed_new_prefill_tokens": 300,
                        "prefix_hit_ratio": 0.7,
                        "output_text": "answer",
                    },
                ]
            )
        summary = MODULE.summarize(rows)
        compiled = next(row for row in summary if row["layout"] == "compiled")
        self.assertEqual(compiled["fresh_processes"], 3)
        self.assertEqual(compiled["ttft_reduction_vs_raw_pct"], 60)
        self.assertAlmostEqual(
            compiled["new_prefill_reduction_vs_raw_pct"], 66.666667
        )
        self.assertEqual(compiled["paired_output_equal_rate"], 1)
        self.assertEqual(compiled["mean_quality_delta_vs_raw"], 0)


if __name__ == "__main__":
    unittest.main()
