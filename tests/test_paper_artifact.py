import tempfile
import unittest
from pathlib import Path

from scripts.build_paper_artifact import CORE_FILES, GENERATED_FILES, ROOT


class PaperArtifactTest(unittest.TestCase):
    def test_core_allowlist_exists(self):
        missing = [path for path in CORE_FILES if not (ROOT / path).is_file()]
        self.assertEqual(missing, [])

    def test_generated_allowlist_has_no_raw_logs(self):
        text = "\n".join(GENERATED_FILES)
        self.assertNotIn("logs/", text)
        self.assertNotIn("_raw.jsonl", text)
        self.assertNotIn("models/", text)

    def test_artifact_readme_is_generated_not_copied(self):
        self.assertNotIn("README.md", CORE_FILES)


if __name__ == "__main__":
    unittest.main()
