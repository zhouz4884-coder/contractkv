import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExternalSGLangBaselineTests(unittest.TestCase):
    def test_external_baseline_uses_same_frozen_qwen_trace(self):
        script = (ROOT / "scripts/run_external_sglang_baseline.sh").read_text(encoding="utf-8")
        self.assertIn("phase19b_untouched_sessions_v0.jsonl", script)
        self.assertIn("--concurrency 2", script)
        self.assertIn("--turns 10", script)
        self.assertIn("96 2600 8150", script)
        self.assertIn("offline-safe-compiled", script)
        self.assertIn("Mistral-7B-Instruct-v0.3", script)
        self.assertIn("for repeat in 1 2 3", script)

    def test_external_runner_never_claims_hidden_cache_hits(self):
        source = (ROOT / "scripts/run_external_sglang_raw_replay.py").read_text(encoding="utf-8")
        self.assertIn("cached_tokens_observable_rate", source)
        self.assertIn("reported only if the backend exposes", source)

    def test_each_server_has_isolated_process_group_and_single_driver_lock(self):
        script = (ROOT / "scripts/run_external_sglang_baseline.sh").read_text(encoding="utf-8")
        self.assertIn('flock -n 9', script)
        self.assertIn('setsid "$SGLANG_PY" -m sglang.launch_server', script)
        self.assertIn('kill -TERM -- "-$server"', script)
        self.assertIn('--attention-backend triton', script)

    def test_completed_cells_are_verified_and_resumed_without_overwrite(self):
        script = (ROOT / "scripts/run_external_sglang_baseline.sh").read_text(encoding="utf-8")
        self.assertIn("cell_complete", script)
        self.assertIn("rows == 500", script)
        self.assertIn('data.get("completed_requests") == 450', script)
        self.assertIn("SKIP_COMPLETE", script)


if __name__ == "__main__":
    unittest.main()
