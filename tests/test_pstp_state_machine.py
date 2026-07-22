import unittest

from scripts.pstp_transaction_stress import PSTPStateMachine, State, Transaction


class PSTPStateMachineTests(unittest.TestCase):
    def test_only_exact_verified_prefix_is_published(self):
        machine = PSTPStateMachine(); txn = Transaction("t", (1, 2, 3), "scope", 1)
        machine.open(txn)
        machine.apply("t", "begin_verify", scope="scope", epoch=1)
        machine.apply("t", "verify_pass", scope="scope", epoch=1)
        machine.apply("t", "commit", scope="scope", epoch=1)
        self.assertEqual(txn.state, State.COMMITTED)
        self.assertEqual(txn.published_blocks, (1, 2, 3))
        self.assertEqual(machine.audit(), [])

    def test_cancel_commit_race_cannot_publish_after_abort(self):
        machine = PSTPStateMachine(); txn = Transaction("t", (1, 2), "scope", 1)
        machine.open(txn)
        machine.apply("t", "begin_verify", scope="scope", epoch=1)
        machine.apply("t", "verify_pass", scope="scope", epoch=1)
        machine.apply("t", "invalidation", scope="scope", epoch=1)
        machine.apply("t", "commit", scope="scope", epoch=1)
        self.assertEqual(txn.state, State.ABORTED)
        self.assertEqual(txn.published_blocks, ())
        self.assertEqual(machine.audit(), [])


if __name__ == "__main__":
    unittest.main()
