"""Deterministic, label-blind input packing for the isolated protocol repair.

Protect task-defining fields verbatim. Optional context is retained as original
head/tail substrings with an explicit omission marker; whitespace is never
collapsed. Fit callbacks count complete rendered prompts, never model outputs.
"""
from copy import deepcopy
import hashlib
import json
import math
import time
from scripts.phase22_llama_layout_ladder import split_text_preserving


OPTIONAL_CONTEXT_TYPES = {
    'RAG_CHUNK', 'DOC_CONTEXT', 'SYNTHETIC_CONTEXT', 'REPO_CONTEXT',
    'REPO_IMPORT', 'REPO_CLASS', 'REPO_FUNCTION',
}
PROTECTED_TYPES = {'SYS_PROMPT', 'USER_QUERY', 'CODE_PREFIX', 'TOOL_OBS', 'CHAT_HISTORY', 'SCRATCHPAD'}


def sha_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def context_units(text, segment_type, maximum_units=512):
    if not text:
        return []
    if segment_type.startswith('REPO_'):
        units = text.splitlines(keepends=True)
    elif '\n\n' in text:
        chunks = text.split('\n\n')
        units = [chunk + ('\n\n' if i + 1 < len(chunks) else '') for i, chunk in enumerate(chunks)]
    else:
        units = text.splitlines(keepends=True)
        if len(units) <= 1:
            units = split_text_preserving(text, maximum_units)
    if len(units) > maximum_units:
        size = math.ceil(len(units) / maximum_units)
        units = [''.join(units[i:i + size]) for i in range(0, len(units), size)]
    if ''.join(units) != text:
        raise ValueError('Context unitization changed source characters')
    return units


def retain_context(text, units, count, segment_type):
    if count >= len(units):
        return text, [[0, len(text)]], None
    head_count, tail_count = (count + 1) // 2, count // 2
    head = ''.join(units[:head_count])
    tail = ''.join(units[len(units) - tail_count:]) if tail_count else ''
    marker = ('\n# CONTEXT_OMITTED_BY_WINDOW_BUDGET\n' if segment_type.startswith('REPO_')
              else '\n\n[CONTEXT_OMITTED_BY_WINDOW_BUDGET]\n\n')
    ranges = ([[0, len(head)]] if head else []) + ([[len(text) - len(tail), len(text)]] if tail else [])
    return head + marker + tail, ranges, [len(head), len(text) - len(tail)]


def pack_task_input(sample, fit, validate=None):
    """Return packed copy and complete fit/omission ledger.

    fit/validate each return {fits: bool, ...window diagnostics...}. validate
    should cover every declared request variant; fit may use a conservative
    tokenizer-only bound to accelerate the finite context-size search.
    """
    started = time.perf_counter()
    validate = validate or fit
    original = deepcopy(sample)
    optional = []
    for index, segment in enumerate(original['segments']):
        if segment['type'] in OPTIONAL_CONTEXT_TYPES:
            optional.append((index, context_units(segment['text'], segment['type'])))
    total = sum(len(units) for _, units in optional)
    calls = []

    def checked(candidate, checker, stage, keep):
        result = checker(candidate)
        if type(result.get('fits')) is not bool:
            raise ValueError('Tokenizer fit callback must return a Boolean fits field')
        calls.append({'stage': stage, 'retained_optional_units': keep, 'result': result})
        return result['fits']

    def candidate(keep):
        result = deepcopy(original)
        allocations = [keep * len(units) // total if total else 0 for _, units in optional]
        remaining = keep - sum(allocations)
        for i, (_, units) in enumerate(optional):
            amount = min(remaining, len(units) - allocations[i])
            allocations[i] += amount
            remaining -= amount
        ledger = []
        for (index, units), count in zip(optional, allocations):
            before = original['segments'][index]
            after, ranges, omitted = retain_context(before['text'], units, count, before['type'])
            result['segments'][index]['text'] = after
            ledger.append({'segment_index': index, 'segment_type': before['type'],
                           'original_characters': len(before['text']), 'retained_original_characters': sum(b - a for a, b in ranges),
                           'original_units': len(units), 'retained_units': count,
                           'kept_original_character_ranges': ranges, 'omitted_original_character_range': omitted,
                           'original_text_sha256': sha_text(before['text']), 'packed_text_sha256': sha_text(after)})
        return result, ledger

    full, full_ledger = candidate(total)
    if checked(full, validate, 'full_input_all_variants', total):
        result, ledger, status = full, full_ledger, 'full_original_text_preserved'
    else:
        minimal, minimum_ledger = candidate(0)
        if not checked(minimal, validate, 'protected_fields_all_variants', 0):
            return {'status': 'protected_task_input_exceeds_window', 'sample': None,
                    'original_source_segments_sha256': sha_text(json.dumps(original['segments'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))),
                    'fit_calls': calls, 'new_model_requests': 0,
                    'input_preparation_CPU_wall_s': time.perf_counter() - started,
                    'protected_fields_were_not_truncated': True}
        low, high = 0, total
        while low < high:
            middle = (low + high + 1) // 2
            trial, _ = candidate(middle)
            if checked(trial, fit, 'conservative_tokenizer_search', middle):
                low = middle
            else:
                high = middle - 1
        result, ledger = candidate(low)
        while not checked(result, validate, 'selected_input_all_variants', low):
            if low == 0:
                raise ValueError('Fit callback changed for identical protected-only input')
            low -= 1
            result, ledger = candidate(low)
        status = 'optional_context_cropped_to_window'
    for before, after in zip(original['segments'], result['segments']):
        if before['type'] not in OPTIONAL_CONTEXT_TYPES and before['text'] != after['text']:
            raise ValueError('Task-defining field changed during optional context packing')
    if original != sample:
        raise ValueError('Packing mutated the caller input')
    return {'status': status, 'sample': result, 'segment_ledger': ledger,
            'protected_fields_preserved': True, 'retained_whitespace_preserved': True,
            'fit_calls': calls, 'new_model_requests': 0,
            'input_preparation_CPU_wall_s': time.perf_counter() - started,
            'selection_boundary': 'Input text, type and tokenizer window only; no reference labels, answer locations, scores, margins or qualifications are inspected.'}
