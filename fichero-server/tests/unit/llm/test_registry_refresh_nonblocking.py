"""The model registry must never refresh on the caller's thread.

`_price_table()` is reached from `async def` route handlers (workflow cost
estimation, the provider-model catalogs) and from the runner's per-node cost
tally. The refresh is an HTTPS GET with a five-second timeout, so doing it
inline blocked the whole engine's event loop — once on a fresh install and
again every week. Fixed cost, identical answer: a large slice of "runs feel
slow for a single file" (Daniel, 2026-09-01).
"""

from __future__ import annotations

import threading

import fichero_server.llm.model_types as model_types


def test_the_refresh_runs_off_the_calling_thread(monkeypatch, tmp_path):
    calling_thread = threading.current_thread()
    seen: dict[str, object] = {}
    done = threading.Event()

    def _fake_refresh(cache):
        seen["thread"] = threading.current_thread()
        done.set()
        return False

    monkeypatch.setattr(model_types, "_refresh_registry_cache", _fake_refresh)
    monkeypatch.setattr(model_types, "_REFRESH_STARTED", False)

    model_types._schedule_registry_refresh(tmp_path / "model_prices.json")

    assert done.wait(timeout=5), "the refresh never ran"
    assert seen["thread"] is not calling_thread


def test_a_price_lookup_does_not_wait_on_the_network(monkeypatch, tmp_path):
    """The table answers from disk while the refresh is still in flight."""
    release = threading.Event()

    def _slow_refresh(cache):
        release.wait(timeout=5)
        return False

    monkeypatch.setattr(model_types, "_refresh_registry_cache", _slow_refresh)
    monkeypatch.setattr(model_types, "_REFRESH_STARTED", False)
    monkeypatch.setattr(model_types, "_PRICE_TABLE", None)
    monkeypatch.setattr(
        model_types, "_cached_registry_path", lambda: tmp_path / "absent.json"
    )

    # Would hang for the refresh's whole duration before the fix; now it
    # falls straight through to the vendored snapshot.
    table = model_types._price_table()
    release.set()

    assert isinstance(table, dict) and len(table) > 500


def test_the_refresh_is_scheduled_at_most_once(monkeypatch, tmp_path):
    calls: list[object] = []

    def _count(cache):
        calls.append(cache)
        return False

    monkeypatch.setattr(model_types, "_refresh_registry_cache", _count)
    monkeypatch.setattr(model_types, "_REFRESH_STARTED", False)

    for _ in range(5):
        model_types._schedule_registry_refresh(tmp_path / "model_prices.json")

    # Give the one thread a moment to land.
    for _ in range(50):
        if calls:
            break
        threading.Event().wait(0.02)
    assert len(calls) == 1
