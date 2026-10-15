from scripts.tsc_revision_r3_output_contract import python_statement_contract
from scripts.tsc_revision_r3_output_contract import OutputContractRegistrar
from types import SimpleNamespace

def test_invalid_concatenation_rejected_without_gold_or_rewriting():
    value='<think>\n\n</think>\n\ntest_dataset = NYUDepthV2Dataset(data_path=config["data_path"]) return test_dataset'
    assert not python_statement_contract(value)['passed']
    assert python_statement_contract('return test_dataset')['passed']
    assert python_statement_contract('x = create_dataset(path)')['passed']

def test_conservative_complete_statement_subset():
    assert not python_statement_contract('x=1\ny=2')['passed']
    assert not python_statement_contract('x = (')['passed']
    assert python_statement_contract('```python\nreturn x\n```')['passed']

def test_invalid_real_failure_shape_abstains_before_any_rpc_and_never_retries():
    calls=[];r=OutputContractRegistrar(.0625,.125,lambda *args:calls.append(args))
    gate={'allow_verification':True,'output_contract':'one_python_statement','plan':{
        'stable_prefix_end_token':16,'stable_content_hash':'h','cpu_http_preparation_ms':0}}
    business={'output_text':'test_dataset = make_dataset() return test_dataset'}
    first=r.register(SimpleNamespace(),'namespace','scope',business,gate)
    cost=first['complete_verification_ms']
    second=r.register(SimpleNamespace(),'namespace','scope',business,gate)
    assert not first['certificate_issued'] and not first['attempts'] and calls==[]
    assert first is second and second['complete_verification_ms']==cost
    assert business['output_text']=='test_dataset = make_dataset() return test_dataset'
