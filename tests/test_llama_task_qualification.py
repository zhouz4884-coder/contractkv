import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.freeze_llama_task_qualification import main


class LlamaTaskQualificationTest(unittest.TestCase):
    def test_only_all_passed_development_family_is_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); dev = root / "dev.jsonl"; held = root / "held.jsonl"
            rows = []
            for index in range(5):
                rows.append({"dataset": "RULER", "task": "niah", "certificate_issued": True,
                             "error_type": "none"})
                rows.append({"dataset": "LongBench", "task": "qasper",
                             "certificate_issued": index < 4, "error_type": "none"})
            dev.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            held.write_text("".join(json.dumps({"dataset": dataset, "task": task,
                                                  "phase19b_session_id": str(index)}) + "\n"
                                    for index, (dataset, task) in enumerate(
                                        [("RULER", "niah"), ("LongBench", "qasper")])), encoding="utf-8")
            manifest = root / "manifest.json"; qualified = root / "qualified.jsonl"
            argv = ["freeze", "--development", str(dev), "--heldout", str(held),
                    "--model-identity", "llama", "--manifest", str(manifest),
                    "--qualified-heldout", str(qualified)]
            with patch.object(sys, "argv", argv):
                self.assertEqual(main(), 0)
            frozen = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(frozen["qualified_task_families"], ["RULER:niah"])
            selected = [json.loads(line) for line in qualified.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["dataset"], "RULER")


if __name__ == "__main__":
    unittest.main()
