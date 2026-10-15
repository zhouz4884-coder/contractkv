"""Use the same R1 client for the existing TP=2 model's full-cost audit."""
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_live as live

if __name__ == "__main__":
    live.FROZEN_LEVELS["Qwen3-14B"] = dict(live.FROZEN_LEVELS["Qwen3-8B"])
    raise SystemExit(live.main())
