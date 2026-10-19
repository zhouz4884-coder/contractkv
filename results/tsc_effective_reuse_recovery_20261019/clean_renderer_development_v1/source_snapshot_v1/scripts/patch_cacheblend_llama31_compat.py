#!/usr/bin/env python3
"""Backport Llama-3 RoPE support into the vLLM 0.4.1 CacheBlend fork."""

from __future__ import annotations

import argparse
from pathlib import Path


CLASS_MARKER = "class Llama3RotaryEmbedding(RotaryEmbedding):"
CLASS_SOURCE = r'''

class Llama3RotaryEmbedding(RotaryEmbedding):
    """Llama-3.1 RoPE frequency scaling backported from vLLM 0.10.2."""

    def __init__(
        self,
        head_size: int,
        rotary_dim: int,
        max_position_embeddings: int,
        base: int,
        is_neox_style: bool,
        scaling_factor: float,
        low_freq_factor: float,
        high_freq_factor: float,
        original_max_position: int,
    ) -> None:
        self.scaling_factor = scaling_factor
        self.low_freq_factor = low_freq_factor
        self.high_freq_factor = high_freq_factor
        self.original_max_position = original_max_position
        super().__init__(head_size, rotary_dim, max_position_embeddings, base,
                         is_neox_style)

    def _compute_inv_freq(self, base: Union[int, float]) -> torch.Tensor:
        inv_freqs = super()._compute_inv_freq(base)
        low_freq_wavelen = self.original_max_position / self.low_freq_factor
        high_freq_wavelen = self.original_max_position / self.high_freq_factor
        wave_len = 2 * math.pi / inv_freqs
        smooth = ((self.original_max_position / wave_len - self.low_freq_factor)
                  / (self.high_freq_factor - self.low_freq_factor))
        return torch.where(
            wave_len < high_freq_wavelen,
            inv_freqs,
            torch.where(
                wave_len > low_freq_wavelen,
                inv_freqs / self.scaling_factor,
                (1 - smooth) * inv_freqs / self.scaling_factor
                + smooth * inv_freqs,
            ),
        )
'''


def patch_rotary(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    if CLASS_MARKER not in text:
        anchor = "\n\nclass LinearScalingRotaryEmbedding(RotaryEmbedding):"
        if anchor not in text:
            raise RuntimeError("rotary class insertion anchor not found")
        text = text.replace(anchor, CLASS_SOURCE + anchor, 1)
        changed = True
    old = '        scaling_type = rope_scaling["type"]\n        scaling_factor = rope_scaling["factor"]'
    new = ('        scaling_type = rope_scaling.get("type", rope_scaling.get("rope_type"))\n'
           '        scaling_factor = rope_scaling["factor"]')
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
    branch_anchor = '        if scaling_type == "linear":\n'
    llama_branch = (
        '        if scaling_type == "llama3":\n'
        '            rotary_emb = Llama3RotaryEmbedding(\n'
        '                head_size, rotary_dim, max_position, base, is_neox_style,\n'
        '                scaling_factor, rope_scaling["low_freq_factor"],\n'
        '                rope_scaling["high_freq_factor"],\n'
        '                rope_scaling["original_max_position_embeddings"])\n'
        '        elif scaling_type == "linear":\n'
    )
    if llama_branch not in text:
        if branch_anchor not in text:
            raise RuntimeError("rotary dispatch anchor not found")
        text = text.replace(branch_anchor, llama_branch, 1)
        changed = True
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def patch_config(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    old = '        if rope_scaling["type"] == "yarn":\n'
    new = ('        scaling_type = rope_scaling.get("type", rope_scaling.get("rope_type"))\n'
           '        if scaling_type == "yarn":\n')
    if old not in text:
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vllm-root", type=Path, required=True)
    args = parser.parse_args()
    rotary = args.vllm_root / "model_executor/layers/rotary_embedding.py"
    config = args.vllm_root / "config.py"
    print({"rotary_changed": patch_rotary(rotary),
           "config_changed": patch_config(config)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
