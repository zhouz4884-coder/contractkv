import unittest

from scripts.phase13b_fresh_policy_quality_replay import POLICIES, build_case, _compile
from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger


class Phase13BFreshPolicyReplayTests(unittest.TestCase):
    def test_repobench_code_context_is_an_ordered_supernode(self):
        sample = {
            "dataset": "RepoBench",
            "task": "python_repository_completion",
            "sample_id": "0",
            "answer": "target",
            "segments": [
                {"type": "SYS_PROMPT", "text": "system", "token_count": 1},
                {"type": "REPO_IMPORT", "text": "import", "token_count": 1},
                {"type": "REPO_CLASS", "text": "class", "token_count": 1},
                {"type": "USER_QUERY", "text": "complete", "token_count": 1},
            ],
        }
        case = build_case(sample)
        raw = _compile("raw-order", case, SegmentPrefixLedger())["topological_order"]
        caposc = _compile("contractkv-caposc", case, SegmentPrefixLedger())["topological_order"]
        self.assertEqual(raw, caposc)

    def test_fresh_policy_set_is_explicit(self):
        self.assertEqual(POLICIES, ["raw-order", "canonical-all", "static-posc", "contractkv-caposc"])


if __name__ == "__main__":
    unittest.main()
