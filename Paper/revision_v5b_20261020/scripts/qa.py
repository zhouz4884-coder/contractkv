"""V5b entry point; baseline implementation is retained in the author audit."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('qa_v5b.py')),run_name="__main__")
