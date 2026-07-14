from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "cross_model"


def read_csv(name: str) -> list[dict[str, str]]:
    with (RESULTS / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class Phase24WhyWhenAnalysisTest(unittest.TestCase):
    def test_cross_model_map_is_complete_and_fail_closed(self) -> None:
        rows = read_csv("phase24_cross_model_qualification_map_v0.csv")
        self.assertEqual(len(rows), 15)
        self.assertEqual(len({(row["model"], row["family"]) for row in rows}), 15)
        self.assertTrue(all(float(row["completion_rate"]) == 1.0 for row in rows))
        self.assertTrue(all(float(row["quality_violation_rate"]) == 0.0 for row in rows))
        llama = {row["family"]: row["safe_max_level"] for row in rows if row["model"].startswith("Llama")}
        self.assertEqual(
            llama,
            {"RULER": "L3", "HotpotQA": "L2", "NarrativeQA": "L2", "Qasper": "L0", "RepoBench": "L0"},
        )
        expected_global = {
            "Qwen3-8B": 0.4165976142337592,
            "Mistral-7B-Instruct-v0.3": 0.32322600289829584,
            "Llama-3.1-8B-Instruct": 0.2940578604056856,
        }
        for model, expected in expected_global.items():
            selected = [row for row in rows if row["model"] == model]
            requests = sum(int(row["future_requests"]) for row in selected)
            raw = sum(float(row["raw_mean_ttft_ms"]) * int(row["future_requests"]) for row in selected) / requests
            net = sum(float(row["net_mean_ttft_ms"]) * int(row["future_requests"]) for row in selected) / requests
            self.assertAlmostEqual((raw - net) / raw, expected)

    def test_layout_ladder_trades_aggressiveness_for_safety(self) -> None:
        rows = read_csv("phase24_layout_aggressiveness_ablation_v0.csv")
        dev = {row["strategy"]: row for row in rows if row["partition"] == "development"}
        self.assertGreater(int(dev["fixed_L3"]["policy_attributable_quality_violations"]), 0)
        self.assertEqual(int(dev["certificate_guided_descent"]["policy_attributable_quality_violations"]), 0)
        self.assertGreater(
            float(dev["certificate_guided_descent"]["new_prefill_reduction_vs_raw"]),
            float(dev["raw_fallback"]["new_prefill_reduction_vs_raw"]),
        )
        heldout = {row["strategy"]: row for row in rows if row["partition"] == "sealed_heldout"}
        self.assertGreater(
            float(heldout["certificate_guided_descent"]["safe_completed_session_coverage"]),
            float(heldout["family_fixed_maximum"]["safe_completed_session_coverage"]),
        )

    def test_qualification_cost_and_stability_are_frozen(self) -> None:
        cost = read_csv("phase24_qualification_cost_v0.csv")[0]
        self.assertEqual(int(cost["development_sessions"]), 25)
        self.assertLess(float(cost["development_gpu_hours"]), 0.5)
        self.assertLess(float(cost["runtime_lookup_p95_us"]), 1.0)
        rows = read_csv("phase24_qualification_stability_1_2_3_5_v0.csv")
        self.assertEqual({int(row["samples_per_family"]) for row in rows}, {1, 2, 3, 5})
        ruler_one = next(
            row for row in rows if row["family"] == "RULER:niah_single_1" and row["samples_per_family"] == "1"
        )
        self.assertEqual(float(ruler_one["selection_agreement_fraction"]), 1.0)

    def test_failure_scopes_do_not_fabricate_runtime_subreasons(self) -> None:
        rows = read_csv("phase24_certificate_failure_reasons_v0.csv")
        runtime = [row for row in rows if row["evidence_scope"].startswith("final_heldout_runtime_canary")]
        self.assertTrue(runtime)
        self.assertTrue(all(row["top1_path_mismatch"] == "" for row in runtime))
        self.assertTrue(all(row["target_absent"] == "" for row in runtime))
        self.assertTrue(all(int(row["scope_mismatch"]) == 0 for row in runtime))
        diagnostics = [row for row in rows if "candidate_token_path_diagnostic" in row["evidence_scope"]]
        self.assertGreater(sum(int(row["top1_path_mismatch"]) for row in diagnostics), 0)
        quality = [row for row in rows if "candidate_quality" in row["evidence_scope"]]
        self.assertGreater(sum(int(row["quality_gate_failure"]) for row in quality), 0)

    def test_margin_result_is_correlation_only(self) -> None:
        payload = json.loads((RESULTS / "phase24_margin_correlation_summary_v0.json").read_text(encoding="utf-8"))
        self.assertGreater(payload["candidate_margin_vs_pass_pearson"], 0)
        self.assertLess(payload["margin_degradation_vs_pass_pearson"], 0)
        self.assertIn("Correlation only", payload["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
