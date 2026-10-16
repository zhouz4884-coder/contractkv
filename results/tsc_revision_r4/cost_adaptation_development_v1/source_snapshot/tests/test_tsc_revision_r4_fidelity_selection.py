"""Source selection must be invariant to outcome labels and pool ordering."""
import unittest
from copy import deepcopy
from scripts.tsc_revision_r4_prepare_fidelity_validation_v1 import ordered_candidates


class SelectionTests(unittest.TestCase):
    def rows(self):
        return [{'dataset': 'LongBench', 'task': 'hotpotqa', 'answer': str(i),
                 'metadata': {'source_group_id': 'doc:'+str(i)}} for i in range(6)]

    def test_labels_and_input_order_cannot_choose_sources(self):
        rows = self.rows()
        altered = deepcopy(list(reversed(rows)))
        for row in altered:
            row['answer'] = 'different gold label'
            row['task_score'] = 1000
            row['model_output'] = 'must not be read'
        names = lambda values: [r['metadata']['source_group_id'] for r in values]
        self.assertEqual(names(ordered_candidates(rows, set(), 'HotpotQA', 10672146)),
                         names(ordered_candidates(altered, set(), 'HotpotQA', 10672146)))

    def test_exclusion_and_source_cluster_deduplication(self):
        rows = self.rows()
        values = ordered_candidates(rows+deepcopy(rows), {'LongBench:hotpotqa:doc:1'}, 'HotpotQA', 10672146)
        names = [r['metadata']['source_group_id'] for r in values]
        self.assertEqual(len(names), 5)
        self.assertNotIn('doc:1', names)
        self.assertEqual(len(names), len(set(names)))


if __name__ == '__main__':
    unittest.main()
