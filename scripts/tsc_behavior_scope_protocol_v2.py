"""Strict Raw evidence plus actual dispatched prefix identity enforcement."""
from scripts.tsc_behavior_scope_protocol_v1 import StrictServingAuthority as ParentAuthority
from scripts.phase17_live_common import digest


def actual_prefix_errors(candidate_ids,certificate):
    end=certificate.get('stable_prefix_tokens',0);commit=certificate.get('committed_tokens',0)
    if (type(end) is not int or type(commit) is not int or commit<=0 or commit%16
            or commit>end or not candidate_ids or end>=len(candidate_ids)):
        return ['actual_certified_prefix_boundary_invalid']
    if digest(candidate_ids[:end])!=certificate.get('stable_prefix_hash'):
        return ['actual_certified_prefix_hash_mismatch']
    return []


class StrictServingAuthority(ParentAuthority):
    def admit(self,sample,tenant,turn,plan,certificate,bound,*,raw_ids=None,candidate_ids=None,behavior=None):
        errors=super().admit(sample,tenant,turn,plan,certificate,bound,raw_ids=raw_ids,candidate_ids=candidate_ids,behavior=behavior)
        if candidate_ids is not None:errors.extend(actual_prefix_errors(candidate_ids,certificate))
        return sorted(set(errors))
