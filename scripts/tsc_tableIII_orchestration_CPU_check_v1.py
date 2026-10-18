"""Safety/argument checks for orchestration, with no model or GPU calls."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
import importlib.util,json,signal,sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'results/tsc_tableIII_fullcost_replay_20261018'
spec=importlib.util.spec_from_file_location('worker',ROOT/'scripts/tsc_tableIII_fullcost_worker_v1.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

class SafetyChecks(unittest.TestCase):
    def test_original_protocol_arguments(self):
        protocol=json.loads((STUDY/'protocol_v1.json').read_text(encoding='utf-8'))
        for model in protocol['models']:
            for repeat in [1,2,3]:
                for policy in ['raw','contract']:
                    args=w.original_args(ROOT,model,repeat,policy,ROOT/'dummy_cell',8960)
                    fields={args[i]:args[i+1] for i in range(0,len(args),2)}
                    self.assertEqual(fields['--stable-word-limit'],str(model['stable_word_limit']))
                    self.assertEqual(fields['--max-tokens'],str(model['max_tokens']))
                    self.assertEqual(fields['--tool-slack-ms'],str(model['historical_slack_ms']))
                    self.assertEqual(fields['--timeout'],'600' if model['key']=='qwen14' else '300')
                    if model['key']=='llama':
                        self.assertEqual(fields['--stable-pieces'],'16')
                        self.assertEqual(fields['--mode'],'frozen' if policy=='contract' else 'raw')
                        self.assertEqual('--qualification-manifest' in fields,policy=='contract')
                        self.assertEqual(fields['--layout-ladder'],'L0=0.0,L1=0.25,L2=0.75,L3=1.0')
                    else:self.assertEqual(fields['--policy'],'contractkv-full' if policy=='contract' else 'raw-order')
    def test_foreign_GPU_PID_is_not_owned(self):
        with patch.object(w.os,'getpgid',side_effect=lambda pid:{11:100,12:200}[pid],create=True):
            self.assertEqual(w.foreign_pids({'processes':[['11','ours'],['12','other']]},{100}),[12])
    def test_cleanup_refuses_a_different_group(self):
        with patch.object(w.os,'getpgid',return_value=999,create=True),patch.object(w.os,'killpg',create=True) as kill:
            with self.assertRaises(AssertionError):w.stop_own_group(SimpleNamespace(pid=123))
            kill.assert_not_called()
    def test_cleanup_own_group_when_API_parent_is_gone(self):
        calls=[]
        def kill(group,sig):
            calls.append((group,sig))
            if sig==0:raise ProcessLookupError()
        with patch.object(w.os,'getpgid',side_effect=ProcessLookupError(),create=True),patch.object(w.os,'killpg',side_effect=kill,create=True):
            w.stop_own_group(SimpleNamespace(pid=123))
        self.assertEqual(calls,[(123,signal.SIGTERM),(123,0)])
    def test_busy_resources_prevent_preflight_and_launch(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.artifacts') as d:
            root=Path(d);study=root/w.STUDY_REL;study.mkdir(parents=True)
            (study/'protocol_v1.json').write_text(json.dumps({'archived_source_files':[],'input_files':[]}))
            (study/'freeze_v1.json').write_text(json.dumps({'files':[]}))
            (study/'launch_addendum_v1.json').write_text(json.dumps({'files':[]}))
            busy={'time_utc':'fixture','processes':[['12','another-study']]}
            with patch.object(w.sys,'platform','linux'),patch.object(w,'DISK',root),patch.object(w,'resource_snapshot',return_value=busy),\
                 patch.object(w.os,'getpgid',return_value=200,create=True),patch.object(w,'full_model_registry') as model_check,\
                 patch.object(w.subprocess,'Popen') as launch,patch.object(w.sys,'argv',['worker','--root',str(root),'--mode','execute']):
                self.assertEqual(w.main(),75)
                model_check.assert_not_called();launch.assert_not_called()
            self.assertFalse((study/'launch_attempt1_preflight').exists())

def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SafetyChecks)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    record={'status':'PASS' if result.wasSuccessful() else 'FAIL','tests_run':result.testsRun,
        'checks':['Frozen model/policy/timeout arguments across 24 cells','Reject foreign GPU PID','Never signal a different process group',
                  'Clean owned orphan children after API parent exit','Busy resource gate prevents both model preflight and server launch'],
        'GPU_model_calls':0,'evidence_type':'CPU infrastructure tests, not LLM correctness or latency results'}
    (STUDY/'orchestration_CPU_check_v1.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record));return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
