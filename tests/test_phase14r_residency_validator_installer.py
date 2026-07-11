from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.install_vllm_v1_residency_validator import install, uninstall


SCHEDULER = '''from x import y

class Scheduler:
    def schedule(self):
        if request.num_computed_tokens == 0:
                    new_computed_blocks, num_new_local_computed_tokens = \\
                        self.kv_cache_manager.get_computed_blocks(
                            request)
        self._update_after_schedule(scheduler_output)
'''


class ResidencyValidatorInstallerTest(unittest.TestCase):
    def test_install_and_uninstall_are_reversible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduler.py"
            path.write_text(SCHEDULER, encoding="utf-8")
            self.assertEqual(install(path), "installed")
            installed = path.read_text(encoding="utf-8")
            self.assertIn("prefix_residency_validation", installed)
            self.assertEqual(install(path), "already_installed")
            self.assertEqual(uninstall(path), "uninstalled")
            restored = path.read_text(encoding="utf-8")
            self.assertNotIn("CONTRACTKV_RESIDENCY", restored)
            self.assertIn("get_computed_blocks", restored)


if __name__ == "__main__":
    unittest.main()
