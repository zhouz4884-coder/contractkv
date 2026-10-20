"""Exact-input Raw behavior evidence, separate from template authorization.

Trusted-controller admission only. A deployment canary is never Raw evidence.
This finite evidence does not prove arbitrary future generation equivalence.
"""
from copy import deepcopy
import hashlib
import hmac
import json
import secrets


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


class ExactBehaviorLedger:
    schema='contractkv.exact-raw-behavior.v1'

    def __init__(self,context):
        self.context=deepcopy(context)
        self._key=secrets.token_bytes(32)
        self._issued={}

    def scope(self,raw_ids,candidate_ids):
        if not raw_ids or not candidate_ids or any(type(i) is not int or i<0 for i in raw_ids+candidate_ids):
            raise ValueError('complete_actual_prompt_token_IDs_required')
        return dict(schema=self.schema,context=self.context,raw_prompt_sha256=digest(raw_ids),
                    candidate_prompt_sha256=digest(candidate_ids))

    def key(self,raw_ids,candidate_ids):
        return digest(self.scope(raw_ids,candidate_ids))

    def issue(self,raw,candidate,certificate,raw_ids,candidate_ids,reference_kind,verification_reference_sha256):
        scope=self.scope(raw_ids,candidate_ids)
        if reference_kind!='RAW_QUERY':raise ValueError('compiled_deployment_is_not_Raw_behavior_evidence')
        for result,ids in [(raw,raw_ids),(candidate,candidate_ids)]:
            if not result.get('success') or result.get('prompt_token_ids')!=ids:
                raise ValueError('actual_prompt_evidence_missing_or_mismatched')
            if result.get('finish_reason')!='stop' or not result.get('output_token_ids'):
                raise ValueError('complete_answer_and_EOS_required')
        if not raw.get('witness_available') or not raw.get('reference_margins'):
            raise ValueError('actual_Raw_logprob_witness_required')
        if raw['output_token_ids']!=candidate['output_token_ids'] or raw['finish_reason']!=candidate['finish_reason']:
            raise ValueError('Raw_candidate_free_generation_differs')
        if verification_reference_sha256!=digest(raw_ids):raise ValueError('verification_did_not_use_this_Raw_witness')
        if (not certificate.get('certificate_issued') or not certificate.get('minimum_margin_guard_passed')
                or certificate.get('raw_margin_min',-1)<.0625 or certificate.get('candidate_margin_min',-1)<.125
                or certificate.get('terminal_stop_margin',-1)<.125 or min(raw['reference_margins'])<.0625
                or not certificate.get('committed_tokens',0) or certificate['committed_tokens']%16):
            raise ValueError('existing_Token_EOS_PSTP_contract_not_satisfied')
        value=dict(**scope,reference_kind='RAW_QUERY',raw_output_sha256=digest(raw['output_token_ids']),
                   finish_reason=raw['finish_reason'],certificate_hash=certificate['certificate_hash'],
                   stable_prefix_hash=certificate['stable_prefix_hash'],committed_tokens=certificate['committed_tokens'])
        key=digest(scope);self._issued[key]=deepcopy(value)
        return dict(evidence=deepcopy(value),signature=hmac.new(self._key,digest(value).encode(),hashlib.sha256).hexdigest())

    def errors(self,raw_ids,candidate_ids,certificate,bound):
        if not bound or 'evidence' not in bound:return ['exact_Raw_behavior_evidence_missing']
        value=bound['evidence'];errors=[]
        signature=hmac.new(self._key,digest(value).encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,str(bound.get('signature',''))):errors.append('behavior_signature_invalid')
        try:scope=self.scope(raw_ids,candidate_ids)
        except ValueError:return ['actual_prompt_IDs_missing']
        if any(value.get(k)!=v for k,v in scope.items()):errors.append('exact_request_behavior_scope_mismatch')
        if self._issued.get(digest(scope))!=value:errors.append('behavior_evidence_not_issued_for_request')
        for key in ['certificate_hash','stable_prefix_hash','committed_tokens']:
            if value.get(key)!=certificate.get(key):errors.append('behavior_certificate_binding_mismatch')
        if value.get('reference_kind')!='RAW_QUERY':errors.append('Raw_reference_kind_required')
        return sorted(set(errors))
