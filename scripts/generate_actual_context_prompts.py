#!/usr/bin/env python3
"""Generate chat prompts with measured post-template token lengths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_TEXTS = {
    "synthetic_repeat": (
        "Agentic serving request segment. KV cache lifecycle reuse repair precision placement slack. "
    ),
    "ruler_haystack": (
        "One of the special magic numbers for blue-lantern is: 7391024. "
        "The haystack contains many neutral sentences about cities, weather, tasks, and notebooks. "
        "Remember the hidden key-value pair and answer only with the value when asked. "
    ),
    "longbench_hotpotqa": (
        "Passage 1: ContractKV studies long-context serving under memory pressure. "
        "Passage 2: LongBench-style tasks combine retrieved passages and a short user query. "
        "Question: Which system studies long-context serving under memory pressure? "
    ),
    "repobench_code": (
        "# Repo Name: contractkv\n# Path: scripts/cache.py\n"
        "class KVSegment:\n    def __init__(self, segment_type, text):\n"
        "        self.segment_type = segment_type\n        self.text = text\n\n"
        "# Path: service/scheduler.py\n"
        "def schedule(segment):\n    return segment.segment_type\n"
    ),
}


def count_chat_template_tokens(tokenizer: Any, messages: list[dict[str, str]]) -> int:
    return len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))


def within_token_tolerance(actual: int, target: int, tolerance: float) -> bool:
    if target <= 0:
        return False
    return abs(actual - target) / target <= tolerance


def build_prompt_record(
    tokenizer: Any,
    target_tokens: int,
    tolerance: float,
    prompt_source: str,
    prompt_entropy_type: str,
    messages: list[dict[str, str]],
    generation_max_tokens: int,
) -> dict[str, Any]:
    actual_tokens = count_chat_template_tokens(tokenizer, messages)
    if not within_token_tolerance(actual_tokens, target_tokens, tolerance):
        raise ValueError(
            f"actual_prompt_tokens_after_chat_template={actual_tokens} target={target_tokens} "
            f"tolerance={tolerance}"
        )
    preview = " ".join(message["content"] for message in messages)[:240]
    return {
        "id": f"{prompt_source}_{target_tokens}",
        "target_tokens": target_tokens,
        "actual_prompt_tokens_after_chat_template": actual_tokens,
        "tolerance": tolerance,
        "prompt_source": prompt_source,
        "prompt_entropy_type": prompt_entropy_type,
        "messages": messages,
        "prompt_text_preview": preview,
        "generation_max_tokens": generation_max_tokens,
    }


def _token_count(tokenizer: Any, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def _fit_text_to_target(tokenizer: Any, base_text: str, target_tokens: int, tolerance: float) -> str:
    overhead = count_chat_template_tokens(tokenizer, [{"role": "user", "content": ""}])
    content_target = max(1, target_tokens - overhead)
    base_ids = tokenizer.encode(base_text, add_special_tokens=False)
    if not base_ids:
        raise ValueError("base_text produced no tokenizer ids")
    search_margin = max(4096, int(target_tokens * 0.25))
    repeats = ((content_target + search_margin) // len(base_ids)) + 4
    repeated_ids = (base_ids * repeats)[: content_target + search_margin]

    best = tokenizer.decode(repeated_ids[:content_target])
    best_error = abs(count_chat_template_tokens(tokenizer, [{"role": "user", "content": best}]) - target_tokens)
    lower = max(1, content_target - search_margin)
    upper = min(len(repeated_ids), content_target + search_margin)

    lo, hi = lower, upper
    pivot = content_target
    for _ in range(24):
        mid = (lo + hi) // 2
        text = tokenizer.decode(repeated_ids[:mid])
        actual = count_chat_template_tokens(tokenizer, [{"role": "user", "content": text}])
        error = abs(actual - target_tokens)
        if error < best_error:
            best = text
            best_error = error
            pivot = mid
        if within_token_tolerance(actual, target_tokens, tolerance):
            return text
        if actual < target_tokens:
            lo = mid + 1
        else:
            hi = mid - 1

    scan_lower = max(lower, pivot - 512)
    scan_upper = min(upper, pivot + 512)
    for length in range(scan_lower, scan_upper + 1):
        text = tokenizer.decode(repeated_ids[:length])
        actual = count_chat_template_tokens(tokenizer, [{"role": "user", "content": text}])
        error = abs(actual - target_tokens)
        if error < best_error:
            best = text
            best_error = error
        if within_token_tolerance(actual, target_tokens, tolerance):
            return text
    return best


def load_dataset_source_texts(path: Path | None) -> dict[str, str]:
    texts = dict(DEFAULT_SOURCE_TEXTS)
    if path is None or not path.exists():
        return texts
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            sample = json.loads(line)
            dataset = sample.get("dataset", "")
            task = sample.get("task", "")
            combined = "\n".join(segment.get("text", "") for segment in sample.get("segments", []))
            if dataset == "LongBench" and task == "hotpotqa":
                texts["longbench_hotpotqa"] = combined or texts["longbench_hotpotqa"]
            elif dataset == "RepoBench":
                texts["repobench_code"] = combined or texts["repobench_code"]
            elif dataset == "RULER":
                texts["ruler_haystack"] = combined or texts["ruler_haystack"]
    return texts


def generate_records(
    tokenizer: Any,
    lengths: list[int],
    sources: list[str],
    tolerance: float,
    generation_max_tokens: int,
    source_texts: dict[str, str],
) -> list[dict[str, Any]]:
    entropy = {
        "synthetic_repeat": "low_entropy_repeat",
        "ruler_haystack": "synthetic_haystack",
        "longbench_hotpotqa": "real_text_qa",
        "repobench_code": "real_code",
    }
    records = []
    for source in sources:
        base = source_texts[source]
        for target in lengths:
            fitted = _fit_text_to_target(tokenizer, base, target, tolerance)
            messages = [{"role": "user", "content": fitted}]
            records.append(
                build_prompt_record(
                    tokenizer=tokenizer,
                    target_tokens=target,
                    tolerance=tolerance,
                    prompt_source=source,
                    prompt_entropy_type=entropy[source],
                    messages=messages,
                    generation_max_tokens=generation_max_tokens,
                )
            )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--lengths", default="4096,8192,16384,32768")
    parser.add_argument(
        "--sources",
        default="synthetic_repeat,ruler_haystack,longbench_hotpotqa,repobench_code",
    )
    parser.add_argument("--dataset-samples", default="results/datasets/sample_prompts.jsonl")
    parser.add_argument("--output", default="configs/qwen3_8b_actual_context_prompts.jsonl")
    parser.add_argument("--tolerance", type=float, default=0.03)
    parser.add_argument("--generation-max-tokens", type=int, default=128)
    args = parser.parse_args()

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    lengths = [int(item) for item in args.lengths.split(",") if item]
    sources = [item for item in args.sources.split(",") if item]
    source_texts = load_dataset_source_texts(Path(args.dataset_samples))
    records = generate_records(
        tokenizer=tokenizer,
        lengths=lengths,
        sources=sources,
        tolerance=args.tolerance,
        generation_max_tokens=args.generation_max_tokens,
        source_texts=source_texts,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} prompts to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
