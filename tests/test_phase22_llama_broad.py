import json
import tempfile
import unittest
from pathlib import Path

from scripts.phase22_llama_broad_live import eligible_level_descent, parse_ladder
from scripts.phase22_llama_broad_analysis import score_pairs
from scripts.phase22_llama_layout_ladder import expand_stable_segments, layout_for_level, split_text_preserving


class Phase22LlamaBroadTests(unittest.TestCase):
    def case(self):
        return {
            "trajectory_id": "mixed:0", "dataset": "Unknown", "task": "mixed",
            "segments": [
                {"segment_id": "s0", "segment_type": "SYS_PROMPT", "text": "system", "token_count": 1, "dependencies": []},
                {"segment_id": "t", "segment_type": "TOOL_OBS", "text": "dynamic", "token_count": 1, "dependencies": ["s0"]},
                {"segment_id": "c", "segment_type": "RAG_CHUNK", "text": "alpha  beta\ngamma delta epsilon zeta eta theta", "token_count": 8, "dependencies": ["s0"]},
                {"segment_id": "q", "segment_type": "USER_QUERY", "text": "query", "token_count": 1, "dependencies": ["c", "t"]},
            ],
        }

    def test_split_preserves_every_character(self):
        text = "def f():\n    return  7\n"
        self.assertEqual("".join(split_text_preserving(text, 4)), text)

    def test_progressive_prefix_is_monotonic_and_valid(self):
        case = expand_stable_segments(self.case())
        layouts = [layout_for_level(case, level) for level in ("L0", "L1", "L2", "L3")]
        self.assertEqual([layout["violated_edges"] for layout in layouts], [[], [], [], []])
        moved = [layout["moved_stable_tokens"] for layout in layouts]
        self.assertEqual(moved, sorted(moved))
        self.assertEqual(moved[0], 0)
        self.assertEqual(moved[-1], layouts[-1]["total_stable_tokens"])

    def test_layout_logic_does_not_branch_on_task_name(self):
        first = expand_stable_segments(self.case())
        second = json.loads(json.dumps(first)); second["dataset"] = "RepoBench"; second["task"] = "python_v1.1"
        for level in ("L0", "L1", "L2", "L3"):
            self.assertEqual(layout_for_level(first, level)["topological_order"],
                             layout_for_level(second, level)["topological_order"])

    def test_conservative_ladder_is_uniform_and_monotonic(self):
        ladder = parse_ladder("L0=0,L1=.0625,L2=.25,L3=.5")
        case = expand_stable_segments(self.case(), pieces=16)
        moved = [layout_for_level(case, level, ladder)["moved_stable_tokens"]
                 for level in ("L0", "L1", "L2", "L3")]
        self.assertEqual(moved, sorted(moved))
        self.assertLess(moved[-1], layout_for_level(case, "L3", ladder)["total_stable_tokens"])

    def test_raw_fallback_difference_is_not_attributed_to_policy(self):
        sessions = {"s": {"dataset": "RULER", "task": "niah_single_1", "answer": "needle"}}
        raw = [{"row_type": "future", "session_id": "s", "turn_id": 1, "output_text": "needle"}]
        candidate = [{"row_type": "future", "session_id": "s", "turn_id": 1,
                      "output_text": "miss", "effective_level": "L0"}]
        row = score_pairs(sessions, raw, candidate, "candidate")[0]
        self.assertTrue(row["quality_violation"])
        self.assertTrue(row["raw_fallback_pair_difference"])
        self.assertFalse(row["policy_attributable_quality_violation"])

    def test_frozen_level_descent_uses_only_development_eligible_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({
                "family_eligible_levels": {"Unknown:mixed": ["L1", "L2"]}
            }), encoding="utf-8")
            args = type("Args", (), {"mode": "frozen", "qualification_manifest": path})()
            self.assertEqual(eligible_level_descent(args, self.case(), "L3"), ["L2", "L1"])

    def test_final_sealed_artifacts_pass_paper_gate(self):
        root = Path("results/cross_model/llama_broad_generalization_r3")
        if not root.exists():
            self.skipTest("sealed Phase 22 artifacts are not present")
        gate = json.loads((root / "heldout_gate_v0.json").read_text(encoding="utf-8"))
        self.assertTrue(gate["paper_gate_pass"])
        self.assertFalse(gate["strong_gate_pass"])
        self.assertEqual(gate["heldout_sessions"], 50)
        self.assertEqual(gate["future_requests_per_repeat"], 450)
        self.assertEqual(gate["fresh_process_repeats"], 3)

        import csv
        with (root / "heldout_scope_aggregate_v0.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        global_row = next(row for row in rows if row["scope"] == "all")
        self.assertEqual(float(global_row["completion_rate"]), 1.0)
        self.assertGreaterEqual(float(global_row["net_mean_ttft_reduction"]), 0.25)
        self.assertGreaterEqual(float(global_row["new_prefill_reduction"]), 0.30)
        self.assertEqual(float(global_row["policy_attributable_quality_violations"]), 0.0)
        self.assertEqual(float(global_row["max_dynamic_suffix_reuse_tokens"]), 0.0)


if __name__ == "__main__":
    unittest.main()
