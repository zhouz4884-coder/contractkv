import unittest

from scripts.phase16a_microchunk_scheduler import PolicyConfig, simulate_policy, summarize
from scripts.phase16b_ephemeral_kv_transaction import BlockPool
from scripts.phase16d_drift_budget_lifecycle import (
    Certificate,
    TurnEvidence,
    hard_invalidated,
    jaccard_distance,
    wilson_upper,
)


class Phase16MicroChunkSchedulerTests(unittest.TestCase):
    def test_idle_microchunk_bounds_penalty_better_than_naive_shadow(self) -> None:
        naive = simulate_policy(16001, PolicyConfig("naive-ordinary-shadow", 4096, False, True), 2000, 40, 1000, 4096, 3)
        idle = simulate_policy(16001, PolicyConfig("IDLE_ONLY-16", 16, True), 2000, 40, 1000, 4096, 3)
        naive_summary = summarize(naive)[0]
        idle_summary = summarize(idle)[0]
        self.assertGreater(float(naive_summary["active_p95_penalty_ms"]), 100.0)
        self.assertLess(float(idle_summary["active_p95_penalty_ms"]), 10.0)


class Phase16EphemeralKVTests(unittest.TestCase):
    def test_ephemeral_blocks_are_invisible_until_commit_and_clean_after_abort(self) -> None:
        pool = BlockPool(total_blocks=1024)
        txn = pool.begin_txn("txn", "req", 64)
        pool.allocate_ephemeral(txn.txn_id, ["h0", "h1", "h2", "h3"])
        self.assertFalse(pool.foreground_can_see_ephemeral(txn.txn_id))
        promoted, freed = pool.commit(txn.txn_id, stable_full_blocks=2)
        self.assertEqual(promoted, 2)
        self.assertEqual(freed, 2)
        self.assertTrue(pool.cache_resident("h0"))
        self.assertTrue(pool.cache_resident("h1"))

        txn2 = pool.begin_txn("txn2", "req2", 64)
        pool.allocate_ephemeral(txn2.txn_id, ["x0", "x1"])
        before = len(pool.cached_block_hash_to_block)
        pool.abort(txn2.txn_id)
        self.assertEqual(before, len(pool.cached_block_hash_to_block))
        self.assertEqual(pool.leak_count(), 0)
        self.assertEqual(pool.stale_hash_pointers(), 0)


class Phase16DriftBudgetTests(unittest.TestCase):
    def test_hard_invalidator_and_source_distance_are_separate_from_residency(self) -> None:
        cert = Certificate(
            stable_hash="stable",
            dag_hash="dag",
            layout_hash="layout",
            tool_schema_hash="tool",
            output_contract="contract",
            stable_tokens=100,
            issued_query_distance=10,
            issued_margin_q10=1.0,
            issued_sources=frozenset({"a", "b"}),
        )
        turn = TurnEvidence(
            dynamic_tokens=10,
            query_distance=12,
            margin_q10=0.9,
            source_ids=frozenset({"b", "c"}),
            tool_schema_hash="tool",
            stable_hash="stable",
            dag_hash="dag",
            layout_hash="layout",
            output_contract="contract",
            answer_changed=False,
            retained_prefix_gain=0.5,
        )
        self.assertFalse(hard_invalidated(cert, turn))
        self.assertAlmostEqual(jaccard_distance(cert.issued_sources, turn.source_ids), 2 / 3)
        self.assertLess(wilson_upper(0, 400), 0.01)


if __name__ == "__main__":
    unittest.main()
