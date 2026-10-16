"""A scope receives at most one GPU qualification attempt, with early abstention."""
import math
from threading import Lock
import time
from scripts.phase17_live_common import api_root,post_json
from scripts.tsc_revision_r2_candidate_plan import verification_request


class SingleShotRegistrar:
    def __init__(self,raw_floor,candidate_floor,poster=post_json):
        if not all(math.isfinite(x) and x>0 for x in (raw_floor,candidate_floor)):
            raise ValueError('Deployment floors must be finite and positive')
        self.raw_floor=raw_floor;self.candidate_floor=candidate_floor;self.poster=poster
        self.decisions={};self.reserved=set();self.lock=Lock()

    def register(self,args,namespace,scope,business,gate,record=lambda row:None):
        key=(namespace,scope)
        with self.lock:
            if key in self.decisions:return self.decisions[key]
            if key in self.reserved:
                return {'certificate_issued':False,'selected_level':'L0','query_scope':scope,
                        'attempts':[],'failure_reason':'same_scope_qualification_pending'}
            self.reserved.add(key)
        begin=time.perf_counter();plan=gate.get('plan')
        result={'certificate_issued':False,'selected_level':'L0','query_scope':scope,'attempts':[],
                'stable_prefix_tokens':plan['stable_prefix_end_token'] if plan else 0,
                'stable_prefix_hash':plan['stable_content_hash'] if plan else '',
                'pre_business_planning_ms':plan['cpu_http_preparation_ms'] if plan else 0,
                'complete_verification_ms':0,'failure_reason':'','verification_status':'not_attempted',
                'prospective_gate':{k:v for k,v in gate.items() if k!='plan'}}
        def finish():
            result['post_business_registration_ms']=(time.perf_counter()-begin)*1000
            result['complete_verification_ms']=result['pre_business_planning_ms']+result['post_business_registration_ms']
            with self.lock:self.decisions[key]=result
            return result
        if not gate.get('allow_verification'):
            result['failure_reason']=gate.get('reason','prospective_benefit_rejected')
            return finish()
        margins=business.get('reference_margins')
        if (not business.get('witness_available') or not margins or len(margins)!=len(business['output_token_ids'])
                or not all(math.isfinite(x) for x in margins)):
            result['failure_reason']='raw_business_margin_evidence_incomplete';return finish()
        result['raw_all_tokens_margin_min']=min(margins);result['raw_eos_margin']=margins[-1]
        if min(margins)<self.raw_floor:
            result['failure_reason']='pointwise_raw_answer_or_eos_margin_below_floor';return finish()
        rid=f'{args.cell_id}-single-{namespace}-{scope}'
        try:
            payload,evidence=verification_request(args,plan,business,rid,args.policy_hash+':'+namespace,True,'r2-margin-benefit-single-shot-v1')
        except ValueError as exc:
            result['failure_reason']=str(exc);return finish()
        record({'row_type':'verification_request','request_id':rid,'payload':payload,**evidence})
        started=time.perf_counter()
        try:response=self.poster(api_root(args.base_url)+'/v1/contractkv/verify',payload,args.timeout)
        except Exception as exc:
            result['attempts']=[{'level':plan['level'],'request_id':rid,'verification_ms':(time.perf_counter()-started)*1000,
                                 'result_unavailable':True,'error':repr(exc)}]
            result['failure_reason']=repr(exc);result['verification_status']='indeterminate_request_failure'
            return finish()
        result['attempts']=[{'level':plan['level'],'verification_ms':(time.perf_counter()-started)*1000,**response}]
        result['verification_status']='completed'
        record({'row_type':'verification_response','request_id':rid,'response':response})
        commit=int(response.get('committed_tokens',0))
        if not response.get('certificate_issued'):
            if commit:raise RuntimeError('Rejected single-shot qualification published tokens')
            result['failure_reason']=response.get('failure_reason','single_shot_rejected')
            return finish()
        if (not response.get('minimum_margin_guard_passed') or response['raw_margin_min']<self.raw_floor
                or response['candidate_margin_min']<self.candidate_floor or response['terminal_stop_margin']<self.candidate_floor
                or commit<=0 or commit%16 or commit>plan['stable_prefix_end_token']):
            raise RuntimeError('Server admission violates frozen pointwise/publication contract')
        result.update(response,selected_level=plan['level'],failure_reason='')
        return finish()
