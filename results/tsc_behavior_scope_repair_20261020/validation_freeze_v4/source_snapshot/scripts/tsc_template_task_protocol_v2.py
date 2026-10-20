"""Task-bearing controlled deployment protocol, distinct from Raw-query witness R4.

Fixed authorized FAQ entry, fixed task question, stable workspace documents,
and the original service-quality benchmark's neutral per-request tool metadata.
This is a controlled repetition protocol, not a production arrival trace.
"""
from copy import deepcopy
from dataclasses import asdict
import secrets
import time

from scripts.tsc_revision_r4_fidelity_adapter import build_faithful_case
from scripts.tsc_revision_r4_fidelity_adapter_v2 import ordered_text_preserving_segments
from scripts.phase22_llama_layout_ladder import expand_stable_segments, layout_for_level
from scripts.phase14c_run_full_pool_quality_jobs import quality_messages
from scripts.phase17_live_common import digest, tokenize
from scripts.contractkv_pstp import lcp_length
from scripts.contractkv_cache_identity import CacheAuthority
from scripts.contractkv_certificate_binding import CertificateBinding, RequestBinding, sign, validation_errors
from scripts.contractkv_authorized_requests import adapted_register, authorized_business_generate
from scripts.tsc_revision_r2_candidate_plan import verification_request as original_verification_request
from scripts.tsc_revision_incomplete_reference_fix_v5 import repaired_register
from scripts.contractkv_verifier import VerificationIncomplete

MODELS=['Qwen3-8B','Mistral-7B-Instruct-v0.3','Llama-3.1-8B-Instruct']
STUDY='results/tsc_template_task_serving_20261019'
DISK='/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9'
GENERATION='configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json'
OBSERVATION_SCHEMA='original-service-quality-neutral-tenant-turn-no-task-evidence-v1'

def make_case(sample,tenant,turn):
    assert sample['revision_family'] in {'HotpotQA','RepoBench'}
    case=expand_stable_segments(build_faithful_case(deepcopy(sample),0),16)
    for segment in case['segments']:
        if segment['segment_type']=='TOOL_OBS':
            segment['text']=(f'[PRIVATE_TOOL_OBS] authorized tenant=tenant{tenant:02d}; turn={turn}; '
                             'no additional task evidence is provided.')
    return case

def prepared(sample,tenant,turn,level):
    case=make_case(sample,tenant,turn)
    order=layout_for_level(case,level,{'L0':0,'L1':.25,'L2':.75,'L3':1})['topological_order']
    return case,order,quality_messages(case,ordered_text_preserving_segments(order,case['segments']))

def candidate_plan(args,sample,tenant=0,turn=0):
    started=time.perf_counter();case,order,messages=prepared(sample,tenant,turn,'L3')
    ids=tokenize(args.base_url,args.model,messages,True,args.timeout)
    stable=[];byid={s['segment_id']:s for s in case['segments']}
    for sid in order:
        if byid[sid]['segment_type'] in {'TOOL_OBS','USER_QUERY','CHAT_HISTORY','SCRATCHPAD'}:break
        stable.append(sid)
    prefix=tokenize(args.base_url,args.model,quality_messages(case,ordered_text_preserving_segments(stable,case['segments'])),False,args.timeout)
    end=lcp_length(ids,prefix)
    return dict(level='L3',messages=messages,prompt_token_ids=ids,prompt_ids_sha256=digest(ids),
        stable_prefix_end_token=end,stable_full_blocks=end//16,stable_content_hash=digest(ids[:end]),
        layout_hash=digest(order),dependency_graph_hash=digest([(s['segment_id'],s.get('dependencies',[])) for s in case['segments']]),
        query_scope=digest(dict(question=question(sample),schema=OBSERVATION_SCHEMA)),output_budget=budget(sample),
        cpu_http_preparation_ms=(time.perf_counter()-started)*1000)

def budget(sample):return 128 if sample['revision_family']=='HotpotQA' else 384

def question(sample):
    values=[s['text'] for s in sample['segments'] if s['type']=='USER_QUERY']
    assert len(values)==1 and values[0]
    return values[0]

def deployment_request(*args,**kwargs):
    payload,evidence=original_verification_request(*args,**kwargs)
    payload['attestation_mode']='prospective-qualified-deployment-compiled-witness-v2'
    payload['policy_version']='task-bearing-session-template-same-attestation-v1'
    evidence['reference_kind']='compiled_deployment_attestation_not_Raw_equivalence'
    return payload,evidence

