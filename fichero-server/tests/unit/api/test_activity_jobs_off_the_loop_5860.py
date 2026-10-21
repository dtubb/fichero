"""`GET /api/activity/jobs` never holds the event loop (#5860, `activity.jobs-poll-off-the-loop`).

WHY: the app polls it every 2 s, and every database read waits on the connection's transaction gate behind a writer. A read made
directly in the async route holds the loop for that wait (the #5843 family). So each such read goes through `asyncio.to_thread`;
only the cached or pure calls in ALLOWED may be called straight."""
from __future__ import annotations

import ast
from pathlib import Path

from fichero_server.api.routes.system import activity

# in-memory or cached: no database, no subprocess
ALLOWED = {
    ("job_queue", "is_paused"), ("job_queue", "mode"), ("job_queue", "kind_name"), ("job_queue", "offer_for"),
}
RECEIVERS = {"db", "job_queue", "recipe_runner", "derivatives", "tracker", "throttle"}


def _route() -> ast.AsyncFunctionDef:
    tree = ast.parse(Path(activity.__file__).read_text())
    return next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "list_background_jobs")


def test_the_jobs_route_calls_no_database_or_queue_function_on_the_loop():
    offenders = []
    for call in (n for n in ast.walk(_route()) if isinstance(n, ast.Call)):
        f = call.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in RECEIVERS:
            if (f.value.id, f.attr) in ALLOWED:
                continue
            if f.value.id == "tracker" and f.attr == "store":
                continue
            offenders.append(f"{f.value.id}.{f.attr}")
    # `tracker.store.list_workflow_runs` is awaited (async); a sync call on these receivers is the offence
    assert not offenders, f"called straight on the loop: {offenders}"


def test_the_route_hands_each_read_to_a_worker_thread():
    """The reads that wait on the gate are named by `to_thread`'s first argument, so a refactor that drops one is seen."""
    threaded = set()
    for call in (n for n in ast.walk(_route()) if isinstance(n, ast.Call)):
        f = call.func
        if isinstance(f, ast.Attribute) and f.attr == "to_thread" and call.args:
            a = call.args[0]
            threaded.add(a.attr if isinstance(a, ast.Attribute) else getattr(a, "id", ""))
    assert {"waiting_reason_of", "read_again_runs", "snapshot", "name_and_pages", "_remote_row", "process_tree_rusage",
            "machine_state", "_queue_summary"} <= threaded, threaded
