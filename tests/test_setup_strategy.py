import unittest
from pathlib import Path


class SetupStrategyTests(unittest.TestCase):
    def test_setup_uses_conda_first_and_avoids_pytorch_pip_index(self):
        script = Path("scripts/setup_contractkv_cu128.sh").read_text(encoding="utf-8")
        conda_pos = script.find("conda install")
        pip_pos = script.find("python -m pip install")

        self.assertNotEqual(conda_pos, -1)
        self.assertNotEqual(pip_pos, -1)
        self.assertLess(conda_pos, pip_pos)
        self.assertNotIn("download.pytorch.org/whl/cu128", script)
        self.assertIn("pytorch=2.8", script)
        self.assertIn("triton=3.4", script)


if __name__ == "__main__":
    unittest.main()
