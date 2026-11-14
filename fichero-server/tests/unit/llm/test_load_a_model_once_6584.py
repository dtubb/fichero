"""One loaded instance of a Kraken model per engine, shared by every page that asks (#6584,
`activity.limits.load-a-model-once`). Spec: docs/contributor_manual/specs/ui/activity-pane.md. WHY (owner 2026-11-13): never
five copies of the Kraken model for five pages. The runtime's resident cache under its load lock is the one place; pinned here
with a counting loader: twenty pages across three runs' threads load the model exactly once, and a replacement unloads the old.
"""
from __future__ import annotations

import threading

from fichero_server.llm import kraken_runtime


def test_twenty_pages_across_three_runs_load_the_model_once(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "_RESIDENT", {})
    loads: list[str] = []
    lock = threading.Lock()

    def load():
        with lock:
            loads.append("blla")
        return object()

    got: list[object] = []

    def a_run(pages: int):
        for _ in range(pages):
            got.append(kraken_runtime._resident("segment", "blla", load))

    threads = [threading.Thread(target=a_run, args=(7,)) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)

    assert len(loads) == 1, f"the model was loaded {len(loads)} times for 21 pages"
    assert len({id(m) for m in got}) == 1, "every page got the one instance"


def test_another_model_of_the_same_kind_replaces_the_held_one_never_sits_beside_it(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "_RESIDENT", {})
    kraken_runtime._resident("read", "model-a", object)
    kraken_runtime._resident("read", "model-b", object)
    assert set(kraken_runtime._RESIDENT) == {"read"} and kraken_runtime._RESIDENT["read"][0] == "model-b"
