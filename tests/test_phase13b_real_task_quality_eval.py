import unittest

from scripts.phase13b_real_task_quality_eval import build_quality_rows, summarize_quality_rows


class Phase13BRealTaskQualityTests(unittest.TestCase):
    def test_sspp_and_rar_are_explicit_projections(self):
        source = [
            {
                "layout": "raw-order",
                "dataset": "RULER",
                "task": "niah_single_1",
                "sample_id": "0",
                "success": True,
                "answer": "needle",
                "output_text": "needle",
            },
            {
                "layout": "canonical-slot",
                "dataset": "RULER",
                "task": "niah_single_1",
                "sample_id": "0",
                "success": True,
                "answer": "needle",
                "output_text": "needle",
            },
        ]
        rows = build_quality_rows(source)
        provenance = {row["policy"]: row["scoring_provenance"] for row in rows}
        self.assertEqual(provenance["vllm-raw-order"], "fresh_real_qwen3_8b_output")
        self.assertEqual(provenance["contractkv-caposc"], "fresh_real_qwen3_8b_output")
        self.assertEqual(provenance["contractkv-caposc-sspp"], "projected_from_real_caposc_output")
        self.assertEqual(provenance["contractkv-caposc-sspp-rar"], "projected_from_real_caposc_output")

    def test_quality_drop_uses_raw_policy_baseline(self):
        source = [
            {"layout": "raw-order", "dataset": "RepoBench", "task": "python", "sample_id": "0", "success": True, "answer": "good", "output_text": "good"},
            {"layout": "canonical-slot", "dataset": "RepoBench", "task": "python", "sample_id": "0", "success": True, "answer": "good", "output_text": "bad"},
        ]
        summary = summarize_quality_rows(build_quality_rows(source))
        canonical = [row for row in summary if row["policy"] == "contractkv-caposc"][0]
        self.assertEqual(float(canonical["quality_drop_vs_raw"]), 1.0)
        self.assertEqual(canonical["quality_drop_le_0_03"], False)


if __name__ == "__main__":
    unittest.main()
