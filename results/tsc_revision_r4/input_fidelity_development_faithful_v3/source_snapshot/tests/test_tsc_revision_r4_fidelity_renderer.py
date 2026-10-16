import unittest
from scripts.tsc_revision_r4_fidelity_adapter_v2 import ordered_text_preserving_segments, installed_adapter
from scripts.phase12f_real_vllm_caposc_replay import _ordered_text
from scripts import tsc_revision_live, tsc_revision_r1r_live, tsc_revision_r4_live, tsc_revision_r2_candidate_plan


class RendererTests(unittest.TestCase):
    def test_contiguous_python_prefix_keeps_whitespace_and_cursor(self):
        pieces = [
            {'segment_id': 's1__p0', 'segment_type': 'CODE_PREFIX', 'text': 'module.py\nclass X:\n'},
            {'segment_id': 's1__p1', 'segment_type': 'CODE_PREFIX', 'text': '    def f(self):\n        return ('},
            {'segment_id': 's1__p2', 'segment_type': 'CODE_PREFIX', 'text': '\n            1 +'},
        ]
        text = ordered_text_preserving_segments([p['segment_id'] for p in pieces], pieces)
        self.assertTrue(text.endswith(''.join(p['text'] for p in pieces)))
        self.assertEqual(text.count('[CODE_PREFIX:'), 1)
        self.assertNotIn('__p', text)

    def test_tool_boundary_remains_explicit_without_reordering(self):
        pieces = [
            {'segment_id': 's1__p0', 'segment_type': 'RAG_CHUNK', 'text': 'first\n'},
            {'segment_id': 's1__p1', 'segment_type': 'RAG_CHUNK', 'text': 'last\n'},
            {'segment_id': 's2', 'segment_type': 'TOOL_OBS', 'text': 'private'},
        ]
        text = ordered_text_preserving_segments(['s1__p0', 's2', 's1__p1'], pieces)
        self.assertLess(text.index('first'), text.index('private'))
        self.assertLess(text.index('private'), text.index('last'))
        self.assertIn('[RAG_CHUNK:s1__p1]\nlast\n', text)

    def test_all_serving_and_qualification_consumers_restore_after_exception(self):
        modules = (tsc_revision_live, tsc_revision_r1r_live, tsc_revision_r4_live, tsc_revision_r2_candidate_plan)
        with self.assertRaisesRegex(ValueError, 'test unwind'):
            with installed_adapter():
                self.assertTrue(all(module._ordered_text is ordered_text_preserving_segments for module in modules))
                raise ValueError('test unwind')
        self.assertTrue(all(module._ordered_text is _ordered_text for module in modules))


if __name__ == '__main__':
    unittest.main()
