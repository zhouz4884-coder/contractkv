import json
import tempfile
import unittest
from pathlib import Path

from scripts.repair_submission_scope_telemetry import repair


class ScopeTelemetryRepairTests(unittest.TestCase):
    def test_repair_uses_executed_policy_without_changing_it(self):
        rows = [
            {"row_type": "future", "policy": "contractkv-full",
             "effective_policy": "physical-cache-aware", "certificate_issued": True,
             "certificate_scope_valid": False,
             "certificate_scope_errors": ["certificate_missing_or_unissued"],
             "ttft_ms": 12.0},
            {"row_type": "future", "policy": "contractkv-full",
             "effective_policy": "raw-order", "certificate_issued": False,
             "certificate_scope_valid": True, "certificate_scope_errors": [],
             "ttft_ms": 20.0},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            record = repair(path)
            result = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertTrue(result[0]["certificate_scope_valid"])
        self.assertFalse(result[1]["certificate_scope_valid"])
        self.assertEqual(result[0]["effective_policy"], "physical-cache-aware")
        self.assertEqual(result[0]["ttft_ms"], 12.0)
        self.assertEqual(record["executed_policy_rows_changed"], 0)


if __name__ == "__main__":
    unittest.main()
