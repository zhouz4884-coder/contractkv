"""CPU controls for positional horizon reporting, not generation evidence."""
import unittest

from scripts.tsc_revision_r1r_output_horizon import horizon_measures


class OutputHorizonTests(unittest.TestCase):
    def test_identical_witness_has_no_extra_positions(self):
        result=horizon_measures(3,[1,2,99],[1,2,99])
        self.assertEqual(result['positions_beyond_reference_length'],0)
        self.assertEqual(result['first_divergence_from_witness'],-1)
        self.assertEqual(result['future_positions_from_first_divergence'],0)

    def test_longer_sequence_reports_excess_separately_from_path_divergence(self):
        result=horizon_measures(3,[1,2,3,4,99],[1,2,99])
        self.assertEqual(result['positions_beyond_reference_length'],2)
        self.assertEqual(result['first_divergence_from_witness'],2)
        self.assertEqual(result['future_positions_from_first_divergence'],3)

    def test_shorter_divergent_output_is_not_treated_as_the_same_path(self):
        result=horizon_measures(3,[8,99],[1,2,99])
        self.assertEqual(result['positions_beyond_reference_length'],0)
        self.assertEqual(result['first_divergence_from_witness'],0)
        self.assertEqual(result['future_positions_from_first_divergence'],2)

    def test_missing_historical_ids_do_not_invent_sequence_comparison(self):
        result=horizon_measures(3,[1,2,3,4,99])
        self.assertEqual(result['positions_beyond_reference_length'],2)
        self.assertFalse(result['witness_ids_available'])
        self.assertEqual(result['first_divergence_from_witness'],'unavailable')

    def test_invalid_reference_count_cannot_silently_pass(self):
        with self.assertRaises(ValueError): horizon_measures(0,[1])
        with self.assertRaises(ValueError): horizon_measures(3,[1],[1,2])


if __name__=='__main__': unittest.main()
