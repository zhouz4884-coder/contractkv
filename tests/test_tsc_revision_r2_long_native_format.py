from scripts.tsc_revision_r2_long_native_format import template_options

def test_native_template_flag_is_explicit_condition_only():
    messages=[{'role':'system','content':'explicit'}]
    assert template_options('qwen3-8b',messages,'explicit')=={'enable_thinking':False}
    assert template_options('qwen3-8b',messages,'other') is None
    assert template_options('mistral7b',messages,'explicit') is None
