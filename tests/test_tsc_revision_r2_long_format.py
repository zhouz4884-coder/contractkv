from scripts.tsc_revision_r2_long_format import scores
from scripts.tsc_revision_r2_long_format_summary import wire_schema
import json

def test_original_128_predicate_preserved_and_new_task_separate():
    original=json.dumps(list(range(1001,1129)))
    assert scores(original,128,1001)['original_128_score']['complete_correct_array']
    strings=json.dumps([str(x) for x in range(1001,1129)])
    assert not scores(strings,128,1001)['strict_plain_json_integer_sequence']
    longer=scores(json.dumps(list(range(1001,1161))),160,1001)
    assert longer['original_128_score'] is None and longer['separate_160_task_score']
    labeled=scores('[JSON_ARRAY]'+original,128,1001)
    assert not labeled['original_128_score']['complete_correct_array']

def test_primary_tolerant_fence_score_does_not_hide_strict_schema_failure():
    value='```json\n'+json.dumps(list(range(1001,1129)))+'\n```'
    result=scores(value,128,1001)
    assert result['original_128_score']['complete_correct_array']
    assert not result['strict_plain_json_integer_sequence']

def test_model_think_stripping_is_not_raw_wire_json_compliance():
    value='<think>\n\n</think>\n\n'+json.dumps(list(range(1001,1129)))
    assert scores(value,128,1001)['original_128_score']['complete_correct_array']
    assert scores(value,128,1001)['strict_plain_json_integer_sequence']
    assert not wire_schema(value,128,1001)
    assert wire_schema(json.dumps(list(range(1001,1129))),128,1001)
