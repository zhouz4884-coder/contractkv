import tempfile
import unittest
from pathlib import Path

from scripts.audit_vllm_v1_actuators import (
    ACTUATOR_NAMES,
    audit_v1_actuators,
    classify_actuator_decisions,
)
from scripts.install_vllm_v1_recompute_probe import install as install_recompute_probe
from scripts.install_vllm_v1_recompute_probe import uninstall as uninstall_recompute_probe
from scripts.build_recompute_actuator_probe_summary import summarize_recompute_probe


class Phase104ActuatorAuditTests(unittest.TestCase):
    def make_source_tree(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "v1" / "core" / "sched").mkdir(parents=True)
        (root / "v1" / "core").mkdir(exist_ok=True)
        (root / "v1" / "worker").mkdir(parents=True)
        (root / "engine").mkdir()
        (root / "worker").mkdir()
        (root / "v1" / "core" / "sched" / "scheduler.py").write_text(
            "\n".join(
                [
                    "class Scheduler:",
                    "    def schedule(self):",
                    "        preempted_reqs = []",
                    "        blocks_to_swap_in = []",
                    "        blocks_to_swap_out = []",
                    "        return SchedulerOutput()",
                ]
            ),
            encoding="utf-8",
        )
        (root / "v1" / "core" / "kv_cache_manager.py").write_text(
            "\n".join(
                [
                    "class KVCacheManager:",
                    "    def get_block_ids(self, request_id):",
                    "        return []",
                    "    def free(self, request):",
                    "        self.block_pool.free_blocks([])",
                ]
            ),
            encoding="utf-8",
        )
        (root / "v1" / "core" / "block_pool.py").write_text(
            "class BlockPool:\n    def get_num_free_blocks(self): return 1\n",
            encoding="utf-8",
        )
        (root / "v1" / "worker" / "gpu_model_runner.py").write_text(
            "prefix_cache_stats = True\nblock_table = []\n",
            encoding="utf-8",
        )
        (root / "engine" / "async_llm_engine.py").write_text(
            "async def add_request(request_id): pass\n",
            encoding="utf-8",
        )
        (root / "worker" / "worker.py").write_text(
            "def execute_model(): pass\n",
            encoding="utf-8",
        )
        return root

    def test_actuator_audit_emits_required_candidate_schema(self):
        root = self.make_source_tree()
        report = audit_v1_actuators(root, "0.10.2", "/tmp/python")

        self.assertEqual(report["schema_version"], "phase10_4_vllm_v1_actuator_candidates_v0")
        self.assertEqual(sorted(report["actuators"].keys()), sorted(ACTUATOR_NAMES))
        for name, candidate in report["actuators"].items():
            self.assertEqual(candidate["actuator"], name)
            for field in [
                "files",
                "call_path",
                "can_observe",
                "can_trigger",
                "risk",
                "minimum_probe",
                "decision",
            ]:
                self.assertIn(field, candidate)

    def test_actuator_decisions_rank_recompute_before_prefix_when_observed(self):
        root = self.make_source_tree()
        report = audit_v1_actuators(root, "0.10.2", "/tmp/python")
        decisions = classify_actuator_decisions(report["actuators"])

        self.assertIn(decisions["active_recompute_preemption"], {"open", "unknown"})
        self.assertIn(decisions["active_swap"], {"blocked", "unknown"})
        self.assertEqual(decisions["prefix_cache_layout"], "open")
        self.assertEqual(decisions["admission_gate"], "open")
        self.assertIn(report["recommended_10_4b_probe"], {"preemption_recompute", "prefix_cache_layout"})

    def test_active_swap_blocks_without_worker_copy_path(self):
        root = self.make_source_tree()
        report = audit_v1_actuators(root, "0.10.2", "/tmp/python")

        self.assertEqual(report["decisions"]["active_swap"], "blocked")
        self.assertIn("worker cache copy", report["actuators"]["active_swap"]["minimum_probe"])

    def test_actuator_audit_ignores_contractkv_probe_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "v1" / "core" / "sched").mkdir(parents=True)
            (root / "v1" / "core").mkdir(exist_ok=True)
            (root / "v1" / "worker").mkdir(parents=True)
            (root / "engine").mkdir()
            (root / "worker").mkdir()
            for rel in [
                "v1/core/kv_cache_manager.py",
                "v1/core/block_pool.py",
                "v1/worker/gpu_model_runner.py",
                "engine/async_llm_engine.py",
                "worker/worker.py",
            ]:
                (root / rel).write_text("# empty\n", encoding="utf-8")
            scheduler = root / "v1" / "core" / "sched" / "scheduler.py"
            scheduler.write_text(
                "def _contractkv_v1_probe_log_scheduler():\n"
                "    preempted_reqs = []\n"
                "    blocks_to_swap_out = []\n",
                encoding="utf-8",
            )

            report = audit_v1_actuators(root, "0.10.2", "/tmp/python")

            self.assertFalse(report["actuators"]["preemption_recompute"]["can_observe"])
            self.assertEqual(report["decisions"]["active_recompute_preemption"], "blocked")

    def test_recompute_probe_installer_is_guarded_and_reversible(self):
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = Path(tmp) / "scheduler.py"
            original = (
                "class Scheduler:\n"
                "    def schedule(self) -> SchedulerOutput:\n"
                "        scheduled_timestamp = time.monotonic()\n"
                "        # First, schedule the RUNNING requests.\n"
                "        return SchedulerOutput()\n"
            )
            scheduler.write_text(original, encoding="utf-8")

            status = install_recompute_probe(scheduler)
            patched = scheduler.read_text(encoding="utf-8")

            self.assertEqual(status, "installed")
            self.assertIn("CONTRACTKV_RECOMPUTE_PROBE", patched)
            self.assertIn("_contractkv_force_preempt_once", patched)
            self.assertIn("# First, schedule the RUNNING requests.", patched)

            status = uninstall_recompute_probe(scheduler)
            restored = scheduler.read_text(encoding="utf-8")

            self.assertEqual(status, "uninstalled")
            self.assertEqual(restored, original)

    def test_recompute_probe_summary_reports_block_delta_and_completion(self):
        events = [
            {
                "event": "contractkv_forced_recompute_preemption",
                "request_id": "req-1",
                "before_free_gpu_blocks": 10,
                "after_free_gpu_blocks": 14,
                "free_gpu_blocks_delta": 4,
                "preempt_latency_ms": 1.25,
            }
        ]
        requests = [{"request_index": 0, "success": True, "latency_ms": 123.0, "response_bytes": 512}]

        row = summarize_recompute_probe(events, requests, "qwen3-4b")

        self.assertEqual(row["model"], "qwen3-4b")
        self.assertEqual(row["forced_preemption_events"], 1)
        self.assertEqual(row["free_gpu_blocks_delta"], 4)
        self.assertTrue(row["request_completed"])
        self.assertTrue(row["active_recompute_probe_success"])


if __name__ == "__main__":
    unittest.main()
