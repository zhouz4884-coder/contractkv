import copy
import unittest
from scripts.tsc_revision_r4_input_fidelity import pack_task_input


class InputFidelityTests(unittest.TestCase):
    def sample(self):
        return {'answer': 'gold must not guide packing', 'segments': [
            {'type': 'SYS_PROMPT', 'text': 'Complete the requested task.'},
            {'type': 'REPO_CONTEXT', 'text': ''.join(f'line_{i} = {i}\n' for i in range(40))},
            {'type': 'CODE_PREFIX', 'text': 'def solve(x):\n    if x:\n        '},
            {'type': 'USER_QUERY', 'text': 'Complete the next line of code.'},
        ]}

    def test_full_input_is_byte_preserved_and_caller_is_immutable(self):
        source = self.sample()
        saved = copy.deepcopy(source)
        result = pack_task_input(source, lambda s: {'fits': True})
        self.assertEqual(result['status'], 'full_original_text_preserved')
        self.assertEqual(result['sample'], source)
        self.assertEqual(source, saved)

    def test_budget_reduces_optional_context_but_keeps_cursor_and_query(self):
        source = self.sample()
        fits = lambda s: {'fits': len(s['segments'][1]['text']) <= 180}
        result = pack_task_input(source, fits)
        self.assertEqual(result['status'], 'optional_context_cropped_to_window')
        self.assertTrue(fits(result['sample'])['fits'])
        self.assertEqual(result['sample']['segments'][2], source['segments'][2])
        self.assertEqual(result['sample']['segments'][3], source['segments'][3])
        self.assertIn('line_0 = 0\n', result['sample']['segments'][1]['text'])
        self.assertIn('line_39 = 39\n', result['sample']['segments'][1]['text'])

    def test_changing_gold_never_changes_retained_input(self):
        first, second = self.sample(), self.sample()
        second['answer'] = 'an entirely different answer near the tail'
        fits = lambda s: {'fits': len(s['segments'][1]['text']) <= 180}
        one, two = pack_task_input(first, fits), pack_task_input(second, fits)
        self.assertEqual(one['sample']['segments'], two['sample']['segments'])
        self.assertEqual(one['segment_ledger'], two['segment_ledger'])

    def test_oversized_critical_input_is_reported_without_clipping_it(self):
        source = self.sample()
        result = pack_task_input(source, lambda s: {'fits': False})
        self.assertEqual(result['status'], 'protected_task_input_exceeds_window')
        self.assertIsNone(result['sample'])
        self.assertTrue(result['protected_fields_were_not_truncated'])

    def test_final_all_variant_validation_can_reject_a_quick_fit(self):
        source = self.sample()
        result = pack_task_input(source, lambda s: {'fits': True},
                                 validate=lambda s: {'fits': len(s['segments'][1]['text']) <= 180})
        self.assertLessEqual(len(result['sample']['segments'][1]['text']), 180)
        self.assertEqual(result['sample']['segments'][2]['text'], source['segments'][2]['text'])


if __name__ == '__main__':
    unittest.main()
