#!/usr/bin/env python3
"""Install the Phase 26R terminal-stop robustness guard in compact vLLM."""

from __future__ import annotations

import argparse
from pathlib import Path


PATCH_MARKER = "CONTRACTKV_PHASE26R_STOP_MARGIN_V1"
CACHE_SALT_MARKER = "CONTRACTKV_PHASE26R_OBSERVATION_SALT_V1"


def replace_once(text: str, old: str, new: str, path: Path) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one patch anchor in {path}, found {count}")
    return text.replace(old, new, 1)


def patch_engine(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        return
    old = '    degradation_q95: float = float("nan")\n'
    new = old + f'    terminal_stop_margin: float = float("nan")  # {PATCH_MARKER}\n'
    path.write_text(replace_once(text, old, new, path), encoding="utf-8")


def patch_api(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER not in text:
        old = '''        "degradation_q95": (result.degradation_q95
                            if math.isfinite(result.degradation_q95) else None),
'''
        new = old + f'''        "terminal_stop_margin": (result.terminal_stop_margin
                                 if math.isfinite(result.terminal_stop_margin)
                                 else None),  # {PATCH_MARKER}
'''
        text = replace_once(text, old, new, path)
    if CACHE_SALT_MARKER not in text:
        text = replace_once(
            text,
            '    timeout_s: float = 300.0\n\n\nclass PrometheusResponse',
            f'    timeout_s: float = 300.0\n'
            f'    cache_salt: str | None = None  # {CACHE_SALT_MARKER}\n\n\n'
            'class PrometheusResponse',
            path,
        )
        text = replace_once(
            text,
            '''        verify_spec=spec,
        timeout_s=payload.timeout_s,
    )
''',
            '''        verify_spec=spec,
        timeout_s=payload.timeout_s,
        cache_salt=payload.cache_salt,
    )
''',
            path,
        )
    path.write_text(text, encoding="utf-8")


def patch_scheduler(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        return
    text = replace_once(
        text,
        '        degradation_q95 = float("nan")\n        certificate_hash = ""\n',
        '        degradation_q95 = float("nan")\n'
        f'        terminal_stop_margin = float("nan")  # {PATCH_MARKER}\n'
        '        certificate_hash = ""\n',
        path,
    )
    text = replace_once(
        text,
        '''            stop_ids = [int(value)
                        for value in lists.logprob_token_ids[stop_row]]
            stop_ok = stop_rank == 1 and spec.terminal_stop_token_id in stop_ids
''',
        '''            stop_ids = [int(value)
                        for value in lists.logprob_token_ids[stop_row]]
            stop_values = [float(value)
                           for value in lists.logprobs[stop_row]]
            stop_targets = [value for token_id, value in zip(
                stop_ids, stop_values)
                            if token_id == spec.terminal_stop_token_id]
            stop_competitors = [value for token_id, value in zip(
                stop_ids, stop_values)
                                if token_id != spec.terminal_stop_token_id]
            if not stop_targets or not stop_competitors:
                raise ValueError("terminal_stop_target_or_competitor_unavailable")
            terminal_stop_margin = stop_targets[0] - max(stop_competitors)
            stop_ok = stop_rank == 1 and spec.terminal_stop_token_id in stop_ids
''',
        path,
    )
    text = replace_once(
        text,
        '''            max_degradation = float(os.environ.get(
                "CONTRACTKV_MAX_DEGRADATION", "4.0"))
            if (all(rank == 1 for rank in candidate_ranks) and stop_ok
                    and candidate_q05 >= min_margin
                    and degradation_q95 <= max_degradation):
''',
        '''            max_degradation = float(os.environ.get(
                "CONTRACTKV_MAX_DEGRADATION", "4.0"))
            min_stop_margin = float(os.environ.get(
                "CONTRACTKV_MIN_STOP_MARGIN", "-inf"))
            if (all(rank == 1 for rank in candidate_ranks) and stop_ok
                    and candidate_q05 >= min_margin
                    and degradation_q95 <= max_degradation
                    and terminal_stop_margin >= min_stop_margin):
''',
        path,
    )
    text = replace_once(
        text,
        '            degradation_q95=degradation_q95,\n        )\n',
        '            degradation_q95=degradation_q95,\n'
        '            terminal_stop_margin=terminal_stop_margin,\n        )\n',
        path,
    )
    path.write_text(text, encoding="utf-8")


def patch_async_llm(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if CACHE_SALT_MARKER in text:
        return
    text = replace_once(
        text,
        '''        verify_spec: ContractKVVerifySpec,
        timeout_s: float = 300.0,
    ) -> ContractKVCompactResult:
''',
        '''        verify_spec: ContractKVVerifySpec,
        timeout_s: float = 300.0,
        cache_salt: str | None = None,
    ) -> ContractKVCompactResult:
''',
        path,
    )
    text = replace_once(
        text,
        '            prompt={"prompt_token_ids": prompt_token_ids},\n',
        '            prompt={"prompt_token_ids": prompt_token_ids,\n'
        f'                    "cache_salt": cache_salt}},  # {CACHE_SALT_MARKER}\n',
        path,
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    patch_engine(args.source_root / "vllm/v1/engine/__init__.py")
    patch_api(args.source_root / "vllm/entrypoints/openai/api_server.py")
    patch_scheduler(args.source_root / "vllm/v1/core/sched/scheduler.py")
    patch_async_llm(args.source_root / "vllm/v1/engine/async_llm.py")
    print(f"installed {PATCH_MARKER} in {args.source_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
