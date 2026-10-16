"""Optional Python-output syntax admission; never rewrites or scores responses."""
import ast
import re
import textwrap
import time
from scripts.tsc_revision_r2_admission import SingleShotRegistrar

def python_statement_contract(text):
    answer=re.sub(r'<think>.*?</think>','',text,flags=re.S).strip()
    if answer.startswith('```') and answer.endswith('```'):
        answer=re.sub(r'^```(?:python|py)?\s*','',answer);answer=answer[:-3].strip()
    try:tree=ast.parse(textwrap.dedent(answer))
    except (SyntaxError,ValueError) as error:return {'passed':False,'reason':'python_syntax_'+type(error).__name__}
    if len(tree.body)!=1:return {'passed':False,'reason':'expected_one_complete_python_statement'}
    return {'passed':True,'reason':'one_parseable_python_statement'}

class OutputContractRegistrar(SingleShotRegistrar):
    def register(self,args,namespace,scope,business,gate,record=lambda row:None):
        key=(namespace,scope)
        with self.lock:already=key in self.decisions or key in self.reserved
        if already:return super().register(args,namespace,scope,business,gate,record)
        started=time.perf_counter();checked=False
        if gate.get('allow_verification') and gate.get('output_contract')=='one_python_statement':
            checked=True
            check=python_statement_contract(business['output_text'])
            record({'row_type':'output_contract_check','certificate_namespace':namespace,'query_scope':scope,
                    'contract':'one_python_statement','check':check,'output_unchanged':True})
            if not check['passed']:gate={**gate,'allow_verification':False,'reason':'raw_output_contract:'+check['reason']}
        check_ms=(time.perf_counter()-started)*1000 if checked else 0
        result=super().register(args,namespace,scope,business,gate,record)
        if 'complete_verification_ms' not in result:return result
        result['output_contract_check_ms']=check_ms
        result['complete_verification_ms']+=check_ms
        if 'post_business_registration_ms' in result:result['post_business_registration_ms']+=check_ms
        return result
