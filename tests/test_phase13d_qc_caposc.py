import unittest

from scripts.phase12e_cache_aware_posc import SegmentPrefixLedger
from scripts.phase13d_qc_caposc_qasper import qc_compile


class QCCAPOSCTests(unittest.TestCase):
    def test_ordered_discourse_risk_falls_back_without_task_name(self):
        case = {
            "trajectory_id": "generic-doc", "turn_id": 0, "tool_slack_ms": 100,
            "segments": [
                {"segment_id": "s0", "segment_type": "SYS_PROMPT", "text": "system", "token_count": 1, "dependencies": [], "volatility": 0.0, "cache_stability": 1.0},
                {"segment_id": "s1", "segment_type": "TOOL_OBS", "text": "tool", "token_count": 1, "dependencies": ["s0"], "volatility": 1.0, "cache_stability": 0.0},
                {"segment_id": "s2", "segment_type": "RAG_CHUNK", "text": "Abstract\nIntroduction\nMethods\nResults", "token_count": 10, "dependencies": ["s0"], "volatility": 0.0, "cache_stability": 1.0},
                {"segment_id": "s3", "segment_type": "USER_QUERY", "text": "answer", "token_count": 1, "dependencies": ["s1", "s2"], "volatility": 1.0, "cache_stability": 0.0},
            ],
        }
        compiled = qc_compile(case, SegmentPrefixLedger(), epsilon=0.03)
        self.assertTrue(compiled["risk_fallback"])
        self.assertEqual(compiled["topological_order"], ["s0", "s1", "s2", "s3"])
        self.assertGreater(compiled["layout_risk_upper_bound"], 0.03)


if __name__ == "__main__":
    unittest.main()
