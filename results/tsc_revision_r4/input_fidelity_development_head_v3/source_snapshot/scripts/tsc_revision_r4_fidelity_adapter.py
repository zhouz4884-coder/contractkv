"""Isolated task-input adapter; the frozen R4 client and backend stay unchanged.

The caller must supply already packed, provenance-bound input and word cap 0.
Only the contradictory CODE_PREFIX volatility annotation is corrected here.
No text, dependency, scoring, qualification or scheduling rule changes.
"""
from contextlib import contextmanager
from scripts.phase13b_fresh_policy_quality_replay import build_case as historical_build_case
from scripts import tsc_revision_live as original


ADAPTER_VERSION = 'task-fidelity-preserved-text-code-prefix-types-v1'


def build_faithful_case(sample, stable_word_limit=0):
    if stable_word_limit != 0:
        raise ValueError('Faithful input must not undergo the historical word-cap renderer')
    if sample.get('revision_input_fidelity', {}).get('protocol') != 'structure-preserving-window-v2':
        raise ValueError('Require explicitly packed and provenance-bound faithful input')
    case = historical_build_case(sample, stable_word_limit=0)
    for segment in case['segments']:
        if segment['segment_type'] == 'CODE_PREFIX':
            segment['volatility'] = 0.0
            segment['cache_stability'] = 1.0
    return case


@contextmanager
def installed_adapter():
    previous = original.build_case
    if previous is not historical_build_case:
        raise RuntimeError('An undeclared input adapter is already installed')
    original.build_case = build_faithful_case
    try:
        yield
    finally:
        original.build_case = previous
