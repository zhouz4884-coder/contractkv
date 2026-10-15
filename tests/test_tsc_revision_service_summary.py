import json
from pathlib import Path
import tempfile
import unittest

from scripts.tsc_revision_service_summary import summarize


class ServiceSummaryTests(unittest.TestCase):
    def build(self, root, http_calls, guard_calls=0):
        name = "zero-slack_qwen_r1_D2-template-contractkv"
        directory = root / "service" / name; directory.mkdir(parents=True)
        rows = [dict(session_id="s" + str(i // 9), turn_id=i % 9 + 1) for i in range(180)]
        (directory / "raw.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (directory / "registration.jsonl").write_text(json.dumps(dict(registration_ms=10)) + "\n")
        (directory / "summary.jsonl").write_text(json.dumps(dict(actual_verifier_endpoint_calls=1)) + "\n")
        logs = root / "logs"; logs.mkdir()
        (logs / (name + "_server.log")).write_text('"POST /v1/contractkv/verify HTTP/1.1" 200 OK\n' * http_calls)
        if guard_calls:
            (root / "guard_probe_qwen_v1.jsonl").write_text('{}\n' * guard_calls)
        return logs

    def test_planned_attempt_is_not_an_actual_rpc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); logs = self.build(root, 0)
            records, _, _, _ = summarize(root, logs)
            self.assertEqual(records[0]["planned_same_engine_verification_attempts"], 1)
            self.assertEqual(records[0]["verifier_http_calls_from_server_log"], 0)
            self.assertNotIn("actual_verifier_endpoint_calls", records[0])

    def test_guard_probe_rpcs_are_excluded_from_service_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); logs = self.build(root, 24, 20)
            records, _, _, _ = summarize(root, logs)
            self.assertEqual(records[0]["verifier_http_calls_whole_server_process"], 24)
            self.assertEqual(records[0]["guard_probe_calls_excluded"], 20)
            self.assertEqual(records[0]["verifier_http_calls_from_server_log"], 4)


if __name__ == "__main__": unittest.main()
