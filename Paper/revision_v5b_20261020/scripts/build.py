"""Build both manuscripts through the inspected no-shell-escape compiler."""
from pathlib import Path
import os,subprocess,sys

root=Path(__file__).resolve().parents[1]
env=os.environ.copy()
if os.name=='nt':
    candidate=Path(os.environ.get('LOCALAPPDATA',''))/'Programs/MiKTeX/miktex/bin/x64'
    if candidate.is_dir():env['PATH']=str(candidate)+os.pathsep+env['PATH']
for stem in ('contractkv_tsc_v5b','contractkv_supplement'):
    for repetition in range(3):
        result=subprocess.run([sys.executable,'-B',str(root/'scripts/compile.py'),
            str(root/(stem+'.tex')),'--recipe','pdflatex'],env=env,capture_output=True)
        (root/'audit'/f'{stem}_compile_pass{repetition+1}.txt').write_bytes(result.stdout+result.stderr)
        if result.returncode:
            print((result.stdout+result.stderr).decode(errors='replace')[-5000:])
            raise SystemExit(result.returncode)
    print(stem+': compiled successfully',flush=True)
