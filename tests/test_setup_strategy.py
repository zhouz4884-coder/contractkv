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

    def test_setup_keeps_conda_cache_on_large_disk_and_pins_cuda128_builds(self):
        script = Path("scripts/setup_contractkv_cu128.sh").read_text(encoding="utf-8")

        self.assertIn("CONTRACTKV_DISK_ROOT", script)
        self.assertIn("CONDA_PKGS_DIRS", script)
        self.assertIn("conda-pkgs/contractkv-cu128", script)
        self.assertIn("XDG_CACHE_HOME", script)
        self.assertIn("HF_HOME", script)
        self.assertIn("TORCH_HOME", script)
        self.assertIn("TRITON_CACHE_DIR", script)
        self.assertIn("VLLM_CACHE_ROOT", script)
        self.assertIn("--override-channels", script)
        self.assertIn("gpu_cuda128_py310", script)
        self.assertIn("cuda128py310", script)
        self.assertNotIn("cuda129", script)

    def test_setup_pins_transformers_to_vllm_compatible_four_x_line(self):
        script = Path("scripts/setup_contractkv_cu128.sh").read_text(encoding="utf-8")

        self.assertIn("transformers==4.55.2", script)
        self.assertNotIn("transformers==5", script)

    def test_run_vllm_keeps_runtime_caches_on_large_disk(self):
        script = Path("scripts/run_vllm_server.sh").read_text(encoding="utf-8")

        self.assertIn("CONTRACTKV_DISK_ROOT", script)
        self.assertIn("XDG_CACHE_HOME", script)
        self.assertIn("HF_HOME", script)
        self.assertIn("TORCH_HOME", script)
        self.assertIn("TRITON_CACHE_DIR", script)
        self.assertIn("VLLM_CACHE_ROOT", script)
        self.assertIn("contractkv-runtime", script)
        self.assertIn("export TMPDIR XDG_CACHE_HOME", script)

    def test_run_vllm_uses_short_tmpdir_for_zmq_ipc(self):
        script = Path("scripts/run_vllm_server.sh").read_text(encoding="utf-8")

        self.assertIn("RUNTIME_TMP_REAL", script)
        self.assertIn("RUNTIME_TMP_LINK", script)
        self.assertIn("/tmp/contractkv-runtime", script)
        self.assertIn("ln -s", script)


if __name__ == "__main__":
    unittest.main()
