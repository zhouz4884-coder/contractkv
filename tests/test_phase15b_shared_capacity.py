from __future__ import annotations

import unittest

from scripts.summarize_phase15b_shared_capacity import summarize


class Phase15BSharedCapacityTests(unittest.TestCase):
    def test_knee_requires_all_three_seeds_stable(self) -> None:
        rows = []
        for seed, stable in (("1", "True"), ("2", "True"), ("3", "False")):
            rows.append({
                "policy": "raw-order", "arrival_rate_rps": "1", "_seed": seed,
                "capacity_stable": stable, "completed_requests": "200", "min_second_half_samples_required": "100",
                "completion_rate": "1", "p95_ttft_ms": "100", "slo_compliant_req_per_sec": "1",
                "end_backlog": "0", "second_half_wait_slope_sec_per_sec": "0", "primer_latency_ms": "0",
                "cold_start_amortized_latency_ms": "1", "mean_observed_new_prefill_tokens": "2",
            })
        self.assertFalse(summarize(rows)[0]["all_seeds_stable"])


if __name__ == "__main__":
    unittest.main()
