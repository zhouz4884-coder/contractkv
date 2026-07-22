"""Compatibility shim for LMCache 0.3.9 CacheBlend on vLLM 0.10.2.

LMCache constructs its blender while vLLM initializes the KV connector, before
GPUModelRunner.load_model has installed the model object.  Delay only blender
construction, then register the actual model immediately after vLLM loads it.
The cache lookup, layerwise transfer, and blend implementation remain LMCache's.
"""

from __future__ import annotations

import os


if os.environ.get("CONTRACTKV_LMCACHE_CACHEBLEND_COMPAT") == "1":
    try:
        from lmcache.integration.vllm.utils import ENGINE_NAME
        from lmcache.v1.compute.blend.utils import LMCBlenderBuilder
        from lmcache.v1.compute.models.utils import VLLMModelTracker
        from vllm.v1.worker.gpu_model_runner import GPUModelRunner
    except ModuleNotFoundError:
        # vLLM may spawn helper interpreters outside the LMCache environment.
        # They do not construct the connector and must not fail at startup.
        pass
    else:

        _original_get_or_create = LMCBlenderBuilder.get_or_create
        _original_load_model = GPUModelRunner.load_model

        class _DeferredBlender:
            def __init__(self, instance_id, cache_engine, gpu_connector, config):
                self._args = (instance_id, cache_engine, gpu_connector, config)

            def blend(self, *args, **kwargs):
                blender = _original_get_or_create(*self._args)
                return blender.blend(*args, **kwargs)

        def _deferred_get_or_create(cls, instance_id, cache_engine, gpu_connector, config):
            try:
                VLLMModelTracker.get_model(instance_id)
            except ValueError:
                return _DeferredBlender(instance_id, cache_engine, gpu_connector, config)
            return _original_get_or_create(instance_id, cache_engine, gpu_connector, config)

        def _load_and_register(self, *args, **kwargs):
            result = _original_load_model(self, *args, **kwargs)
            VLLMModelTracker.register_model(ENGINE_NAME, self.model)
            return result

        LMCBlenderBuilder.get_or_create = classmethod(_deferred_get_or_create)
        GPUModelRunner.load_model = _load_and_register
