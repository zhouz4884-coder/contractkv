import tempfile
import unittest
from pathlib import Path

from scripts.audit_vllm_hook_points import PATTERNS, scan_source_tree, summarize_hook_points
from scripts.run_real_quality_matrix import (
    CONDITIONS,
    aggregate_quality_matrix,
    build_condition_messages,
    score_output,
)


class Phase10HardSystemsTests(unittest.TestCase):
    def sample(self):
        return {
            "dataset": "RULER",
            "task": "niah",
            "sample_id": "0",
            "segments": [
                {"type": "SYS_PROMPT", "text": "Find the key.", "token_count": 3},
                {"type": "SYNTHETIC_CONTEXT", "text": "The key is 7391024.", "token_count": 5},
                {"type": "USER_QUERY", "text": "What is the key?", "token_count": 5},
            ],
            "answer": "7391024",
        }

    def test_audit_scans_required_vllm_hook_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "core" / "scheduler.py").write_text(
                "class Scheduler: pass\nrequest_id = seq_group.request_id\nswap_in = True\n",
                encoding="utf-8",
            )
            (root / "core" / "block_manager.py").write_text(
                "class BlockManager:\n    block_table = []\n    gpu_blocks = []\n    cpu_blocks = []\n    def swap_out(self): pass\n",
                encoding="utf-8",
            )

            hits = scan_source_tree(root, PATTERNS)
            summary = summarize_hook_points(hits, root, "0.10.2", "/tmp/python")

            self.assertIn("scheduler", hits)
            self.assertGreaterEqual(hits["swap_in"]["total_hits"], 1)
            self.assertGreaterEqual(hits["swap_out"]["total_hits"], 1)
            self.assertEqual(summary["vllm_version"], "0.10.2")
            self.assertIn("request_id_mapping", summary["answers"])
            self.assertIn("swap_in_out_path", summary["answers"])

    def test_condition_messages_change_context_without_mutating_sample(self):
        sample = self.sample()

        baseline = build_condition_messages(sample, "full_context_baseline")
        evicted = build_condition_messages(sample, "segment_eviction")
        repaired = build_condition_messages(sample, "boundary_repair")

        self.assertIn("The key is 7391024", baseline[0]["content"])
        self.assertNotIn("The key is 7391024", evicted[0]["content"])
        self.assertIn("repair", repaired[0]["content"].lower())
        self.assertIn("The key is 7391024", sample["segments"][1]["text"])

    def test_real_quality_scoring_supports_contains_and_f1(self):
        good = score_output("The answer is 7391024.", "7391024", "RULER")
        bad = score_output("The answer is 111.", "7391024", "RULER")

        self.assertEqual(good["contains_answer"], 1.0)
        self.assertEqual(good["score"], 1.0)
        self.assertEqual(bad["contains_answer"], 0.0)
        self.assertLess(bad["score"], good["score"])

    def test_aggregate_quality_matrix_uses_baseline_drop(self):
        rows = [
            {"dataset": "RULER", "task": "niah", "condition": "full_context_baseline", "score": 1.0},
            {"dataset": "RULER", "task": "niah", "condition": "segment_eviction", "score": 0.25},
        ]

        matrix = aggregate_quality_matrix(rows)
        by_condition = {row["condition"]: row for row in matrix}

        self.assertEqual(by_condition["full_context_baseline"]["mean_quality_drop"], 0.0)
        self.assertEqual(by_condition["segment_eviction"]["mean_quality_drop"], 0.75)

    def test_required_conditions_are_registered(self):
        for condition in [
            "full_context_baseline",
            "segment_eviction",
            "context_truncation",
            "boundary_corruption",
            "boundary_repair",
            "contractkv_safe_decision",
        ]:
            self.assertIn(condition, CONDITIONS)


if __name__ == "__main__":
    unittest.main()
