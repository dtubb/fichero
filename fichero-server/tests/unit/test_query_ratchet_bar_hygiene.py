"""A bar may only exist for something that was actually measured (#4487).

The 173-zero incident (2026-08-02): 173 of 476 query-count bars said 0 —
"best ever: zero queries" for endpoints like POST /api/library that cannot
touch the database fewer than hundreds of times. The zeros were written by
requests served through a MOCKED DB layer: the ``mock_db`` fixture patches
``db_manager.get_database``, the route runs, the counter counts nothing, and
the middleware recorded that nothing as a measurement. Every later REAL run
then "regressed" against an unachievable bar.

Three facts that must never share a representation, proven here in bytes:

* an endpoint NOT exercised            -> NO bar
* exercised with the instrument DEAD   -> NO bar (mocked DB layer)
* exercised, instrument live, 0 queries -> a bar of 0 (a genuine zero is a
  real measurement worth holding — /api/health may honestly be 0; refusing
  to ever write 0 would be the wrong fix)

Plus the partial-run decision: an INTERRUPTED session (pytest exit code 2)
flushes nothing — every bar a partial run writes is a claim made by a
session that did not finish (the killed-at-34% harvest).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def _root_conftest():
    """The loaded tests/conftest.py, by file path (see perf/conftest.py)."""
    root_path = (Path(__file__).resolve().parents[1] / "conftest.py").resolve()
    for module in list(sys.modules.values()):
        if getattr(module, "__file__", None) and Path(module.__file__).resolve() == root_path:
            return module
    raise RuntimeError("tests/conftest.py not loaded")


@pytest.fixture()
def ratchet(monkeypatch, tmp_path):
    """perf_ratchet pointed at a throwaway baseline, session cleared."""
    import perf_ratchet

    monkeypatch.setattr(perf_ratchet, "BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.delenv("FICHERO_PERF_NO_HISTORY", raising=False)
    perf_ratchet._query_session.clear()
    yield perf_ratchet
    perf_ratchet._query_session.clear()


class TestFlushWritesOnlyWhatWasMeasured:
    def test_an_unexercised_endpoint_gets_no_bar(self, ratchet):
        """flush writes ONLY what note_query_count recorded — an endpoint
        nothing hit must not appear, at any count, least of all 0."""
        ratchet.note_query_count("queries.GET./api/exercised", 3)
        ratchet.flush_query_session()

        data = json.loads(ratchet.BASELINE_PATH.read_text())
        assert "queries.GET./api/exercised" in data
        assert all(k == "queries.GET./api/exercised" for k in data), (
            f"bars appeared for endpoints never noted: {sorted(data)}"
        )

    def test_a_genuine_zero_is_recorded_and_held(self, ratchet):
        """Refusing to write 0 would be the wrong fix — a real endpoint that
        issues no queries has a real bar, and a regression FROM 0 counts."""
        ratchet.note_query_count("queries.GET./api/health", 0)
        assert ratchet.flush_query_session() == []
        data = json.loads(ratchet.BASELINE_PATH.read_text())
        assert data["queries.GET./api/health"]["count"] == 0

        ratchet.note_query_count("queries.GET./api/health", 2)
        regressions = ratchet.flush_query_session()
        assert regressions and "2 queries vs best 0" in regressions[0]


class TestTheMiddlewareKnowsWhenItsInstrumentIsDead:
    """The writer-side fix: 'exercised' means the query counter was in the
    request's path, not merely that the route returned."""

    def _hit(self, monkeypatch, ratchet, mock_db_layer: bool):
        """Drive the middleware FUNCTION directly with a stub request.

        Not via TestClient on the shared app: re-executing conftest after
        the app has served a request raises "Cannot add middleware after an
        application has started", so an app-level version of this test is
        order-dependent. The guard under test lives entirely inside
        ``_count_queries_per_request``; a stub request exercises it exactly.
        """
        import asyncio
        from types import SimpleNamespace

        conftest = _root_conftest()
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        if mock_db_layer:
            # Exactly what the mock_db fixture does: replace the DB layer.
            from unittest.mock import MagicMock

            monkeypatch.setattr(
                conftest.db_manager, "get_database", lambda _path: MagicMock()
            )

        request = SimpleNamespace(
            method="GET",
            scope={"route": SimpleNamespace(path="/api/health")},
        )

        async def call_next(_request):
            return SimpleNamespace(status_code=200)

        asyncio.run(conftest._count_queries_per_request(request, call_next))
        return dict(ratchet._query_session)

    def test_a_request_through_a_mocked_db_layer_writes_no_bar(
        self, monkeypatch, ratchet
    ):
        session = self._hit(monkeypatch, ratchet, mock_db_layer=True)
        assert not any(k.startswith("queries.") for k in session), (
            f"a mocked-DB request was recorded as a measurement: {session} — "
            "this is how POST /api/library acquired 'best 0' (#4487)"
        )

    def test_the_same_request_through_the_real_layer_IS_recorded(
        self, monkeypatch, ratchet
    ):
        """The guard must not eat genuine measurements — same request, real
        DB layer, a bar appears (0 is fine; absent is the defect)."""
        session = self._hit(monkeypatch, ratchet, mock_db_layer=False)
        assert "queries.GET./api/health" in session, (
            "the real-layer request recorded nothing — the mock guard is "
            "over-broad and the ratchet just went blind the polite way"
        )


class TestInterruptedRunsWriteNothing:
    def test_sessionfinish_flushes_nothing_on_exitstatus_2(
        self, monkeypatch, ratchet
    ):
        conftest = _root_conftest()
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        calls: list[str] = []
        monkeypatch.setattr(
            ratchet, "flush_session", lambda: calls.append("timing") or []
        )
        monkeypatch.setattr(
            ratchet, "flush_query_session", lambda: calls.append("queries") or []
        )
        monkeypatch.setattr(
            ratchet,
            "flush_session_memory",
            lambda scope: calls.append("memory") or ([], "ok"),
        )

        conftest.pytest_sessionfinish(session=None, exitstatus=2)

        assert calls == [], (
            "an INTERRUPTED session flushed ratchet state — every bar a "
            "partial run writes is a claim made by a session that did not "
            "finish (the killed-at-34% harvest, #4487)"
        )
