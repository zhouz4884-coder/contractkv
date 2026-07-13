import unittest

from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.phase19b_end_to_end_live import stable_order
from scripts.phase19b_end_to_end_live import request_context, validity_scope
from scripts.contractkv_certificate_scope import validation_errors
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

    def test_main_replay_uses_explicit_qualified_session_scope(self):
        args = Namespace(
            model_identity="model-a", model="served-a",
            certificate_scope_mode="qualified_session",
            policy_hash="policy-a", qualification_hash="qualification-a",
        )
        sample = {"dataset": "LongBench", "task": "hotpotqa"}
        base_segments = [
            {"segment_id": "sys", "segment_type": "SYS_PROMPT", "text": "system", "dependencies": []},
            {"segment_id": "doc", "segment_type": "RAG_CHUNK", "text": "stable", "dependencies": ["sys"]},
            {"segment_id": "obs", "segment_type": "TOOL_OBS", "text": "observation 0", "dependencies": ["sys"]},
            {"segment_id": "query", "segment_type": "USER_QUERY", "text": "question", "dependencies": ["doc", "obs"]},
        ]
        layout = {"topological_order": ["sys", "doc", "obs", "query"]}
        issued = validity_scope(args, sample, {"turn_id": 0, "segments": base_segments}, layout)
        changed = [dict(segment) for segment in base_segments]
        changed[2]["text"] = "observation 1"
        current = validity_scope(args, sample, {"turn_id": 1, "segments": changed}, layout)
        self.assertEqual(validation_errors(issued, request_context(current)), [])

    def test_observation_scope_rejects_future_observation(self):
        args = Namespace(
            model_identity="model-a", model="served-a",
            certificate_scope_mode="observation",
            policy_hash="policy-a", qualification_hash="",
        )
        sample = {"dataset": "RULER", "task": "niah"}
        segments = [
            {"segment_id": "sys", "segment_type": "SYS_PROMPT", "text": "system", "dependencies": []},
            {"segment_id": "obs", "segment_type": "TOOL_OBS", "text": "observation 0", "dependencies": ["sys"]},
        ]
        layout = {"topological_order": ["sys", "obs"]}
        issued = validity_scope(args, sample, {"turn_id": 0, "segments": segments}, layout)
        changed = [dict(segment) for segment in segments]
        changed[1]["text"] = "observation 1"
        current = validity_scope(args, sample, {"turn_id": 1, "segments": changed}, layout)
        errors = validation_errors(issued, request_context(current))
        self.assertIn("observation_identity_mismatch", errors)
        self.assertIn("observation_epoch_mismatch", errors)

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

    def test_async_future_rows_bind_request_local_scope_errors(self):
        source = (ROOT / "scripts/phase19b_end_to_end_live.py").read_text(encoding="utf-8")
        self.assertIn("exact_lcp_tokens, job_scope_errors) in jobs", source)
        self.assertIn('"certificate_scope_errors": job_scope_errors', source)


if __name__ == "__main__":
    unittest.main()
