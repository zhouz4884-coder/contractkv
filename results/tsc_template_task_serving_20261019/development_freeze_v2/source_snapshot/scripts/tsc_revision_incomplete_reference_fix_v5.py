"""Return fail-closed for the existing incomplete-answer/EOS exception.

Complete-reference behavior is delegated byte-for-byte to the original method.
Only the pre-RPC VerificationIncomplete path gains an explicit rejection result.
"""
from functools import wraps
import time


def repaired_register(original_register,incomplete_error):
    @wraps(original_register)
    def register(self,args,namespace,scope,business,gate,record=lambda row:None):
        started=time.perf_counter()
        try:
            return original_register(self,args,namespace,scope,business,gate,record)
        except incomplete_error as error:
            # The frozen splitter raises only when stop/answer evidence is
            # incomplete. Do not mask an unrelated publication/runtime error.
            if business.get('finish_reason')=='stop' and len(business.get('output_token_ids',[]))>=2:
                raise
            plan=gate.get('plan') or {};margins=business.get('reference_margins') or []
            result=dict(certificate_issued=False,selected_level='L0',query_scope=scope,attempts=[],
                stable_prefix_tokens=plan.get('stable_prefix_end_token',0),
                stable_prefix_hash=plan.get('stable_content_hash',''),
                pre_business_planning_ms=plan.get('cpu_http_preparation_ms',0),
                failure_reason=str(error),verification_status='not_attempted',verify_decision='INCOMPLETE',
                txn_state='ABORTED',committed_tokens=0,raw_all_tokens_margin_min=min(margins) if margins else None,
                raw_eos_margin=None,prospective_gate={k:v for k,v in gate.items() if k!='plan'},
                incomplete_reference_fail_closed_repair='v5',GPU_RPC_dispatched=False)
            record(dict(row_type='raw_reference_incomplete_fail_closed',certificate_namespace=namespace,
                        query_scope=scope,failure_reason=str(error),actual_finish_reason=business.get('finish_reason'),
                        budget_not_extended=True,GPU_RPC_dispatched=False,repair='v5'))
            elapsed=(time.perf_counter()-started)*1000
            result.update(post_business_registration_ms=elapsed,
                          complete_verification_ms=result['pre_business_planning_ms']+elapsed)
            with self.lock:
                if self.decisions.get((namespace,scope),{}).get('certificate_issued'):
                    raise RuntimeError('Incomplete-reference repair must never replace an issued decision')
                self.decisions[namespace,scope]=result
            return result
    return register
