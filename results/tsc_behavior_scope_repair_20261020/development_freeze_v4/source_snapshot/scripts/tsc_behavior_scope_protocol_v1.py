"""Strict successor; the frozen deployment protocol remains unchanged."""
from scripts.tsc_template_task_protocol_v2 import ServingAuthority as DeploymentAuthority
from scripts.contractkv_exact_behavior import ExactBehaviorLedger
from scripts.phase17_live_common import digest


class StrictServingAuthority(DeploymentAuthority):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.behavior=ExactBehaviorLedger(dict(identity=self.identity,model=self.args.model_identity,
            policy=self.args.policy_hash,qualification=self.qualification_hash,domain=self.domain,
            epoch=self.epoch,generation=dict(temperature=0,top_p=1,seed=14014,QA_budget=128,Repo_budget=384)))

    def admit(self,sample,tenant,turn,plan,certificate,bound,*,raw_ids=None,candidate_ids=None,behavior=None):
        errors=super().admit(sample,tenant,turn,plan,certificate,bound)
        if raw_ids is None or candidate_ids is None:errors.append('actual_prompt_IDs_missing')
        else:
            errors.extend(self.behavior.errors(raw_ids,candidate_ids,certificate,behavior))
            if digest(candidate_ids)!=plan['prompt_ids_sha256']:errors.append('actual_candidate_plan_mismatch')
        return sorted(set(errors))
