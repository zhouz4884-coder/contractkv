"""Development prototypes: expected-value admission and explicit sharing scope."""
import hashlib
import math
import re
import time
from scripts.phase17_live_common import digest
from scripts.tsc_revision_r3_output_contract import OutputContractRegistrar


def risk_adjusted_benefit(p_pass, remaining_reuses, save_per_reuse_ms,
                          complete_cost_ms, baseline_ttft_p95_ms, tail_budget_ms,
                          minimum_net_ms=0, safety_factor=1):
    result={'allow_verification':False,'reason':'invalid_cost_features',
            'online_verification_attempt_limit':1,'prediction_is_not_realized_saving':True,
            'tail_budget_is_forecast_not_runtime_guarantee':True}
    values=(p_pass,remaining_reuses,save_per_reuse_ms,complete_cost_ms,
            baseline_ttft_p95_ms,tail_budget_ms,minimum_net_ms,safety_factor)
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in values):return result
    if not (0<=p_pass<=1 and remaining_reuses>=0 and save_per_reuse_ms>=0 and complete_cost_ms>0 and
            baseline_ttft_p95_ms>=0 and tail_budget_ms>0 and minimum_net_ms>=0 and safety_factor>=1):return result
    expected=p_pass*remaining_reuses*save_per_reuse_ms;cost=safety_factor*complete_cost_ms
    result.update(p_pass=p_pass,declared_remaining_reuses=remaining_reuses,
                  expected_saved_ms=expected,estimated_complete_cost_ms=cost,
                  expected_net_ms=expected-cost,minimum_net_ms=minimum_net_ms,
                  baseline_ttft_p95_ms=baseline_ttft_p95_ms,
                  predicted_ready_bound_ms=baseline_ttft_p95_ms+cost,tail_budget_ms=tail_budget_ms)
    if remaining_reuses==0:result['reason']='no_declared_remaining_reuse'
    elif expected-cost<=minimum_net_ms:result['reason']='risk_adjusted_benefit_rejected'
    elif baseline_ttft_p95_ms+cost>tail_budget_ms:result['reason']='online_tail_budget_rejected'
    else:result.update(allow_verification=True,reason='risk_adjusted_benefit_and_tail_pass')
    return result


def answer_for_scope(text):
    answer=re.sub(r'<think>.*?</think>','',text,flags=re.S).strip()
    if answer.startswith('```') and answer.endswith('```'):
        answer=re.sub(r'^```[^\n]*\n','',answer);answer=answer[:-3].strip()
    return ' '.join(answer.strip(' \t\r\n\"\'`').rstrip('.').split()).casefold()


def reference_scope_contract(case,text,max_words=16):
    """An eligibility restriction, never a task-score or general invariance proof."""
    excluded={'SYS_PROMPT','TOOL_OBS','USER_QUERY','CHAT_HISTORY','SCRATCHPAD'}
    segments=case.get('segments',[])
    context=' '.join(' '.join(str(s.get('text','')).split()) for s in segments if s.get('segment_type') not in excluded).casefold()
    observation=[(s.get('segment_id'),s.get('segment_type'),s.get('text')) for s in segments if s.get('segment_type')=='TOOL_OBS']
    answer=answer_for_scope(text);words=len(answer.split())
    valid_limit=type(max_words) is int and max_words>0
    pattern=(r'(?<!\w)' if answer and answer[0].isalnum() else '')+re.escape(answer)+(r'(?!\w)' if answer and answer[-1].isalnum() else '')
    span=re.search(pattern,context) if valid_limit and answer and words<=max_words and '<think>' not in answer else None
    passed=bool(span)
    return {'shareable_query_scope':passed,'scope_type':'query_with_metadata_schema' if passed else 'exact_observation_only',
            'reason':'short_stable_context_literal_span' if passed else 'free_form_reference_requires_observation_scope',
            'normalized_answer_words':words,'max_literal_answer_words':max_words,
            'normalized_answer_sha256':hashlib.sha256(answer.encode()).hexdigest(),
            'stable_context_sha256':hashlib.sha256(context.encode()).hexdigest(),
            'exact_observation_hash':digest(observation),'matched_context_span':list(span.span()) if span else None,
            'uses_gold_labels':False,'served_output_rewritten':False,
            'boundary':'Structural sharing eligibility; finite evidence does not prove all future quality.'}


class ScopeContractRegistrar(OutputContractRegistrar):
    def register(self,args,namespace,scope,business,gate,record=lambda row:None):
        key=(namespace,scope)
        with self.lock:already=key in self.decisions or key in self.reserved
        if already:return super().register(args,namespace,scope,business,gate,record)
        started=time.perf_counter();check=None
        if gate.get('allow_verification'):
            if not gate.get('scope_case'):
                gate={**gate,'allow_verification':False,'reason':'scope_contract_case_evidence_missing'}
            else:
                check=reference_scope_contract(gate['scope_case'],business['output_text'],gate.get('max_literal_answer_words',16))
                record({'row_type':'reference_scope_contract','certificate_namespace':namespace,'query_scope':scope,'check':check})
                if not check['shareable_query_scope']:
                    gate={**gate,'allow_verification':False,'reason':'observation_scope_has_no_declared_exact_reuse'}
        check_ms=(time.perf_counter()-started)*1000
        result=super().register(args,namespace,scope,business,gate,record)
        result['scope_contract_check_ms']=check_ms;result['reference_scope_contract']=check
        result['complete_verification_ms']+=check_ms
        result['post_business_registration_ms']+=check_ms
        return result
