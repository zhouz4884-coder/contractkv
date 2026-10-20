"""Trusted-controller cache identities for both native Raw APC and certified KV.

This is an internal authorization adapter, not public caller authentication or a
complete tenant isolation boundary. Operator content labels remain trusted.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import json


class CacheAuthorizationError(ValueError):
    pass


@dataclass(frozen=True)
class CacheIdentity:
    principal: str
    authorization_domain: str
    service_epoch: int
    template_identity: str
    engine_identity: str
    policy_identity: str
    cache_salt: str = field(repr=False)


class CacheAuthority:
    def __init__(self, secret, engine_identity, policy_identity, active_epochs, memberships):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError('A controller-only key of at least 256 bits is required')
        if not engine_identity or not policy_identity:
            raise ValueError('Engine and policy identities must be explicit')
        self._secret = secret
        self.engine_identity = engine_identity
        self.policy_identity = policy_identity
        self._epochs = dict(active_epochs)
        self._memberships = {k: frozenset(v) for k, v in memberships.items()}
        if not self._epochs or any(not k or type(v) is not int or v < 0 for k, v in self._epochs.items()):
            raise ValueError('Active authorization epochs are required')

    def _salt(self, domain, epoch, template):
        value = dict(version='contractkv.authorized-cache.v1', domain=domain,
                     service_epoch=epoch, template=template,
                     engine=self.engine_identity, policy=self.policy_identity)
        body = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
        return 'ckv-auth-v1:' + hmac.new(self._secret, body, hashlib.sha256).hexdigest()

    def bind(self, principal, authorization_domain, requested_epoch, template_identity):
        # Principal/domain/epoch are already authenticated controller inputs.
        if authorization_domain not in self._memberships.get(principal, ()):
            raise CacheAuthorizationError('principal_not_authorized_for_domain')
        if type(requested_epoch) is not int or requested_epoch != self._epochs.get(authorization_domain):
            raise CacheAuthorizationError('inactive_or_stale_request_epoch')
        if not isinstance(template_identity, str) or not template_identity:
            raise CacheAuthorizationError('missing_template_identity')
        return CacheIdentity(principal, authorization_domain, requested_epoch, template_identity,
                             self.engine_identity, self.policy_identity,
                             self._salt(authorization_domain, requested_epoch, template_identity))

    def require(self, identity):
        if not isinstance(identity, CacheIdentity):
            raise CacheAuthorizationError('explicit_cache_identity_required')
        expected = self.bind(identity.principal, identity.authorization_domain,
                             identity.service_epoch, identity.template_identity)
        if (identity.engine_identity != expected.engine_identity or
                identity.policy_identity != expected.policy_identity or
                not hmac.compare_digest(identity.cache_salt, expected.cache_salt)):
            raise CacheAuthorizationError('cache_identity_binding_mismatch')
        return identity.cache_salt

    def advance_epoch(self, authorization_domain, new_epoch):
        # Trusted lifecycle control, not a client-provided new epoch.
        current = self._epochs.get(authorization_domain)
        if current is None or type(new_epoch) is not int or new_epoch <= current:
            raise CacheAuthorizationError('epoch_must_advance_monotonically')
        self._epochs[authorization_domain] = new_epoch
