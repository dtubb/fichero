"""The Transformers NER pipeline's in-use count and its idle thread (## 1004, #4999 `activity.lane.idle-unload`, ## 1003):
a Stop that lands while the model loads must not leave the pipeline held for good, and the thread that releases idle
pipelines must not end while a new load believes it is running."""
from __future__ import annotations

from tests._this_thread import sleep_here
import asyncio
import threading
import time

import pytest

from fichero_server.workflows.ner import providers
from fichero_server.workflows.ner.providers import TransformersNERProvider, clear_transformers_pipelines

MODEL = "dslim/bert-base-NER"


@pytest.fixture(autouse=True)
def _fresh():
    clear_transformers_pipelines()
    providers._TRANSFORMERS_IN_USE.clear()
    yield
    clear_transformers_pipelines()
    providers._TRANSFORMERS_IN_USE.clear()


def test_a_stop_that_lands_while_the_model_loads_leaves_it_free_to_release(monkeypatch):
    loading, may_finish = threading.Event(), threading.Event()

    def slow_build(self):
        loading.set()
        may_finish.wait(10)
        return lambda text: []

    monkeypatch.setattr(TransformersNERProvider, "_build_pipeline", slow_build)

    async def go() -> None:
        task = asyncio.create_task(TransformersNERProvider().extract("Don Juan de Mosquera."))
        while not loading.is_set():
            await asyncio.sleep(0.01)
        task.cancel()  # Stop, mid-load
        with pytest.raises(asyncio.CancelledError):
            await task
        may_finish.set()  # the load thread carries on after the cancel and finishes

    asyncio.run(go())
    deadline = time.monotonic() + 10
    while MODEL not in providers._TRANSFORMERS_PIPELINES and time.monotonic() < deadline:
        time.sleep(0.02)
    assert MODEL in providers._TRANSFORMERS_PIPELINES, "the load never finished"
    assert not providers._TRANSFORMERS_IN_USE.get(MODEL), f"the cancelled extract still holds it: {providers._TRANSFORMERS_IN_USE}"
    assert providers.release_idle_transformers(idle_seconds=0) == [MODEL]


def test_the_idle_thread_that_decides_to_end_is_no_longer_the_running_one(monkeypatch):
    """The window: the thread has seen an empty cache and is about to return, a load starts, sees the thread alive, and starts none.
    So the decision to end and the forgetting of the thread are one step under the lock."""
    monkeypatch.setattr(providers.time, "sleep", sleep_here(lambda s: None))
    sentinel = threading.Thread(target=lambda: None)
    monkeypatch.setattr(providers, "_TRANSFORMERS_RELEASER", sentinel)
    providers._release_transformers_when_idle()  # the cache is empty: it ends
    assert providers._TRANSFORMERS_RELEASER is None, "an ended releaser is still the one a new load relies on"
