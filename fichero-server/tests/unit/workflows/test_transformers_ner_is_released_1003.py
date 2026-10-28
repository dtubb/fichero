"""The cached Transformers NER pipeline is released with the other models (## 1003, #4999 `activity.lane.idle-unload`): it is ~1 GB with
torch and nothing freed it until quit."""
from __future__ import annotations

import asyncio
import sys
import time
from types import SimpleNamespace

import pytest

from fichero_server.db import embeddings
from fichero_server.workflows.ner import providers
from fichero_server.workflows.ner.providers import TransformersNERProvider, clear_transformers_pipelines

MODEL = "dslim/bert-base-NER"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(TransformersNERProvider, "_build_pipeline", lambda self: (lambda text: []))
    clear_transformers_pipelines()
    yield
    clear_transformers_pipelines()


def _load():
    asyncio.run(TransformersNERProvider().extract("Don Juan de Mosquera vendió una casa."))


def test_the_embedders_pressure_path_releases_it_and_gives_the_gpu_buffers_back(monkeypatch):
    emptied = []
    torch = SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)),
                            mps=SimpleNamespace(empty_cache=lambda: emptied.append(True)))
    monkeypatch.setitem(sys.modules, "torch", torch)
    _load()
    assert MODEL in providers._TRANSFORMERS_PIPELINES
    released = embeddings.release_idle_embedders(idle_seconds=0, reason="another model needs the memory")
    assert MODEL in released and providers._TRANSFORMERS_PIPELINES == {}, "the pressure path left the pipeline loaded"
    assert emptied, "the GPU's cached buffers were not given back"
    _load()  # and the next extract loads it again
    assert MODEL in providers._TRANSFORMERS_PIPELINES


def test_one_in_use_or_used_a_moment_ago_is_kept_until_it_has_been_idle_long_enough():
    _load()
    assert providers.release_idle_transformers(idle_seconds=600) == [], "a pipeline used just now was released"
    providers._TRANSFORMERS_IN_USE[MODEL] = 1  # an extract holds it
    assert providers.release_idle_transformers(idle_seconds=0) == [], "a pipeline an extract holds was released"
    providers._TRANSFORMERS_IN_USE[MODEL] = 0
    providers._TRANSFORMERS_LAST_USE[MODEL] = time.monotonic() - 601
    assert providers.release_idle_transformers(idle_seconds=600) == [MODEL]


def test_the_idle_thread_releases_it_after_the_idle_spell(monkeypatch):
    monkeypatch.setattr(embeddings, "EMBEDDER_IDLE_SECONDS", 0.2)
    monkeypatch.setattr(providers, "_TRANSFORMERS_RELEASER", None)  # an earlier test's thread is asleep on the long interval
    _load()
    deadline = time.monotonic() + 10
    while providers._TRANSFORMERS_PIPELINES and time.monotonic() < deadline:
        time.sleep(0.05)
    assert providers._TRANSFORMERS_PIPELINES == {}, "the idle thread never released the pipeline"
