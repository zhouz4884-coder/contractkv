import unittest

from scripts.generate_actual_context_prompts import (
    within_token_tolerance,
    count_chat_template_tokens,
    build_prompt_record,
)


class FakeTokenizer:
    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        text = "".join(m["content"] for m in messages)
        tokens = text.split()
        if add_generation_prompt:
            tokens += ["<assistant>"]
        return tokens if tokenize else " ".join(tokens)


class ActualContextPromptsTests(unittest.TestCase):
    def test_token_tolerance_uses_relative_error(self):
        self.assertTrue(within_token_tolerance(actual=8176, target=8192, tolerance=0.03))
        self.assertFalse(within_token_tolerance(actual=7600, target=8192, tolerance=0.03))

    def test_counts_tokens_after_chat_template(self):
        tokenizer = FakeTokenizer()
        messages = [{"role": "user", "content": "alpha beta gamma"}]

        self.assertEqual(count_chat_template_tokens(tokenizer, messages), 4)

    def test_prompt_record_contains_required_metadata(self):
        tokenizer = FakeTokenizer()
        messages = [{"role": "user", "content": "alpha beta gamma delta"}]

        record = build_prompt_record(
            tokenizer=tokenizer,
            target_tokens=5,
            tolerance=0.03,
            prompt_source="synthetic_repeat",
            prompt_entropy_type="low_entropy_repeat",
            messages=messages,
            generation_max_tokens=128,
        )

        self.assertEqual(record["target_tokens"], 5)
        self.assertEqual(record["actual_prompt_tokens_after_chat_template"], 5)
        self.assertEqual(record["generation_max_tokens"], 128)
        self.assertEqual(record["prompt_source"], "synthetic_repeat")
        self.assertEqual(record["prompt_entropy_type"], "low_entropy_repeat")
        self.assertIn("prompt_text_preview", record)


if __name__ == "__main__":
    unittest.main()
