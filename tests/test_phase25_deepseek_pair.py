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


if __name__ == "__main__":
    unittest.main()
