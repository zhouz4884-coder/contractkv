"""Transparent rendering and exact token ownership for the structural survey."""
from pathlib import Path
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def messages_for(sample, history, turn, protocol):
    segments = sample['segments']
    query = '\n'.join(s['text'] for s in segments if s['type'] == 'USER_QUERY')
    wrapped = protocol['query_wrappers'][turn].format(query=query)
    systems = [s['text'] for s in segments if s['type'] == 'SYS_PROMPT']
    system = (protocol['RepoBench_system'] if sample['family'] == 'RepoBench'
              else '\n'.join(systems + [protocol['QA_system_suffix']]))
    messages = [{'role': 'system', 'content': system}]
    spans = [[(0, len(system), 'stable', 'SYS_PROMPT')]]
    for previous in history:
        for role, key in [('user', 'query'), ('assistant', 'answer')]:
            value = previous[key]
            messages.append({'role': role, 'content': value})
            spans.append([(0, len(value), 'history', 'CHAT_HISTORY')])
    current = ''
    local = []

    def add(kind, text, category):
        nonlocal current
        if current:
            current += '\n\n'
        current += '[' + kind + ']\n'
        start = len(current)
        current += text
        local.append((start, len(current), category, kind))

    if sample['family'] == 'RepoBench':
        add('USER_QUERY', wrapped, 'query')
    for segment in segments:
        kind = segment['type']
        if kind in {'SYS_PROMPT', 'USER_QUERY'}:
            continue
        category = 'stable' if kind in protocol['stable_categories'] else 'query'
        add(kind, segment['text'], category)
    if sample['family'] != 'RepoBench':
        add('USER_QUERY', wrapped, 'query')
    messages.append({'role': 'user', 'content': current})
    spans.append(local)
    return messages, spans, wrapped


def tokenize_request(tokenizer, sample, history, turn, protocol):
    messages, spans, wrapped = messages_for(sample, history, turn, protocol)
    rendered = tokenizer.apply_chat_template(messages, tokenize=False,
        add_generation_prompt=True, enable_thinking=protocol['enable_thinking'])
    encoded = tokenizer(rendered, add_special_tokens=False, return_offsets_mapping=True)
    ids = list(encoded['input_ids'])
    assert ids == tokenizer.apply_chat_template(messages, tokenize=True,
        add_generation_prompt=True, enable_thinking=protocol['enable_thinking'])
    ranges = []
    cursor = 0
    for message, local in zip(messages, spans):
        text = message['content']
        if not text:
            continue
        header = '<|im_start|>' + message['role'] + '\n'
        body_start = rendered.index(header, cursor)+len(header)
        kept_start, kept_end = 0, len(text)
        if rendered.startswith(text, body_start):
            start = body_start
        else:
            stripped = text.strip()
            assert stripped and rendered.startswith(stripped, body_start), 'Undeclared chat-template transformation'
            kept_start = len(text)-len(text.lstrip())
            kept_end = len(text.rstrip())
            start = body_start-kept_start
        assert rendered.startswith('<|im_end|>', start+kept_end)
        for a, b, category, kind in local:
            a, b = max(a, kept_start), min(b, kept_end)
            if b > a:
                ranges.append({'start': start+a, 'end': start+b,
                               'category': category, 'segment_type': kind})
        cursor = start+kept_end+len('<|im_end|>')
    categories = []
    boundary = 0
    special = set(tokenizer.all_special_ids)
    for token, (a, b) in zip(ids, encoded['offset_mapping']):
        matches = [r for r in ranges if r['start'] <= a < b <= r['end']]
        overlap = any(a < r['end'] and b > r['start'] for r in ranges)
        if token in special or b <= a:
            matches = []
        assert len(matches) <= 1
        categories.append(matches[0]['category'] if matches else 'framing')
        boundary += int(overlap and not matches and b > a and token not in special)
    assert len(categories) == len(ids)
    return {'messages': messages, 'prompt_text': rendered, 'prompt_token_ids': ids,
            'prompt_ids_sha256': digest(ids), 'character_spans': ranges,
            'token_categories': categories, 'boundary_tokens': boundary,
            'wrapped_query': wrapped}
