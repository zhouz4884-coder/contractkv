"""Check the frozen supplementary TP2 inputs without loading model weights."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_live as live


def main():
    p = argparse.ArgumentParser(); p.add_argument("--sessions", type=Path, required=True)
    p.add_argument("--protocol", type=Path, required=True); p.add_argument("--tokenizer", required=True)
    p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(a.tokenizer, local_files_only=True)
    live.FROZEN_LEVELS["Qwen3-14B"] = dict(live.FROZEN_LEVELS["Qwen3-8B"])
    args = SimpleNamespace(protocol=json.loads(a.protocol.read_text()), experiment="free-generation", model_identity="Qwen3-14B")
    rows = live.read_jsonl(a.sessions); lengths = []
    for sample in rows:
        for turn in range(10):
            _, _, _, raw, candidate = live.make_turn(args, sample, turn)
            lengths.extend(len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
                           for messages in (raw, candidate))
    report = {"schema_version": "tsc-revision-qwen14-preflight.v1", "sessions": len(rows),
              "rendered_prompts_checked": len(lengths), "max_prompt_tokens": max(lengths),
              "output_budget": 96, "model_max_len": 8192, "all_prompts_fit": max(lengths) + 96 <= 8192,
              "input_sha256": hashlib.sha256(a.sessions.read_bytes()).hexdigest(),
              "evidence_type": "Frozen tokenizer-only capacity preflight, not GPU performance"}
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["all_prompts_fit"] and len(rows) == 25 else 2


if __name__ == "__main__": raise SystemExit(main())
