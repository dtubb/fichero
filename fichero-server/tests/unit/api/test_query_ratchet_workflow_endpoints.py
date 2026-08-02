"""#4462 — prove the query-count ratchet actually sees workflow DB access.

`fichero_server.core.duckdb_session.connect_utc` is the one chokepoint the
ratchet's counting wrap (#4443) attaches to. `workflows/tasks.py`,
`workflows/scheduler.py`, and `workflows/activity_store.py` all route through
it (grep confirms no bare `duckdb.connect` remains outside `connect_utc`
itself) — but #4462 was filed because routing through the right function is
not sufficient proof on its own: the counter was ALREADY once silently blind
end-to-end (the Starlette-threadpool context-copy bug) while every unit test
of the wrap in isolation stayed green. "A counter returning 0 looks identical
to an efficient route" (#4462) — so this drives a REAL endpoint, not the
connection object directly, with a REAL (unmocked) `TaskQueue` backed by a
real DuckDB file, through the actual FastAPI middleware stack, and reads the
result back the way the ratchet itself does: from
`perf_ratchet._query_session`, not from `duckdb_session.get_query_count()`
in the test's own thread.

That distinction is load-bearing, not stylistic: `get_query_count()` reads a
`ContextVar`, and `TestClient.get()` dispatches the request onto a *different*
thread/context than the test body runs in. Calling `get_query_count()` after
`client.get()` returns reads the TEST's own (never-set) context, not the
request's — it silently reports 0 regardless of whether the endpoint was
counted, which is exactly the false-green shape #4462 warns about. The
middleware under test (`_count_queries_per_request` in conftest.py) sidesteps
this correctly by reading the count *inside* the request's own context and
handing it to `perf_ratchet.note_query_count`, a plain module-level dict with
no context-var indirection — so that dict is the one place this test can
observe the real number from outside.
"""

from __future__ import annotations

import duckdb
from unittest.mock import patch

import perf_ratchet
from fichero_server.workflows import tasks as tasks_module
from fichero_server.workflows.tasks import TaskQueue

BASE = "/api/tasks"
_ROUTE_KEY = "queries.GET./api/tasks"


class TestQueryRatchetSeesRealTaskQueueTraffic:
    """`GET /api/tasks` with a real `TaskQueue` must count > 0 queries.

    `TaskQueue.__init__` creates its table via `connect_utc` before the
    request starts (so it's outside the per-request counter window by
    design); `list_tasks` issues a SELECT through `connect_utc` from inside
    the request. If either regresses to a bare `duckdb.connect`, this drops
    to 0 and the assertion catches it — the same failure shape #4462 warns
    is otherwise invisible.
    """

    def test_list_tasks_through_a_real_queue_is_counted(self, client, monkeypatch, tmp_path):
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        queue = TaskQueue(str(tmp_path / "ratchet_tasks.duckdb"))
        perf_ratchet._query_session.pop(_ROUTE_KEY, None)

        with patch(
            "fichero_server.api.routes.workflow.tasks.get_task_queue",
            return_value=queue,
        ):
            response = client.get(BASE)

        assert response.status_code == 200
        recorded = perf_ratchet._query_session.get(_ROUTE_KEY)
        assert recorded is not None and recorded > 0, (
            "a real /api/tasks request through a real TaskQueue counted 0 "
            "queries — the wrap has gone blind for workflow DB access "
            "(#4462), even though the endpoint plainly touches the DB"
        )
        perf_ratchet._query_session.pop(_ROUTE_KEY, None)


class TestTheGuardHasTeeth:
    """Synthesise the exact regression #4462 warns about — a call site that
    bypasses `connect_utc` for a bare `duckdb.connect` — and confirm the
    assertion above would have caught it, rather than trusting that it would.
    """

    def test_bypassing_connect_utc_is_caught_as_zero(self, client, monkeypatch, tmp_path):
        monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")
        queue = TaskQueue(str(tmp_path / "ratchet_tasks_bypass.duckdb"))
        perf_ratchet._query_session.pop(_ROUTE_KEY, None)

        # Route list_tasks's connect call around connect_utc, uncounted —
        # the shape of the bug #4462 was filed to prevent.
        monkeypatch.setattr(tasks_module, "connect_utc", duckdb.connect)

        with patch(
            "fichero_server.api.routes.workflow.tasks.get_task_queue",
            return_value=queue,
        ):
            response = client.get(BASE)

        assert response.status_code == 200
        recorded = perf_ratchet._query_session.get(_ROUTE_KEY)
        assert recorded == 0 or recorded is None, (
            "bypassing connect_utc was still counted — this test no longer "
            "proves what it claims to; re-derive the synthesised violation"
        )
        perf_ratchet._query_session.pop(_ROUTE_KEY, None)
