"""CPU auditor controls; these records are not serving measurements."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.tsc_revision_r1r_validation_summary import audit_cell


class RecordIdentityTests(unittest.TestCase):
    def fixture(self,directory,rename=False):
        expected={}; rows=[]; events=[]
        for source in range(50):
            sid=f'source-{source}'; expected[sid]=(f'group-{source}','HotpotQA',sid)
            for turn in range(10):
                rid=f'rid-{source}-{turn}'
                rows.append({'row_type':'warm' if turn==0 else 'future','session_id':('forged-source' if rename and source==0 else sid),
                             'source_group':f'group-{source}','family':'HotpotQA','certificate_namespace':sid,'query_scope':'query',
                             'turn_id':turn,'study':'single-session','model':'Qwen3-8B','repeat':1,'policy':'raw-order',
                             'effective_level':'L0','scope_first_raw_business':False,'success':True,'request_id':rid,
                             'token_ids_available':True,'output_token_ids':[1,2],'completion_tokens':2,'metric_join_success':True,
                             'new_prefill_tokens':10})
                events.append({'event':'prefix_cache_request_observation','initial_prefill_observation':True,
                               'request_id':rid,'prompt_tokens':10,'prefix_hit_tokens':0})
        raw=directory/'raw.jsonl'; raw.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
        (directory/'metrics.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in events),encoding='utf-8')
        (directory/'summary.json').write_text(json.dumps({'study':'single-session','expected_futures':450,
            'raw_file_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'verification_calls':0,'verification_ms_total':0}),encoding='utf-8')
        (directory/'pre_measurement_control.summary.json').write_text(json.dumps({k:True for k in
            ('cold_read_decisions_agree','cached_read_observed','no_unapproved_or_generic_read','zero_rejected_publication')}),encoding='utf-8')
        return expected

    def test_complete_frozen_identity_control_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary); expected=self.fixture(directory)
            result,_,_=audit_cell(directory,expected)
            self.assertEqual(result['findings'],[])

    def test_correct_count_hash_and_unique_requests_cannot_hide_wrong_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary); expected=self.fixture(directory,rename=True)
            result,_,_=audit_cell(directory,expected)
            self.assertIn('frozen_session_turn_set_mismatch',result['findings'])
            self.assertIn('frozen_source_family_or_namespace_mismatch',result['findings'])
            self.assertNotIn('raw_hash_mismatch',result['findings'])
            self.assertNotIn('future_count',result['findings'])
            self.assertNotIn('duplicate_request_id',result['findings'])


if __name__=='__main__': unittest.main()
