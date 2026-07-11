from __future__ import annotations

import unittest

from scripts.phase15c_cache_churn import candidate_hashes


class Phase15CCacheChurnTests(unittest.TestCase):
    def test_candidate_hashes_uses_latest_nonempty_native_observation(self) -> None:
        events = [
            {"event": "prefix_cache_request_observation", "request_id": "r", "physical_block_hashes": ["a"]},
            {"event": "prefix_cache_request_observation", "request_id": "other", "physical_block_hashes": ["x"]},
            {"event": "prefix_cache_request_observation", "request_id": "r", "physical_block_hashes": ["a", "b", None]},
        ]
        self.assertEqual(candidate_hashes(events, "r"), ["a", "b"])

    def test_candidate_hashes_fails_closed_when_unavailable(self) -> None:
        self.assertEqual(candidate_hashes([], "missing"), [])


if __name__ == "__main__":
    unittest.main()
