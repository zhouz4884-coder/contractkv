from __future__ import annotations
import unittest
from scripts.phase14d_full_pool_builder import partition
class FullPoolPartitionTests(unittest.TestCase):
 def test_partition_is_deterministic_and_valid(self):
  got=[partition('LongBench','hotpotqa',str(i)) for i in range(200)]
  self.assertEqual(got,[partition('LongBench','hotpotqa',str(i)) for i in range(200)])
  self.assertEqual(set(got),{'calibration','held_out_quality','live_serving'})
if __name__=='__main__':unittest.main()
