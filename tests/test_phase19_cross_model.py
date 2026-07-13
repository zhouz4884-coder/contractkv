import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Phase19CrossModelTests(unittest.TestCase):
    def test_quality_labels_and_policy_hash_bind_calibration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            replay = temp / "replay.jsonl"
            rows = []
            for session, candidate_score, certificate in (("safe", 1.0, True), ("unsafe", 0.0, True)):
                for policy, score, prefill in (
                    ("raw-order", 1.0, 100.0),
                    ("physical-cache-aware", candidate_score, 10.0),
                    ("contractkv-full", 1.0 if not certificate else candidate_score, 50.0),
                ):
                    rows.append({
                        "row_type": "future", "policy": policy, "success": True,
                        "session_id": session, "turn_id": 1, "dataset": "RULER",
                        "task": "niah", "sample_id": session, "task_score": score,
                        "new_prefill_tokens": prefill,
                        "certificate_issued": certificate if policy == "contractkv-full" else "",
                    })
            replay.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            labels = temp / "labels.csv"; summary = temp / "summary.json"
            subprocess.run([
                sys.executable, str(ROOT / "scripts/phase19c_freeze_quality_labels.py"),
                "--inputs", str(replay), "--policy-hash", "draft",
                "--output-csv", str(labels), "--output-json", str(summary),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            frozen = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(frozen["safe_sessions"], 1)
            self.assertEqual(frozen["unsafe_sessions"], 1)
            self.assertEqual(frozen["unsafe_certified"], 1)

            draft = temp / "draft.json"; policy = temp / "policy.json"
            draft.write_text(json.dumps({"schema_version": "draft", "policy_hash": "old"}), encoding="utf-8")
            subprocess.run([
                sys.executable, str(ROOT / "scripts/phase19c_finalize_model_policy.py"),
                "--draft", str(draft), "--calibration-labels", str(labels),
                "--calibration-summary", str(summary), "--output", str(policy),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            first = json.loads(policy.read_text(encoding="utf-8"))["policy_hash"]
            with labels.open("a", encoding="utf-8") as handle:
                handle.write("changed\n")
            subprocess.run([
                sys.executable, str(ROOT / "scripts/phase19c_finalize_model_policy.py"),
                "--draft", str(draft), "--calibration-labels", str(labels),
                "--calibration-summary", str(summary), "--output", str(policy),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            second = json.loads(policy.read_text(encoding="utf-8"))["policy_hash"]
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
