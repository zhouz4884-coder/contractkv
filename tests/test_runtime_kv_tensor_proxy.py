import unittest

from scripts.runtime_kv_tensor_proxy import estimate_stall_ms, run_proxy_case


class RuntimeKvTensorProxyTests(unittest.TestCase):
    def test_estimate_stall_hides_copy_inside_slack(self):
        self.assertEqual(estimate_stall_ms(copy_ms=10, slack_ms=20, mode="copy_in_tool_slack_window"), 0)
        self.assertEqual(estimate_stall_ms(copy_ms=25, slack_ms=20, mode="copy_in_tool_slack_window"), 5)
        self.assertEqual(estimate_stall_ms(copy_ms=10, slack_ms=20, mode="copy_on_critical_path"), 10)

    def test_proxy_case_has_required_fields(self):
        row = run_proxy_case(size_mb=128, mode="no_copy", repeat=1, device="cpu")

        for field in [
            "mode",
            "kv_size_mb",
            "copy_ms",
            "decode_like_compute_ms",
            "observed_latency_ms",
            "estimated_stall_ms",
            "error_type",
        ]:
            self.assertIn(field, row)
        self.assertEqual(row["mode"], "no_copy")
        self.assertEqual(row["error_type"], "none")


if __name__ == "__main__":
    unittest.main()
