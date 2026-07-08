import unittest

from scripts.prepare_dataset_samples import validate_sample_prompt


class SamplePromptSchemaTests(unittest.TestCase):
    def test_valid_sample_prompt_schema(self):
        sample = {
            "dataset": "LongBench",
            "task": "hotpotqa",
            "sample_id": "0",
            "total_prompt_tokens": 100,
            "segments": [
                {"type": "SYS_PROMPT", "text": "answer briefly", "token_count": 2},
                {"type": "RAG_CHUNK", "text": "alpha beta", "token_count": 2},
                {"type": "USER_QUERY", "text": "question", "token_count": 1},
            ],
            "answer": ["x"],
            "metadata": {"source_note": "LongBench loaded via HuggingFace THUDM/LongBench"},
        }

        validate_sample_prompt(sample, tolerance=3)

    def test_rejects_missing_segment_token_count(self):
        sample = {
            "dataset": "LongBench",
            "task": "hotpotqa",
            "sample_id": "0",
            "total_prompt_tokens": 100,
            "segments": [{"type": "SYS_PROMPT", "text": "answer briefly"}],
            "answer": "x",
            "metadata": {},
        }

        with self.assertRaises(ValueError):
            validate_sample_prompt(sample, tolerance=3)


if __name__ == "__main__":
    unittest.main()
