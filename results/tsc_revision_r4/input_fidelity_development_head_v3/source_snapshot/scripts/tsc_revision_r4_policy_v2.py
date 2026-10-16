"""Broader typed sharing prototype, after literal-only dev coverage failure."""
import math
import re
import time
from scripts.tsc_revision_r4_policy import risk_adjusted_benefit,answer_for_scope
from scripts.tsc_revision_r4_policy import reference_scope_contract as literal_scope
from scripts.tsc_revision_r3_output_contract import OutputContractRegistrar

ABSTENTION=re.compile(r"\b(?:not (?:mentioned|provided|available|given|specified)|no (?:information|evidence)|insufficient (?:information|context)|cannot (?:answer|determine|find)|unable to (?:answer|determine|find)|does not (?:mention|provide|include|contain|specify)|not enough (?:information|context)|i (?:do not|don't) know)\b")


def reference_scope_contract(case,text,max_words=16,raw_margins=None,ambiguity_boundary=.125):
    result=literal_scope(case,text,max_words)
    answer=answer_for_scope(text);denial=bool(ABSTENTION.search(answer))
    finite=bool(raw_margins) and all(isinstance(x,(int,float)) and math.isfinite(x) for x in raw_margins)
    raw_min=min(raw_margins) if finite else None
    short=0<result['normalized_answer_words']<=max_words
    inferred=short and not denial and raw_min is not None and raw_min>ambiguity_boundary
    shared=short and not denial and (result['shareable_query_scope'] or inferred)
    result.update(shareable_query_scope=bool(shared),scope_type='query_with_metadata_schema' if shared else 'exact_observation_only',
                  explicit_abstention=denial,raw_reference_margin_min=raw_min,
                  nonliteral_ambiguity_boundary=ambiguity_boundary,
                  reason=('short_stable_context_literal_span' if result['shareable_query_scope'] and shared else
                          'short_nonabstaining_reference_above_ambiguity_boundary' if shared else
                          'abstention_requires_observation_scope' if denial else
                          'long_or_ambiguous_reference_requires_observation_scope'))
    return result


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
                check=reference_scope_contract(gate['scope_case'],business['output_text'],gate.get('max_literal_answer_words',16),
                                                business.get('reference_margins'),gate.get('nonliteral_ambiguity_boundary',.125))
                record({'row_type':'reference_scope_contract','certificate_namespace':namespace,'query_scope':scope,'check':check})
                if not check['shareable_query_scope']:
                    gate={**gate,'allow_verification':False,'reason':'observation_scope_has_no_declared_exact_reuse'}
        elapsed=(time.perf_counter()-started)*1000
        result=super().register(args,namespace,scope,business,gate,record)
        result['scope_contract_check_ms']=elapsed;result['reference_scope_contract']=check
        result['complete_verification_ms']+=elapsed;result['post_business_registration_ms']+=elapsed
        return result