_register,ADAPTER_PROOF=adapted_register()
# adapted_register creates an isolated globals dict, leaving the historical
# Raw-query registrar untouched. Only declaration of the reference source changes.
_register.__globals__['verification_request']=deployment_request
_register=repaired_register(_register,VerificationIncomplete)
ADAPTER_PROOF={**ADAPTER_PROOF,'request_metadata_declares_compiled_reference':True,
               'margin_EOS_and_PSTP_logic_unchanged':True}

class DeploymentRegistrar:
    def __init__(self,authority,identity):
        from threading import Lock
        from scripts.phase17_live_common import post_json
        self.raw_floor=.0625;self.candidate_floor=.125;self.poster=post_json
        self.decisions={};self.reserved=set();self.lock=Lock()
        self.authority=authority;self.cache_identity=identity

    def register(self,args,namespace,scope,business,gate,record=lambda r:None):
        self.authority.require(self.cache_identity)
        return _register(self,args,namespace,scope,business,gate,record)

class ServingAuthority:
    def __init__(self,args,identity,sources,tenants,qualification_hash):
        self.args=args;self.identity=identity;self.domain='task-bearing-authorized-workspace';self.epoch=1
        self.qualification_hash=qualification_hash;self.key=secrets.token_bytes(32)
        members={'controller':{self.domain}}
        members.update({self.principal(s,t):{self.domain} for s in sources for t in range(tenants)})
        self.cache=CacheAuthority(secrets.token_bytes(32),digest(identity),args.policy_hash,{self.domain:1},members)

    @staticmethod
    def principal(sample,tenant):return sample['revision_session_id']+f'-tenant{tenant:02d}'

    def cache_identity(self,sample,tenant=None):
        return self.cache.bind('controller' if tenant is None else self.principal(sample,tenant),self.domain,self.epoch,sample['revision_session_id'])

    def generate(self,sample,tenant,messages,budget,rid,witness=False):
        identity=self.cache_identity(sample,tenant)
        result=authorized_business_generate(self.cache,identity,self.args,messages,budget,rid,witness)
        result['actual_wire_cache_salt']=self.cache.require(identity)
        return result

    def private_generate(self,sample,messages,budget,rid,witness=False,kind='attestation'):
        identity=self.cache.bind('controller',self.domain,self.epoch,
            sample['revision_session_id']+':controller-private-'+kind)
        result=authorized_business_generate(self.cache,identity,self.args,messages,budget,rid,witness)
        result['actual_wire_cache_salt']=self.cache.require(identity)
        return result

    def fields(self,sample,plan,certificate,tenant_scope):
        qhash=digest(question(sample))
        return dict(model_id=self.args.model_identity,model_revision=self.identity['model_revision'],
            tokenizer_hash=self.identity['tokenizer'],chat_template_hash=self.identity['chat_template_hash'],
            serving_runtime='vllm',runtime_revision=self.identity['runtime_revision'],
            generation_config_hash=digest(dict(question_hash=qhash,source_manifest_hash=digest(sample['segments']),
                observation_schema=OBSERVATION_SCHEMA,temperature=0,top_p=1,seed=14014,budget=budget(sample))),
            qualification_manifest_hash=self.qualification_hash,policy_hash=self.args.policy_hash,
            tenant_id=tenant_scope,authorization_domain=self.domain,service_template_id=sample['revision_session_id'],
            service_template_epoch=self.epoch,stable_prefix_hash=certificate['stable_prefix_hash'],layout_hash=plan['layout_hash'])

    def bind(self,sample,plan,certificate,tenant=None):
        scope='*' if tenant is None else self.principal(sample,tenant)
        binding=CertificateBinding(schema_version='contractkv.task-bearing-deployment.v1',certificate_id=certificate['certificate_hash'],
            expires_at_epoch=self.epoch,**self.fields(sample,plan,certificate,scope))
        return dict(binding=asdict(binding),signature=sign(binding,self.key),tenant_scope=scope,
                    fixed_question_sha256=digest(question(sample)),observation_schema=OBSERVATION_SCHEMA)

    def admit(self,sample,tenant,turn,plan,certificate,bound):
        self.cache.require(self.cache_identity(sample,tenant))
        scope=bound['tenant_scope'];errors=[]
        if scope!='*' and scope!=self.principal(sample,tenant):errors.append('session_membership_mismatch')
        if bound['fixed_question_sha256']!=digest(question(sample)):errors.append('fixed_question_mismatch')
        if type(turn) is not int or not 0<=turn<=8:errors.append('observation_outside_frozen_schema')
        request=RequestBinding(current_epoch=self.epoch,private_suffix_excluded=True,**self.fields(sample,plan,certificate,scope))
        errors.extend(validation_errors(CertificateBinding(**bound['binding']),request,bound['signature'],self.key))
        return sorted(set(errors))
