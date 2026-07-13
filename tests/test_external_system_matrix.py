import tempfile
import unittest
from pathlib import Path

from scripts.summarize_external_system_matrix import FIELDS, parse_sglang_log


class ExternalSystemMatrixTests(unittest.TestCase):
    def test_matrix_keeps_block_metric_unavailability_explicit(self):
        self.assertIn("peak_kv_blocks", FIELDS)
        self.assertIn("claim_boundary", FIELDS)

    def test_sglang_log_parser_uses_backend_counters_not_ttft_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server.log"
            path.write_text(
                "KV Cache is allocated. #tokens: 1000\n"
                "Prefill batch. #new-token: 80, #cached-token: 20, token usage: 0.25\n"
                "Prefill batch. #new-token: 40, #cached-token: 10, token usage: 0.50\n",
                encoding="utf-8")
            row = parse_sglang_log(path)
            self.assertEqual(row["total_cached_tokens"], 30)
            self.assertEqual(row["total_new_prefill_tokens"], 120)
            self.assertEqual(row["peak_kv_token_slots"], 500)


if __name__ == "__main__":
    unittest.main()
