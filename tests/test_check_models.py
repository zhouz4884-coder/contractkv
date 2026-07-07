import tempfile
import unittest
from pathlib import Path

from scripts.check_models import collect_model_rows


class CheckModelsTests(unittest.TestCase):
    def test_marks_complete_model_with_tokenizer_config_weights_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "Qwen3-8B"
            model.mkdir()
            for name in [
                "config.json",
                "tokenizer.json",
                "generation_config.json",
                "model-00001-of-00001.safetensors",
                "model.safetensors.index.json",
            ]:
                (model / name).write_text("{}", encoding="utf-8")

            rows = collect_model_rows(root, ["Qwen3-8B"])

        self.assertEqual(rows[0]["model"], "Qwen3-8B")
        self.assertTrue(rows[0]["exists"])
        self.assertTrue(rows[0]["config"])
        self.assertTrue(rows[0]["tokenizer"])
        self.assertTrue(rows[0]["generation_config"])
        self.assertEqual(rows[0]["num_safetensors"], 1)
        self.assertTrue(rows[0]["has_index"])
        self.assertTrue(rows[0]["complete_for_phase"])

    def test_marks_incomplete_model_without_weights_as_not_blocking_when_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "Qwen3-14B"
            model.mkdir()
            for name in ["config.json", "tokenizer.json", "generation_config.json"]:
                (model / name).write_text("{}", encoding="utf-8")

            rows = collect_model_rows(root, ["Qwen3-14B"], optional_models={"Qwen3-14B"})

        self.assertFalse(rows[0]["complete_for_phase"])
        self.assertTrue(rows[0]["allowed_incomplete"])
        self.assertFalse(rows[0]["blocks_phase_0_2"])


if __name__ == "__main__":
    unittest.main()
