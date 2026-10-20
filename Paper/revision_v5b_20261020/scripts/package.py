"""Clean V5b release entry point."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name("package_v5b.py")),run_name="__main__")
