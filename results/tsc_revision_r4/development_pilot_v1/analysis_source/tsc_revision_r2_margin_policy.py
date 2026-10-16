"""Pointwise answer/EOS margin admission; no task labels or outcome shortcuts."""
from __future__ import annotations
import math


def minimum_margin_gate(raw_margins, candidate_margins, stop_margin,
                        raw_floor=float('-inf'), candidate_floor=float('-inf')):
    """Answer arrays exclude EOS; the candidate floor also applies to its stop."""
    raw=[float(x) for x in raw_margins]; candidate=[float(x) for x in candidate_margins]
    raw_floor=float(raw_floor); candidate_floor=float(candidate_floor); stop=float(stop_margin)
    if math.isnan(raw_floor) or math.isnan(candidate_floor):
        raise ValueError('Margin thresholds cannot be NaN')
    result={'passed':False,'reason':'incomplete_or_nonfinite_token_margins',
            'raw_margin_min':float('nan'),'candidate_margin_min':float('nan'),
            'raw_margin_min_index':-1,'candidate_margin_min_index':-1}
    if not raw or len(raw)!=len(candidate) or not all(math.isfinite(x) for x in raw+candidate+[stop]):
        return result
    raw_index=min(range(len(raw)),key=raw.__getitem__)
    candidate_index=min(range(len(candidate)),key=candidate.__getitem__)
    result.update(raw_margin_min=raw[raw_index],candidate_margin_min=candidate[candidate_index],
                  raw_margin_min_index=raw_index,candidate_margin_min_index=candidate_index)
    if raw[raw_index]<raw_floor:
        result['reason']='raw_token_margin_below_floor'
    elif candidate[candidate_index]<candidate_floor:
        result['reason']='candidate_token_margin_below_floor'
    elif stop<candidate_floor:
        result['reason']='terminal_stop_margin_below_candidate_floor'
    else:
        result.update(passed=True,reason='')
    return result
