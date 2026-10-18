#!/usr/bin/env python3
"""Limit FlashInfer's top-level import to the sparse API required by LMCache.

FlashInfer 0.6 imports unrelated sampling kernels from ``__init__``.  On hosts
whose driver supports CUDA 12 but whose system toolkit is older, that eager
import attempts an unnecessary JIT build before LMCache reaches its sparse
attention backend.  This reversible compatibility patch keeps the actual
``VariableBlockSparseAttentionWrapper`` implementation unchanged.
"""

from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "# CONTRACTKV_FLASHINFER_SPARSE_IMPORT_V1"
MINIMAL_INIT = f'''{MARKER}
"""Sparse-only FlashInfer surface for the LMCache CacheBlend experiment."""

from .version import __git_version__, __version__
from .sparse import BlockSparseAttentionWrapper, VariableBlockSparseAttentionWrapper

__all__ = [
    "BlockSparseAttentionWrapper",
    "VariableBlockSparseAttentionWrapper",
    "__git_version__",
    "__version__",
]
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", type=Path, required=True)
    parser.add_argument("--action", choices=("install", "remove", "status"), required=True)
    args = parser.parse_args()
    backup = args.init.with_suffix(".py.contractkv-original")

    current = args.init.read_text(encoding="utf-8")
    installed = MARKER in current
    if args.action == "status":
        print("installed" if installed else "not-installed")
        return 0
    if args.action == "install":
        if not installed:
            if not backup.exists():
                backup.write_text(current, encoding="utf-8")
            args.init.write_text(MINIMAL_INIT, encoding="utf-8")
        print("installed")
        return 0
    if not backup.exists():
        raise FileNotFoundError(f"missing backup: {backup}")
    args.init.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    print("removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
