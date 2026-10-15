import unittest
from scripts.tsc_revision_r1r_summary import route_audit
from scripts.tsc_revision_r1r_validation_summary import expected_cells


class RepairValidationTests(unittest.TestCase):
    def verify(self,scope='a',level='L2',accepted=True,published=0):
        return {'row_type':'verification','session_id':'first-tenant','certificate_namespace':'template',
                'query_scope':scope,'selected_level':level,'certificate_issued':accepted,
                'attempts':[{'certificate_issued':accepted,'committed_tokens':published}]}

    def future(self,scope='a',level='L2',tenant='other-tenant'):
        return {'row_type':'future','session_id':tenant,'certificate_namespace':'template',
                'query_scope':scope,'effective_level':level,'turn_id':3}

    def test_second_tenant_can_use_bound_scope_but_new_query_cannot(self):
        valid=route_audit([self.verify(),self.future()])
        invalid=route_audit([self.verify(),self.future(scope='new-query')])
        self.assertEqual(valid['scope_invalid_admissions'],0)
        self.assertEqual(invalid['scope_invalid_admissions'],1)

    def test_later_approval_cannot_justify_earlier_use(self):
        self.assertEqual(route_audit([self.future(),self.verify()])['scope_invalid_admissions'],1)

    def test_rejection_never_creates_a_reusable_scope_and_publication_is_audited(self):
        result=route_audit([self.verify(accepted=False,published=16),self.future()])
        self.assertEqual(result['scope_invalid_admissions'],1)
        self.assertEqual(result['rejected_published_tokens'],16)

    def test_formal_matrix_has_distinct_studies_and_all_repeats(self):
        names=expected_cells()
        self.assertEqual(len(names),45)
        self.assertEqual(len(set(names)),45)
        self.assertIn('single-session_llama_query-full_r3',names)
        self.assertIn('template-fanout_mistral_query-prefix_r2',names)


if __name__=='__main__': unittest.main()
