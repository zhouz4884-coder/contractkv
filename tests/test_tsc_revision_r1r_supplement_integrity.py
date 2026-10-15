"""Synthetic CPU audit controls; these are not experimental generations."""
import copy
import json
import unittest

from scripts.tsc_revision_r1r_long_summary import structure_findings
from scripts.tsc_revision_r1r_known_summary_audit_v2 import future_identity_findings


class LongSupplementIntegrityTests(unittest.TestCase):
    def records(self):
        rows=[]; text=json.dumps(list(range(1001,1129)))
        for cap in (256,512,1536):
            common={'model':'qwen3-8b','repeat':1,'cap':cap}
            rows.append({**common,'row_type':'reference','finish_reason':'stop','output_token_ids':[1,2],'witness_available':True})
            rows.append({**common,'row_type':'verification','reference_finish':'stop','reference_tokens':2,'certificate_issued':True})
            for turn in (1,2):
                output={'output_text':text,'output_token_ids':[1,2]}
                score={'complete_correct_array':True,'valid_array':True}
                rows.append({**common,'row_type':'paired_future','turn':turn,'compiled':True,
                             'raw':copy.deepcopy(output),'policy':copy.deepcopy(output),
                             'raw_score':score.copy(),'policy_score':score.copy(),'first_diverging_token':-1})
        return rows

    def audit(self,rows):
        return structure_findings(rows,'qwen3-8b',1,[256,512,1536],2)

    def test_frozen_coordinate_control_passes(self):
        self.assertEqual(self.audit(self.records()),[])

    def test_correct_counts_do_not_hide_wrong_budget_or_turn(self):
        rows=self.records(); rows[0]['cap']=1536; rows[2]['turn']=2
        findings=self.audit(rows)
        self.assertIn('reference_cap_set',findings)
        self.assertIn('future_cap_turn_set',findings)

    def test_scores_and_route_are_checked_against_actual_record(self):
        rows=self.records(); rows[2]['policy']['output_text']='[]'; rows[2]['compiled']=False
        findings=self.audit(rows)
        self.assertIn('reported_array_score_mismatch',findings)
        self.assertIn('future_route_mismatch',findings)


class KnownSupplementIntegrityTests(unittest.TestCase):
    def fixture(self):
        sample={'revision_session_id':'frozen-session','revision_source_group':'frozen-source','revision_family':'NarrativeQA'}
        rows=[]; events={}
        for turn in range(1,10):
            rid=f'future-{turn}'
            rows.append({'session_id':'frozen-session','source_group':'frozen-source','family':'NarrativeQA',
                         'turn_id':turn,'model':'Qwen3-8B','repeat':1,'policy':'query-prefix','request_id':rid,
                         'success':True,'token_ids_available':True,'output_token_ids':[1,2],'completion_tokens':2,
                         'finish_reason':'stop','metric_join_success':True,'new_prefill_tokens':8})
            events[rid]={'prompt_tokens':10,'prefix_hit_tokens':2}
        return rows,[sample],events

    def test_frozen_source_control_passes(self):
        rows,samples,events=self.fixture()
        self.assertEqual(future_identity_findings(rows,samples,'Qwen3-8B','query-prefix',events),[])

    def test_correct_counts_do_not_hide_changed_source(self):
        rows,samples,events=self.fixture(); rows[0]['session_id']='other-session'; rows[0]['source_group']='other-source'
        findings=future_identity_findings(rows,samples,'Qwen3-8B','query-prefix',events)
        self.assertIn('frozen_session_turn_set',findings)
        self.assertIn('frozen_source_family_identity',findings)

    def test_claimed_join_requires_actual_metric_event(self):
        rows,samples,events=self.fixture(); events.pop(rows[0]['request_id'])
        self.assertIn('actual_metric_join',future_identity_findings(rows,samples,'Qwen3-8B','query-prefix',events))


if __name__=='__main__': unittest.main()
