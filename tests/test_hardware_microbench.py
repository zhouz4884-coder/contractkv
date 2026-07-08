import unittest

from scripts.bench_transfer_microbench import (
    parse_block_sizes,
    bandwidth_gbps,
    slowdown_percent,
)


class HardwareMicrobenchTests(unittest.TestCase):
    def test_parse_block_sizes(self):
        self.assertEqual(parse_block_sizes("1,4,16"), [1, 4, 16])

    def test_bandwidth_formula_uses_binary_megabytes_and_decimal_gbps(self):
        self.assertAlmostEqual(bandwidth_gbps(block_mb=1024, milliseconds=1000), 1.074, places=3)

    def test_slowdown_percent(self):
        self.assertEqual(slowdown_percent(without_copy_ms=20, with_copy_ms=25), 25.0)
        self.assertEqual(slowdown_percent(without_copy_ms=0, with_copy_ms=25), "")


if __name__ == "__main__":
    unittest.main()
