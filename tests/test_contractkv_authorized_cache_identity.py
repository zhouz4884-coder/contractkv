from dataclasses import replace
from types import SimpleNamespace
import pytest
from scripts.contractkv_cache_identity import CacheAuthority, CacheAuthorizationError
from scripts import contractkv_authorized_requests as requests
from tests.test_tsc_revision_r2_admission import fixture


def authority():
    return CacheAuthority(b'x' * 32, 'model/runtime', 'policy', {'A': 1, 'B': 1},
                          {'alice': {'A'}, 'alice2': {'A'}, 'bob': {'B'}})


def test_same_authorized_group_shares_but_domains_templates_and_epochs_do_not():
    a = authority()
    x = a.bind('alice', 'A', 1, 'template')
    assert x.cache_salt == a.bind('alice2', 'A', 1, 'template').cache_salt
    assert x.cache_salt != a.bind('bob', 'B', 1, 'template').cache_salt
    assert x.cache_salt != a.bind('alice', 'A', 1, 'other-template').cache_salt
    a.advance_epoch('A', 2)
    with pytest.raises(CacheAuthorizationError, match='stale'):
        a.require(x)
    assert x.cache_salt != a.bind('alice', 'A', 2, 'template').cache_salt


def test_untrusted_domain_missing_identity_and_forged_salt_fail_before_dispatch():
    a = authority()
    with pytest.raises(CacheAuthorizationError):
        a.bind('bob', 'A', 1, 't')
    with pytest.raises(CacheAuthorizationError):
        a.require(None)
    x = a.bind('alice', 'A', 1, 't')
    with pytest.raises(CacheAuthorizationError):
        a.require(replace(x, cache_salt='chosen-by-caller'))
    with pytest.raises(CacheAuthorizationError):
        a.require(replace(x, engine_identity='other-runtime'))
    with pytest.raises(CacheAuthorizationError):
        a.advance_epoch('A', 1)


def test_raw_fallback_and_compiled_business_have_the_same_required_salt(monkeypatch):
    a = authority()
    x = a.bind('alice', 'A', 1, 't')
    observed = []
    monkeypatch.setattr(requests, 'business_generate', lambda *args, **kwargs: observed.append(kwargs))
    for messages in ([{'role': 'user', 'content': 'raw'}], [{'role': 'user', 'content': 'compiled'}]):
        requests.authorized_business_generate(a, x, SimpleNamespace(), messages, 64, 'id')
    assert [r['salt'] for r in observed] == [x.cache_salt] * 2
    a.advance_epoch('A', 2)
    with pytest.raises(CacheAuthorizationError):
        requests.authorized_business_generate(a, x, SimpleNamespace(), [], 64, 'stale')
    assert len(observed) == 2


def test_verification_wire_and_log_identity_match_and_rejection_does_not_retry():
    a = authority()
    x = a.bind('alice', 'A', 1, 't')
    calls, log = [], []
    def reject(url, payload, timeout):
        assert log[-1]['payload'] == payload
        calls.append(payload)
        return {'certificate_issued': False, 'committed_tokens': 0, 'failure_reason': 'actual-reject'}
    args, witness, gate = fixture()
    reg = requests.AuthorizedRegistrar(.0625, .125, a, x, poster=reject)
    first = reg.register(args, 'namespace', 'scope', witness, gate, record=log.append)
    assert reg.register(args, 'namespace', 'scope', witness, gate) is first
    assert len(calls) == 1 and calls[0]['cache_salt'] == x.cache_salt
    assert calls[0]['policy_hash'] == args.policy_hash
    assert not first['certificate_issued'] and first['attempts'][0]['committed_tokens'] == 0
    assert requests.REGISTRAR_ADAPTER_PROOF['all_other_registration_AST_identical']


def test_margin_and_epoch_guards_still_precede_GPU_calls():
    a = authority()
    x = a.bind('alice', 'A', 1, 't')
    calls = []
    reg = requests.AuthorizedRegistrar(.0625, .125, a, x, poster=lambda *args: calls.append(args))
    args, witness, gate = fixture()
    witness['reference_margins'][0] = .001
    result = reg.register(args, 'n', 'q', witness, gate)
    assert not result['certificate_issued'] and calls == []
    a.advance_epoch('A', 2)
    with pytest.raises(CacheAuthorizationError):
        reg.register(args, 'n', 'new-q', witness, gate)
    assert calls == []
