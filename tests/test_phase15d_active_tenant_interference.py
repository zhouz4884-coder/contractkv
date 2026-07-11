import unittest

from scripts.phase15d_active_tenant_interference import add_penalty_summary, summarize


class Phase15DActiveTenantInterferenceTest(unittest.TestCase):
    def test_summarize_and_penalty(self) -> None:
        rows = [
            {
                "seed": 1,
                "condition": "baseline",
                "request_class": "active",
                "success": True,
                "ttft_ms": 10,
                "total_latency_ms": 20,
            },
            {
                "seed": 1,
                "condition": "baseline",
                "request_class": "active",
                "success": True,
                "ttft_ms": 20,
                "total_latency_ms": 30,
            },
            {
                "seed": 1,
                "condition": "shadow_interference",
                "request_class": "shadow",
                "success": True,
                "ttft_ms": 100,
                "total_latency_ms": 200,
            },
            {
                "seed": 1,
                "condition": "shadow_interference",
                "request_class": "active",
                "success": True,
                "ttft_ms": 30,
                "total_latency_ms": 40,
            },
            {
                "seed": 1,
                "condition": "shadow_interference",
                "request_class": "active",
                "success": True,
                "ttft_ms": 40,
                "total_latency_ms": 60,
            },
        ]
        summary = add_penalty_summary(summarize(rows))
        penalty = [row for row in summary if row["condition"] == "shadow_penalty_vs_baseline"][0]
        self.assertEqual(penalty["active_requests"], 2)
        self.assertEqual(penalty["shadow_requests"], 1)
        self.assertAlmostEqual(penalty["active_mean_ttft_ms"], 20.0)
        self.assertAlmostEqual(penalty["active_mean_latency_ms"], 25.0)


if __name__ == "__main__":
    unittest.main()
