# Physical Prefix Deduplication

| Agents | Same-snapshot dedup blocks | Dedup KV GiB | Initial alloc raw/Contract | Peak used raw/Contract | Peak-used KV GiB saved | TTFT reduction | Refcount match | OOM-free lower bound |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 2309.00 | 5.07 | 259.00/3.00 | 1284.00/288.00 | 2.19 | 96.48% | 100.00% | >=20 |
| 20 | 4878.00 | 10.72 | 259.00/3.00 | 1386.00/318.00 | 2.35 | 96.95% | 100.00% | >=20 |

The primary dedup value is measured in one scheduler snapshot as logical shared references minus unique physical block IDs, net of the raw-order cell. Block-pool high-water supplies an independent peak check. Qwen's actual GQA geometry and float16 block size convert blocks to bytes. Cross-lifecycle block-ID reuse is diagnostic only, and new-prefill reduction is never used as a memory proxy.
