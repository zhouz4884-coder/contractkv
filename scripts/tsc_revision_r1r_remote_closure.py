"""Read-only closure of measured counts and owned remote GPU workers."""
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args(); root=a.root
    evidence=root/'results/tsc_revision_r1r'
    primary=json.loads((evidence/'validation/summary/completion_audit_v1.json').read_text())
    long=json.loads((evidence/'long_horizon/summary/completion_audit_v1.json').read_text())
    known=json.loads((evidence/'known_counterexamples/completion_audit_v1.json').read_text())
    owned=set(); pattern=re.compile(r'\((?:APIServer|EngineCore_DP\d+|Worker_TP\d+)\s+pid=(\d+)\)')
    for log in (root/'logs/tsc_revision_r1r').glob('*_server.log'):
        with log.open(encoding='utf-8',errors='replace') as stream:
            for line in stream:
                match=pattern.search(line)
                if match: owned.add(int(match.group(1)))
    query=subprocess.run(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],capture_output=True,text=True)
    resident={int(line.strip()) for line in query.stdout.splitlines() if line.strip().isdigit()}
    still_owned=sorted(owned&resident)
    snapshot=subprocess.run(['nvidia-smi','--query-gpu=index,name,uuid,memory.used,memory.total','--format=csv'],capture_output=True,text=True)
    supervisors={}
    for pid in (2334871,2340849,2343437,2360242,2369591):
        stat=Path('/proc')/str(pid)/'stat'
        if not stat.exists(): supervisors[str(pid)]='exited'; continue
        state=stat.read_text().rsplit(')',1)[1].split()[0]
        supervisors[str(pid)]='zombie_no_active_work' if state=='Z' else 'present_state_'+state
    record={'schema_version':'tsc-r1r.remote-closure.v1','timestamp':datetime.now(timezone.utc).isoformat(),
            'primary_cells':primary['complete_cells'],'primary_futures':primary['measured_futures'],
            'long_cells':long['complete_cells'],'long_actual_generations':long['actual_generations'],
            'known_policy_cells':known['complete_policy_cells'],'known_futures':known['future_generations'],
            'all_experimental_audits_complete':primary['experimental_execution_complete'] and long['execution_complete'] and known['execution_complete'],
            'gpu_process_query_success':query.returncode==0,'owned_resident_gpu_pids':still_owned,
            'other_resident_gpu_pids_not_modified':sorted(resident-owned),
            'owned_gpu_cleanup_verified':query.returncode==0 and not still_owned,
            'prior_supervisor_observations':supervisors,'gpu_snapshot':snapshot.stdout,
            'no_processes_stopped_by_this_audit':True,'local_byte_verification_and_git_publication_are_separate':True}
    (evidence/'remote_closure_v1.json').write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record))
    return 0 if record['all_experimental_audits_complete'] and record['owned_gpu_cleanup_verified'] else 2


if __name__=='__main__': raise SystemExit(main())
