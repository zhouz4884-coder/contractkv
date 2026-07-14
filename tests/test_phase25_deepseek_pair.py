from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ANALYSIS = load_module("phase25_analysis", ROOT / "scripts" / "phase25_deepseek_pair_analysis.py")


class DeepSeekPairProtocolTest(unittest.TestCase):
    def test_protocol_freezes_controlled_pair_and_primary_gates(self) -> None:
        protocol = json.loads(
            (ROOT / "configs" / "phase25_deepseek_v2_lite_pair_protocol.json").read_text(encoding="utf-8")
        )
        self.assertTrue(protocol["frozen_before_heldout"])
        self.assertEqual(set(protocol["models"]), {"chat", "coder"})
        self.assertEqual(protocol["shared_architecture"]["kv_lora_rank"], 512)
        self.assertEqual(protocol["runtime"]["tensor_parallel_size"], 2)
        self.assertEqual(protocol["runtime"]["concurrency"], 2)
        self.assertEqual(protocol["workload"]["stable_word_limit"], 1150)
        self.assertEqual(protocol["workload"]["maximum_input_tokens_after_chat_template"], 8064)
        self.assertEqual(protocol["workload"]["fresh_process_repeats"], 3)
        self.assertFalse(protocol["qualification"]["heldout_retuning_allowed"])
        self.assertEqual(protocol["primary_gates"]["minimum_certificate_coverage"], 0.5)
        self.assertEqual(protocol["primary_gates"]["minimum_new_prefill_reduction"], 0.3)
        self.assertEqual(protocol["primary_gates"]["minimum_net_mean_ttft_reduction"], 0.25)

    def test_mla_memory_boundary_forbids_qwen_gqa_conversion(self) -> None:
        protocol = json.loads(
            (ROOT / "configs" / "phase25_deepseek_v2_lite_pair_protocol.json").read_text(encoding="utf-8")
        )
        boundary = protocol["mla_measurement_boundary"]
        self.assertFalse(boundary["gqa_bytes_formula_reuse"])
        self.assertFalse(boundary["memory_gib_claim_allowed"])
        self.assertEqual(boundary["token_and_physical_block_metrics"], "required")

    def test_validate_cell_requires_real_prefix_and_physical_metrics(self) -> None:
        rows = []
        for session in range(2):
            rows.append({"row_type": "canary", "session_id": str(session)})
            for turn in range(1, 3):
                rows.append(
                    {
                        "row_type": "future",
                        "session_id": str(session),
                        "turn_id": turn,
                        "success": True,
                        "effective_level": "L1",
                        "certificate_scope_valid": True,
                        "dynamic_suffix_reuse_tokens": 0,
                        "prefix_hit_tokens": 16,
                        "physical_block_count": 4,
                    }
                )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cell.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            self.assertTrue(ANALYSIS.validate_cell(path, sessions=2, turns=3)["pass"])
            rows[-1]["physical_block_count"] = ""
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = ANALYSIS.validate_cell(path, sessions=2, turns=3)
            self.assertFalse(result["pass"])
            self.assertFalse(result["checks"]["physical_block_metrics_present"])

    def test_runner_uses_fresh_tp2_servers_and_frozen_fallback(self) -> None:
        script = (ROOT / "scripts" / "run_phase25_deepseek_pair.sh").read_text(encoding="utf-8")
        self.assertIn("--tensor-parallel-size 2", script)
        self.assertIn("--dtype bfloat16", script)
        self.assertIn("--enable-prefix-caching", script)
        self.assertIn("--minimum-admitted-coverage .5", script)
        self.assertIn("certificate_guided", json.loads(
            (ROOT / "configs" / "phase25_deepseek_v2_lite_pair_protocol.json").read_text(encoding="utf-8")
        )["qualification"]["fallback"])

    def test_fault_probe_accepts_conservative_rejection_but_not_publication(self) -> None:
        rows = [
            {
                "case_id": "normal-0", "case_class": "normal_safe", "fault_mode": "none",
                "txn_state": "COMMITTED", "verify_decision": "PASS", "certificate_issued": "True",
                "certificate_after_commit": "True", "policy_consistent": "True",
                "dynamic_suffix_reused_tokens": "0", "cache_entries_delta": "4",
            },
            {
                "case_id": "normal-1", "case_class": "normal_safe", "fault_mode": "none",
                "txn_state": "ABORTED", "verify_decision": "FAIL", "certificate_issued": "False",
                "certificate_after_commit": "False", "policy_consistent": "True",
                "dynamic_suffix_reused_tokens": "0", "cache_entries_delta": "0",
            },
            {
                "case_id": "cancel-before", "case_class": "cancel_before",
                "fault_mode": "cancel_before_verification", "txn_state": "ABORTED",
                "verify_decision": "FAIL", "certificate_issued": "False",
                "certificate_after_commit": "False", "policy_consistent": "True",
                "dynamic_suffix_reused_tokens": "0", "cache_entries_delta": "0",
            },
        ]
        self.assertTrue(all(ANALYSIS.fault_probe_checks(rows).values()))
        rows[-1]["cache_entries_delta"] = "1"
        self.assertFalse(ANALYSIS.fault_probe_checks(rows)["explicit_faults_fail_closed"])

    def test_manifest_mismatch_is_expected_policy_inconsistency(self) -> None:
        rows = [
            {
                "case_id": "normal-0", "case_class": "normal_safe", "fault_mode": "none",
                "txn_state": "COMMITTED", "verify_decision": "PASS", "certificate_issued": "True",
                "certificate_after_commit": "True", "policy_consistent": "True",
                "dynamic_suffix_reused_tokens": "0", "cache_entries_delta": "4",
            },
            {
                "case_id": "mismatch-model", "case_class": "manifest_mismatch", "fault_mode": "none",
                "txn_state": "ABORTED", "verify_decision": "FAIL", "certificate_issued": "False",
                "certificate_after_commit": "False", "policy_consistent": "False",
                "dynamic_suffix_reused_tokens": "0", "cache_entries_delta": "0",
            },
        ]
        self.assertTrue(all(ANALYSIS.fault_probe_checks(rows).values()))

    def test_backfill_cell_metrics_copies_real_block_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            cell = directory / "cell.jsonl"
            metrics = directory / "metrics.jsonl"
            cell.write_text(json.dumps({
                "row_type": "future", "request_id": "req-1", "success": True,
            }) + "\n", encoding="utf-8")
            metrics.write_text(json.dumps({
                "event": "prefix_cache_request_observation", "request_id": "req-1",
                "initial_prefill_observation": True, "physical_block_count": 17,
                "block_size": 16, "reused_physical_blocks": 9, "free_gpu_blocks": 100,
            }) + "\n", encoding="utf-8")
            result = ANALYSIS.backfill_cell_metrics(cell, metrics)
            self.assertTrue(result["complete"])
            row = json.loads(cell.read_text(encoding="utf-8"))
            self.assertEqual(row["physical_block_count"], 17)
            self.assertEqual(row["reused_physical_blocks"], 9)

    def test_certificate_diagnostic_is_development_only_and_records_causes(self) -> None:
        script = (ROOT / "scripts" / "phase25_deepseek_certificate_diagnostic.py").read_text(encoding="utf-8")
        self.assertIn("phase19b_session_id", script)
        self.assertIn('for level in ("L1", "L2", "L3")', script)
        self.assertIn("failure_reason", script)
        self.assertNotIn("heldout", script.lower())
        runner = (ROOT / "scripts" / "run_phase25_deepseek_diagnostics.sh").read_text(encoding="utf-8")
        self.assertIn("certificate_diagnostic_v0.jsonl", runner)
        self.assertIn("--tensor-parallel-size 2", runner)

    def test_final_pair_result_preserves_successes_and_negative_gate(self) -> None:
        result_dir = ROOT / "results" / "cross_model" / "deepseek_v2_lite_pair"
        gate = json.loads((result_dir / "pair_gate_v0.json").read_text(encoding="utf-8"))
        self.assertFalse(gate["pass"])
        self.assertFalse(gate["interpretation"]["moe_mla_architecture_generalization_supported"])
        for model in gate["models"]:
            self.assertEqual(model["completion_rate"], 1.0)
            self.assertEqual(model["policy_quality_violations"], 0.0)
            self.assertEqual(model["max_dynamic_suffix_reuse_tokens"], 0.0)
            self.assertGreater(model["certified_prefix_reuse"], 0.99)

    def test_coder_ruler_gain_and_repobench_boundary_are_machine_checked(self) -> None:
        path = ROOT / "results" / "cross_model" / "deepseek_v2_lite_pair" / "family_summary_v0.csv"
        rows = ANALYSIS.load_csv(path)
        coder_ruler = next(row for row in rows if row["model_key"] == "coder" and row["family"] == "RULER")
        coder_repo = next(row for row in rows if row["model_key"] == "coder" and row["family"] == "RepoBench")
        self.assertEqual(coder_ruler["frozen_level"], "L3")
        self.assertGreater(float(coder_ruler["net_mean_ttft_reduction"]), 0.50)
        self.assertGreater(float(coder_ruler["new_prefill_reduction"]), 0.95)
        self.assertEqual(coder_repo["frozen_level"], "L0")
        self.assertEqual(float(coder_repo["certificate_coverage"]), 0.0)


if __name__ == "__main__":
    unittest.main()
