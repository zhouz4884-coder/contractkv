import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_extended_ruler_sessions import digest_rows
from scripts.summarize_common_ruler_quality import truth
from scripts.verify_frozen_ruler_sessions import verify


class CommonRulerCrossModelTests(unittest.TestCase):
    def test_frozen_split_verifier_accepts_exact_commitment(self):
        rows = [{
            "dataset": "RULER", "task": "niah_single_1", "sample_id": str(i),
            "phase19b_session_id": f"s{i}",
        } for i in range(2)]
        digest = digest_rows(rows)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions = root / "sessions.jsonl"
            sessions.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            commitment = root / "commitment.json"
            commitment.write_text(json.dumps({"selected_sha256": digest, "sessions": 2, "turns": 10}), encoding="utf-8")
            result = verify(sessions, commitment, digest, 2, 10)
            self.assertEqual(result["status"], "pass")

    def test_runner_freezes_identical_common_scope(self):
        runner = (Path(__file__).resolve().parents[1] / "scripts/run_common_ruler_cross_model.sh").read_text(encoding="utf-8")
        self.assertIn('EXPECTED_SHA="7fe10a55f82056125b6acb478aa24bd4883c12c4f6bfd19b3dedfd1f6e13f616"', runner)
        self.assertIn("--turns 10 --max-tokens 96 --stable-word-limit 1500", runner)
        self.assertIn("--concurrency 2", runner)
        self.assertIn("--tool-slack-ms 6000 --slo-ms 1500", runner)
        self.assertIn('VLLM_CACHE_ROOT="$ROOT/cache/common-ruler/$cell/vllm"', runner)
        self.assertIn('TRITON_CACHE_DIR="$ROOT/cache/common-ruler/$cell/triton"', runner)

    def test_quality_boolean_parser_is_csv_stable(self):
        self.assertTrue(truth("True"))
        self.assertTrue(truth("1"))
        self.assertFalse(truth("False"))


if __name__ == "__main__":
    unittest.main()
