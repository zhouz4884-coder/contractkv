from scripts.tsc_template_task_serving_client_v1 import ready_latency,stats
from scripts.tsc_template_task_serving_worker_v1 import adapted_start

def test_registration_delay_is_charged_from_the_original_arrival():
    # Global epoch100, arrival110, registration completes111, first content112.
    # Backend send-relative TTFT must not replace the user's two-second wait.
    r=dict(first_time=112.,end_time=115.,ttft_ms=150.,latency_ms=3150.)
    assert ready_latency(r,110.)==(2000.,5000.)

def test_missing_first_content_is_not_a_zero_latency_success():
    assert ready_latency(dict(first_time=None,end_time=120.),110.)==(None,10000.)
    assert stats([])==dict(mean=None,p95=None,p99=None)

def test_runtime_and_GPU_knobs_are_preserved_in_serving_dispatch():
    _,proof=adapted_start()
    assert proof['all_other_server_AST_identical']
    assert proof['changed_assignments']==['cell','source','protocol','client']
