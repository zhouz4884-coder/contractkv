import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.phase19b_end_to_end_live import stable_order
from scripts.install_vllm_v1_prefix_metrics_probe import install, uninstall


ROOT = Path(__file__).resolve().parents[1]


class Phase19EndToEndTests(unittest.TestCase):
    def test_prefix_probe_install_uninstall_is_byte_exact(self):
        source = (
            "class Scheduler(SchedulerInterface):\n\n"
            "    def schedule(self):\n"
            "        self._update_after_schedule(scheduler_output)\n"
        )
        with TemporaryDirectory() as temp_dir:
            scheduler = Path(temp_dir) / "scheduler.py"
            scheduler.write_text(source, encoding="utf-8")
            self.assertEqual(install(scheduler), "installed")
            self.assertIn("CONTRACTKV_PREFIX_METRICS_HELPER_BEGIN",
                          scheduler.read_text(encoding="utf-8"))
            self.assertEqual(uninstall(scheduler), "uninstalled")
            self.assertEqual(scheduler.read_text(encoding="utf-8"), source)
            self.assertFalse(scheduler.with_name(
                scheduler.name + ".contractkv-prefix-metrics.bak").exists())

    def test_stable_order_stops_before_dynamic_suffix(self):
        case = {"segments": [
            {"segment_id": "s0", "segment_type": "SYS_PROMPT"},
            {"segment_id": "s1", "segment_type": "RAG_CHUNK"},
            {"segment_id": "s2", "segment_type": "TOOL_OBS"},
            {"segment_id": "s3", "segment_type": "USER_QUERY"},
        ]}
        self.assertEqual(stable_order(case, ["s0", "s1", "s2", "s3"]), ["s0", "s1"])

    def test_final_replay_uses_ten_turn_horizon(self):
        script = (ROOT / "scripts/run_phase19b.sh").read_text(encoding="utf-8")
        self.assertIn("--turns 10", script)
        self.assertIn("--max-tokens 96", script)
        self.assertIn("CONTRACTKV_PREFIX_INITIAL_ONLY=1", script)

    def test_all_policies_use_unmeasured_turn_zero(self):
        runner = (ROOT / "scripts/phase19b_end_to_end_live.py").read_text(encoding="utf-8")
        summary = (ROOT / "scripts/phase19b_summarize_net_benefit.py").read_text(encoding="utf-8")
        self.assertIn('"row_type": "warmup"', runner)
        self.assertIn("for turn in range(1, args.turns):", runner)
        self.assertNotIn('range(1 if args.policy == "contractkv-full" else 0', runner)
        self.assertIn('"future_request_count_aligned"', summary)
        self.assertIn('"measured_turns_aligned"', summary)
        self.assertIn('"unmeasured_turn0_complete"', summary)
        self.assertIn('"dynamic_suffix_reuse_zero"', summary)
        self.assertIn("normalize_prefill", summary)
        self.assertIn('f(row["prompt_tokens"]) - f(row["prefix_hit_tokens"])', summary)
        self.assertIn('default=.30', summary)
        self.assertIn('default=.40', summary)

    def test_cross_model_uses_independent_gpu_by_default(self):
        script = (ROOT / "scripts/run_phase19c.sh").read_text(encoding="utf-8")
        self.assertIn('GPU_IDS="${GPU_IDS:-1}"', script)
        self.assertIn("--expected-full-cells 1", script)
        self.assertIn("--max-tokens 96", script)
        self.assertIn("--min-safe-coverage .50", script)
        self.assertIn("--min-retained-prefix-gain .50", script)
        calibration = script.index("phase19c_calibration_quality_labels_v0.csv")
        freeze = script.index("phase19c_finalize_model_policy.py")
        heldout = script.index("for policy in raw-order contractkv-full")
        self.assertLess(calibration, freeze)
        self.assertLess(freeze, heldout)


if __name__ == "__main__":
    unittest.main()
