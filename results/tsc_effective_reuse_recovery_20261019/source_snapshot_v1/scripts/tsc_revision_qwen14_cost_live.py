"""Use the same R1 client for the existing TP=2 model's full-cost audit."""
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_live as live

if __name__ == "__main__":
    live.FROZEN_LEVELS["Qwen3-14B"] = dict(live.FROZEN_LEVELS["Qwen3-8B"])
    arguments = list(sys.argv)
    result = live.main()
    policy = arguments[arguments.index("--policy") + 1]
    output = Path(arguments[arguments.index("--output") + 1])
    guard_output = output.parents[2] / "guard_probe_qwen14_actual_v2.jsonl"
    if result == 0 and policy == "contractkv" and not guard_output.exists():
        from scripts.tsc_revision_guard_probe import main as guard_main
        sys.argv = ["guard-probe", "--base-url", arguments[arguments.index("--base-url") + 1],
                    "--model", arguments[arguments.index("--model") + 1], "--policy-hash",
                    arguments[arguments.index("--policy-hash") + 1], "--actual-routing", "--output", str(guard_output)]
        result = guard_main()
    raise SystemExit(result)
