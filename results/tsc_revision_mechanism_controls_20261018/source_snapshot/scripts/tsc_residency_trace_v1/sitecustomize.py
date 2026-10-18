"""Opt-in diagnostic hooks; call the original backend methods unchanged.

Only used by the separately frozen known-source residency experiment. The
extra synchronous I/O makes every timing unsuitable for performance claims.
"""
import contextvars
import functools
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
from pathlib import Path
import sys
import time


_request = contextvars.ContextVar('residency_request', default=None)
_seq = 0


def emit(event, **fields):
    global _seq
    _seq += 1
    row = dict(event=event, seq=_seq, epoch_s=time.time(), perf_s=time.perf_counter(),
               pid=os.getpid(), request_id=_request.get(), **fields)
    with open(os.environ['CONTRACTKV_RESIDENCY_TRACE'], 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, separators=(',', ':'))+'\n')


def hashed(value):
    return None if value is None else bytes(value).hex()


def mapping(manager, request):
    groups = manager.get_blocks(request.request_id).blocks
    return [[dict(id=b.block_id, hash=hashed(b.block_hash), ref=b.ref_cnt)
             for b in group] for group in groups]


def install_pool(module):
    cls = module.BlockPool
    original = cls._maybe_evict_cached_block

    @functools.wraps(original)
    def evict(self, block):
        key = block.block_hash
        before = len(self.cached_block_hash_to_block.get(key, {})) if key is not None else 0
        block_id, ref = block.block_id, block.ref_cnt
        result = original(self, block)
        if key is not None:
            emit('native_evict_return', block_id=block_id, old_hash=hashed(key),
                 ref_before=ref, duplicate_entries_before=before,
                 duplicate_entries_after=len(self.cached_block_hash_to_block.get(key, {})),
                 removed=bool(result), free_blocks=self.get_num_free_blocks(),
                 pool_blocks=self.num_gpu_blocks)
        return result

    cls._maybe_evict_cached_block = evict


def install_manager(module):
    from vllm.v1.core.kv_cache_utils import make_block_hash_with_group_id
    cls = module.KVCacheManager
    original = cls.get_computed_blocks

    @functools.wraps(original)
    def lookup(self, request):
        context = _request.set(request.request_id)
        try:
            pool = self.block_pool
            keys = [make_block_hash_with_group_id(h, 0) for h in request.block_hashes]
            entries = [[[int(b.block_id), int(b.ref_cnt)] for b in
                        pool.cached_block_hash_to_block.get(k, {}).values()] for k in keys]
            spec = getattr(request, 'contractkv_verify_spec', None)
            emit('lookup_before', backend_cache_salt=request.cache_salt,
                 prompt_tokens=request.num_prompt_tokens, block_size=self.block_size,
                 kv_groups=self.num_kv_cache_groups, backend_hashes=[hashed(k) for k in keys],
                 cached_entries_by_block=entries, free_blocks=pool.get_num_free_blocks(),
                 pool_blocks=pool.num_gpu_blocks, verification=spec is not None,
                 stable_end=spec.stable_prefix_end_token if spec else None,
                 certified_boundary_count=len(getattr(self, 'contractkv_certified_prefixes', {}).get(
                     (request.cache_salt, os.environ.get('CONTRACTKV_POLICY_HASH', '')), {})))
            result = original(self, request)
            emit('lookup_return', hit_tokens=result[1],
                 hit_block_ids=[[b.block_id for b in g] for g in result[0].blocks])
            return result
        finally:
            _request.reset(context)

    cls.get_computed_blocks = lookup
    original_allocate = cls.allocate_slots

    @functools.wraps(original_allocate)
    def allocate(self, request, *args, **kwargs):
        context = _request.set(request.request_id)
        try:
            return original_allocate(self, request, *args, **kwargs)
        finally:
            _request.reset(context)

    cls.allocate_slots = allocate
    original_cache = cls.cache_blocks

    @functools.wraps(original_cache)
    def cache(self, request, num_computed_tokens):
        context = _request.set(request.request_id)
        try:
            result = original_cache(self, request, num_computed_tokens)
            if getattr(request, 'contractkv_verify_spec', None) is not None:
                emit('verification_cache_blocks_return', requested_tokens=num_computed_tokens,
                     computed_before_finalize=request.num_computed_tokens,
                     backend_cache_salt=request.cache_salt, blocks=mapping(self, request))
            return result
        finally:
            _request.reset(context)

    cls.cache_blocks = cache
    original_free = cls.free

    @functools.wraps(original_free)
    def free(self, request):
        context = _request.set(request.request_id)
        try:
            blocks = mapping(self, request)
            result = original_free(self, request)
            emit('request_free_return', blocks_before_free=blocks,
                 free_blocks=self.block_pool.get_num_free_blocks(),
                 pool_blocks=self.block_pool.num_gpu_blocks)
            return result
        finally:
            _request.reset(context)

    cls.free = free


class Loader(importlib.abc.Loader):
    def __init__(self, original, install):
        self.original, self.install = original, install

    def create_module(self, spec):
        return self.original.create_module(spec)

    def __getattr__(self, key):
        return getattr(self.original, key)

    def exec_module(self, module):
        self.original.exec_module(module)
        self.install(module)
        emit('diagnostic_hook_installed', module=module.__name__, path=module.__file__,
             source_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())


class Finder(importlib.abc.MetaPathFinder):
    targets = {'vllm.v1.core.block_pool': install_pool,
               'vllm.v1.core.kv_cache_manager': install_manager}

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.targets:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is not None and spec.loader is not None:
            spec.loader = Loader(spec.loader, self.targets[fullname])
        return spec


if os.environ.get('CONTRACTKV_RESIDENCY_TRACE'):
    sys.meta_path.insert(0, Finder())
