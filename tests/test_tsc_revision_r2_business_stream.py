import json
import time
import pytest
from scripts.phase17_live_common import digest
from scripts.tsc_revision_r2_business_stream import consume_stream,StreamEvidenceError


def stream(prompt=[11,12],usage=None):
    rows=[{'id':'chatcmpl-test','prompt_token_ids':prompt,'choices':[{'delta':{'role':'assistant'}}]},
          {'id':'chatcmpl-test','choices':[{'delta':{'content':'answer'},'token_ids':[21]}]},
          {'id':'chatcmpl-test','choices':[{'delta':{},'token_ids':[22],'finish_reason':'stop'}]},
          {'id':'chatcmpl-test','choices':[],'usage':usage or {'prompt_tokens':2,'completion_tokens':2}}]
    return [f'data: {json.dumps(r)}\n'.encode() for r in rows]+[b'data: [DONE]\n']


def test_prompt_ids_are_taken_from_initial_metadata_chunk():
    result=consume_stream(stream(),'test',time.perf_counter())
    assert result['success']
    assert result['prompt_token_ids']==[11,12]
    assert result['prompt_ids_sha256']==digest([11,12])
    assert result['output_token_ids']==[21,22]


def test_missing_ids_are_never_filled_from_usage_count():
    with pytest.raises(StreamEvidenceError) as exc:
        consume_stream(stream(prompt=None),'test',time.perf_counter())
    assert exc.value.evidence['output_token_ids']==[21,22]
    assert exc.value.evidence['prompt_token_ids'] is None


def test_mismatched_usage_rejects_while_preserving_real_ids():
    with pytest.raises(StreamEvidenceError) as exc:
        consume_stream(stream(usage={'prompt_tokens':3,'completion_tokens':2}),'test',time.perf_counter())
    assert exc.value.evidence['prompt_token_ids']==[11,12]
    assert not exc.value.evidence['success']


def test_text_without_output_ids_is_not_complete_generation_evidence():
    lines=stream(usage={'prompt_tokens':2,'completion_tokens':0})
    for index in (1,2):
        row=json.loads(lines[index].decode()[5:]); row['choices'][0]['token_ids']=[]
        lines[index]=('data: '+json.dumps(row)+'\n').encode()
    with pytest.raises(StreamEvidenceError):
        consume_stream(lines,'test',time.perf_counter())
