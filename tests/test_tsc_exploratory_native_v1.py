from collections import deque
from types import SimpleNamespace as NS
import os
import unittest
from unittest.mock import patch
from scripts.tsc_exploratory_native_v1 import MODE, allocate, fused_rows, actual_fields


class Queue:
    def __init__(self, blocks): self.q = deque(blocks)
    def popleft(self): return self.q.popleft()
    def append(self, x): self.q.append(x)
    def popleft_n(self, n): return [self.q.popleft() for _ in range(n)]


def request(ids=(3, 4), status="FINISHED_STOPPED"):
    spec = NS(attestation_mode=MODE, reference_answer_ids=[3], terminal_stop_token_id=4, verify_start_token=10)
    return NS(contractkv_verify_spec=spec, status=NS(name=status), request_id="unit", prompt_token_ids=[1]*10,
              _exploratory_decode=[dict(token_id=x, top_ids=[x, 9], logprobs=[-.1, -.8], rank=1) for x in ids])


class Hooks(unittest.TestCase):
    def test_actual_decode_indices_and_eos(self):
        r = request()
        rows = fused_rows(r).tolists()
        self.assertEqual(rows.logprob_token_ids[9], [3, 9])
        self.assertEqual(rows.logprob_token_ids[10], [4, 9])
        self.assertEqual(actual_fields(r)["fused_output_ids"], [3, 4])
        with self.assertRaises(IndexError): _ = rows.logprobs[8]

    def test_different_actual_path_fails_closed(self):
        with self.assertRaises(ValueError): fused_rows(request((8, 4)))

    def test_incomplete_and_length_fail_closed(self):
        for r in (request((3,)), request(status="FINISHED_LENGTH_CAPPED")):
            with self.assertRaises(ValueError): fused_rows(r)

    def pool(self):
        blocks = [NS(block_hash=x, ref_cnt=0) for x in ("a", "b", "c")]
        pool = NS(num_gpu_blocks=4, free_block_queue=Queue(blocks))
        pool.get_num_free_blocks = lambda: len(pool.free_block_queue.q)
        return pool, blocks

    def test_no_priority_keeps_allocation_order(self):
        pool, blocks = self.pool()
        self.assertEqual(allocate(pool, 2), blocks[:2])
        self.assertTrue(all(b.ref_cnt == 0 for b in blocks))

    def test_priority_is_revocable_without_refcount_pinning(self):
        pool, blocks = self.pool()
        from collections import OrderedDict
        import time
        pool._exploratory_priority = OrderedDict(g=dict(hashes={"a"}, expires=time.monotonic()+5))
        self.assertEqual([b.block_hash for b in allocate(pool, 2)], ["b", "c"])
        self.assertEqual([b.block_hash for b in allocate(pool, 1)], ["a"])
        self.assertTrue(all(b.ref_cnt == 0 for b in blocks))

    def test_expired_priority_does_not_change_order(self):
        pool, blocks = self.pool()
        from collections import OrderedDict
        pool._exploratory_priority = OrderedDict(g=dict(hashes={"a"}, expires=0))
        self.assertEqual(allocate(pool, 1), blocks[:1])


if __name__ == "__main__": unittest.main()
