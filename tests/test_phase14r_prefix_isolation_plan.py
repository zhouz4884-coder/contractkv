import unittest

from scripts.phase14r_prefix_isolation_plan import build_plan


class Phase14RPrefixIsolationPlanTests(unittest.TestCase):
    def test_plan_requires_fresh_server_and_cache_for_each_policy_run(self):
        rows = build_plan(["raw-order", "static-posc", "cache-aware-posc"], repeats=2, seed=14014, metrics_dir="/tmp/m")
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["requires_fresh_server"] == "true" for row in rows))
        self.assertTrue(all(row["requires_fresh_prefix_cache"] == "true" for row in rows))
        self.assertEqual({row["policy"] for row in rows}, {"raw-order", "static-posc", "cache-aware-posc"})


if __name__ == "__main__":
    unittest.main()
