import unittest

from scripts.phase14a_agent_trace_census import FAMILIES, build_traces, census, summarize


class Phase14ACensusTests(unittest.TestCase):
    def test_trace_builder_produces_five_families_with_100_turns_each(self):
        samples = [
            {"dataset": "RepoBench", "task": "python_repository_completion", "sample_id": str(i), "segments": [{"type": "SYS_PROMPT", "text": "s", "token_count": 1}, {"type": "REPO_CONTEXT", "text": "c", "token_count": 2}, {"type": "USER_QUERY", "text": "q", "token_count": 1}]}
            for i in range(20)
        ] + [
            {"dataset": "LongBench", "task": task, "sample_id": str(i), "segments": [{"type": "SYS_PROMPT", "text": "s", "token_count": 1}, {"type": "RAG_CHUNK", "text": "This paper we propose a method. Introduction Results", "token_count": 2}, {"type": "USER_QUERY", "text": "q", "token_count": 1}]}
            for task in ["hotpotqa", "qasper"] for i in range(20)
        ]
        traces = build_traces(samples, turns_per_trace=5)
        summary = summarize(census(traces))
        self.assertEqual(len(traces), 500)
        self.assertEqual({row["workload_family"] for row in summary}, set(FAMILIES))
        self.assertTrue(all(int(row["turns"]) == 100 for row in summary))

    def test_code_family_is_risk_fallback_when_tool_precedes_repo(self):
        samples = [
            {"dataset": "RepoBench", "task": "python_repository_completion", "sample_id": str(i), "segments": [{"type": "SYS_PROMPT", "text": "s", "token_count": 1}, {"type": "REPO_CONTEXT", "text": "c", "token_count": 2}, {"type": "USER_QUERY", "text": "q", "token_count": 1}]}
            for i in range(20)
        ] + [
            {"dataset": "LongBench", "task": task, "sample_id": str(i), "segments": [{"type": "SYS_PROMPT", "text": "s", "token_count": 1}, {"type": "RAG_CHUNK", "text": "paper", "token_count": 2}, {"type": "USER_QUERY", "text": "q", "token_count": 1}]}
            for task in ["hotpotqa", "qasper"] for i in range(20)
        ]
        code_rows = [row for row in census(build_traces(samples, 5)) if row["workload_family"] == "code_agent"]
        self.assertTrue(all(bool(row["raw_fallback"]) for row in code_rows) is False)
        self.assertTrue(all(bool(row["hard_order_sensitive"]) for row in code_rows))


if __name__ == "__main__":
    unittest.main()
