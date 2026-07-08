import json
import tempfile
import unittest
from pathlib import Path

from scripts.contractkv_decision_logger import DecisionLogger
from scripts.contractkv_policy_runtime import ContractKVRuntime
from scripts.contractkv_segment_parser import parse_chat_segments


class ContractKVRuntimeTests(unittest.TestCase):
    def test_parser_emits_segment_schema_from_chat_request(self):
        request = {
            "model": "qwen3-4b",
            "messages": [
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": "Context:\n" + ("alpha beta " * 40) + "\nQuestion: summarize."},
            ],
        }

        parsed = parse_chat_segments(request)

        self.assertEqual(parsed["dataset"], "runtime")
        self.assertTrue(parsed["segments"])
        self.assertTrue(all({"type", "text", "token_count"} <= set(s) for s in parsed["segments"]))
        self.assertGreater(parsed["total_prompt_tokens"], 0)

    def test_runtime_returns_decision_and_timing_breakdown(self):
        runtime = ContractKVRuntime(
            risk_summary_path=Path("results/risk_ledger/quality_risk_summary_v0.csv"),
            cost_table_path=Path("results/cost/segment_action_cost_table_v0.csv"),
            policy="ContractKV-Joint",
            quality_budget=0.02,
            slo_budget_ms=200,
        )
        request = {"model": "qwen3-4b", "messages": [{"role": "user", "content": "hello world"}]}

        decision, timings = runtime.decide(request)

        self.assertEqual(decision["policy"], "ContractKV-Joint")
        self.assertIn("segments", decision)
        self.assertIn("parse_ms", timings)
        self.assertIn("policy_ms", timings)
        self.assertGreaterEqual(timings["policy_ms"], 0)

    def test_decision_logger_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisions.jsonl"
            logger = DecisionLogger(path)
            logger.write({"request_id": "r0", "decision": {"admitted": True}})

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["request_id"], "r0")
            self.assertTrue(rows[0]["decision"]["admitted"])


if __name__ == "__main__":
    unittest.main()
