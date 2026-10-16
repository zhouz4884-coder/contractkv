"""Optional CPU metadata traces for diagnostic model-runner/verification paths."""
import json
import os
import time


def emit_trace(environment_variable,event):
    path=os.environ.get(environment_variable)
    if not path: return
    record={'timestamp':time.time(),'pid':os.getpid(),**event}
    with open(path,'a',encoding='utf-8') as stream:
        stream.write(json.dumps(record,separators=(',',':'))+'\n')
