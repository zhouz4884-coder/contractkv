"""Validate a frozen exogenous wave-arrival table without consulting outcomes."""
import hashlib
import json
import math


def load_arrivals(path,sessions_sha256,expanded_session_ids,tenants,concurrency):
    raw=path.read_bytes();trace=json.loads(raw.decode('utf-8'))
    if trace['schema_version']!='tsc-r4.fixed-wave-arrivals.v1':raise ValueError('Arrival schema')
    if trace['sessions_sha256']!=sessions_sha256 or trace['tenants_per_template']!=tenants or trace['concurrency']!=concurrency:
        raise ValueError('Arrival input/runtime binding')
    expected={(start,turn):expanded_session_ids[start:start+concurrency] for start in range(0,len(expanded_session_ids),concurrency) for turn in range(10)}
    waves={};previous=-1.
    for row in trace['waves']:
        key=row['cohort_start'],row['turn'];value=row['ready_offset_s']
        if key in waves or key not in expected or row['session_ids']!=expected[key]:raise ValueError('Arrival membership/duplicate')
        if type(value) not in (int,float) or not math.isfinite(value) or value<0 or value<previous:raise ValueError('Nonmonotonic/invalid arrival offset')
        previous=value;waves[key]=row
    if set(waves)!=set(expected) or list(waves)!=list(expected):raise ValueError('Arrival coverage/order')
    if trace['actual_business_requests']!=len(expanded_session_ids)*10:raise ValueError('Arrival count')
    return waves,hashlib.sha256(raw).hexdigest(),trace
