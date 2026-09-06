"""Balanced background throttle ([[user-machine-always-useful]]).

The rule: a big import must never peg the machine. These pin the two levers —
a fraction-of-cores default that is env-configurable, and a best-effort QoS
drop that never raises — plus that the embedder actually receives the thread cap.
"""

from __future__ import annotations

import pytest

from fichero_server.core import background_compute as bc


class TestEmbedThreads:
    def test_default_is_about_half_the_cores(self, monkeypatch):
        monkeypatch.delenv("FICHERO_EMBED_THREADS", raising=False)
        monkeypatch.setattr(bc, "cpu_count", lambda: 8)
        assert bc.embed_threads() == 4

    def test_never_zero_on_a_single_core_box(self, monkeypatch):
        monkeypatch.delenv("FICHERO_EMBED_THREADS", raising=False)
        monkeypatch.setattr(bc, "cpu_count", lambda: 1)
        assert bc.embed_threads() == 1

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("FICHERO_EMBED_THREADS", "3")
        assert bc.embed_threads() == 3

    @pytest.mark.parametrize("bad", ["0", "-2", "not-a-number", ""])
    def test_bad_env_falls_back_to_default(self, monkeypatch, bad):
        monkeypatch.setenv("FICHERO_EMBED_THREADS", bad)
        monkeypatch.setattr(bc, "cpu_count", lambda: 8)
        assert bc.embed_threads() == 4


class TestEmbedConcurrency:
    def test_default_is_one(self, monkeypatch):
        monkeypatch.delenv("FICHERO_EMBED_WORKERS", raising=False)
        assert bc.embed_concurrency() == 1

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("FICHERO_EMBED_WORKERS", "2")
        assert bc.embed_concurrency() == 2


class TestBackgroundQoS:
    def test_is_best_effort_and_never_raises(self):
        # The whole point is that a throttle can't crash the worker it throttles.
        assert bc.set_background_qos() is None

    def test_nice_fallback_when_qos_unavailable(self, monkeypatch):
        # Force the non-darwin path; the nice fallback must also swallow failure.
        monkeypatch.setattr(bc, "sys", __import__("sys"))
        monkeypatch.setattr(bc.sys, "platform", "linux", raising=False)
        calls = {}

        def fake_setpriority(which, who, prio):
            calls["prio"] = prio

        monkeypatch.setattr(bc.os, "setpriority", fake_setpriority)
        bc.set_background_qos()
        assert calls["prio"] == 10  # niced down


class TestEmbedderReceivesThreadCap:
    def test_shared_embedder_is_built_with_the_thread_cap(self, monkeypatch):
        import sys
        import types

        from fichero_server.db import embeddings

        captured = {}

        class _FakeTextEmbedding:
            def __init__(self, model_name, cache_dir=None, threads=None, **kw):
                captured["threads"] = threads

        # fastembed is imported INSIDE the function; stub the module.
        fake_mod = types.ModuleType("fastembed")
        fake_mod.TextEmbedding = _FakeTextEmbedding
        monkeypatch.setitem(sys.modules, "fastembed", fake_mod)
        monkeypatch.setattr(bc, "embed_threads", lambda: 3)

        embeddings._EMBEDDER_CACHE.pop("unit-test-model", None)
        embeddings._get_shared_embedder("unit-test-model", "/tmp/cache")
        try:
            assert captured["threads"] == 3
        finally:
            embeddings._EMBEDDER_CACHE.pop("unit-test-model", None)
