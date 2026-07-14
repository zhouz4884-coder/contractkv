import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Phase23EvidenceTest(unittest.TestCase):
    def test_layout_ablation_is_safe_and_bounded(self):
        path = ROOT / "results/cross_model/llama_broad_generalization_r3/layout_ladder_ablation_v0.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = {row["strategy"]: row for row in csv.DictReader(handle)}
        self.assertEqual(set(rows), {"fixed_L3", "family_fixed_maximum", "certificate_guided_descent", "raw_fallback"})
        self.assertEqual(int(rows["fixed_L3"]["policy_attributable_quality_violations"]), 10)
        self.assertEqual(int(rows["certificate_guided_descent"]["policy_attributable_quality_violations"]), 0)
        self.assertEqual(float(rows["certificate_guided_descent"]["completion_rate"]), 1.0)

    def test_qualification_cost_is_small_and_stable(self):
        path = ROOT / "results/cross_model/llama_broad_generalization_r3/qualification_cost_v0.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(int(row["development_sessions"]), 25)
        self.assertLess(float(row["development_gpu_hours"]), 0.5)
        self.assertLess(float(row["runtime_lookup_p95_us"]), 1.0)

    def test_qwen14_gate_and_repeat_count(self):
        base = ROOT / "results/scale_up/qwen3_14b_tp2_v0"
        gate = json.loads((base / "gate_v0.json").read_text(encoding="utf-8"))
        self.assertTrue(gate["gate_pass"])
        self.assertEqual(gate["fresh_pairs"], 3)
        self.assertTrue(gate["policy_attributable_quality_violations_zero"])
        with (base / "repeat_summary_v0.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(float(row["net_mean_ttft_reduction_vs_raw"]) > 0.4 for row in rows))
        self.assertTrue(all(float(row["certified_prefix_physical_reuse"]) >= 0.95 for row in rows))


if __name__ == "__main__":
    unittest.main()
