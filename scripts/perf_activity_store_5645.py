#!/usr/bin/env python3
"""Performance parity for #5645 slice 4 (ActivityStore onto the managed Database): run on the lead for "before" and
on the branch for "after"; compare the two JSON reports.

Builds a library in a temp folder with the OLD activity tables (as every existing library has them): N workflow runs
of realistic size (execution_log ~20 KB, progress_timeline ~5 KB, python_code ~10 KB, a snapshot; a few dozen
running, paused or failed) and 10 x N activity events. Then, on a warm library, measures each of:

- the Activity list (`GET /api/activity/jobs`'s handler, `list_background_jobs`);
- the runs list (`ActivityStore.list_workflow_runs(limit=50)`);
- one big run (`get_workflow_run`);
- a node-boundary flush of a run whose log is 10 KB, 1 MB and 2 MB (the store's `flush_node_boundary` where it
  exists, else the runner's former call: `update_workflow_run(progress_timeline=..., execution_log=<whole log>)`);
- 1,000 activity events saved (`save_now`).

For each: median and p95 wall time over the repeats, SQL statements issued per call (counted at both seams: the
store's own connections and the managed `Database`), and peak traced Python memory. Also the first open's duration
and peak memory (the one-time fold, after), and a second open's.

Writes nothing outside its temp folder (deleted at the end). Usage:
    PYTHONPATH=fichero-server/src python scripts/perf_activity_store_5645.py --runs 10000 --out report.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import statistics
import tempfile
import time
import tracemalloc
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

OLD_TABLES = """
CREATE TABLE activities (id TEXT PRIMARY KEY, type TEXT NOT NULL, level TEXT NOT NULL, timestamp TIMESTAMP NOT NULL,
    message TEXT NOT NULL, workflow_id TEXT, batch_id TEXT, thread_id TEXT, node_id TEXT, metadata JSON,
    duration_ms FLOAT, error TEXT);
CREATE TABLE workflow_runs (thread_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, workflow_name TEXT NOT NULL,
    python_code TEXT, execution_log TEXT, status TEXT DEFAULT 'running', started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP, duration_ms FLOAT, error TEXT, workflow_snapshot JSON, node_name_map JSON,
    progress_timeline JSON, resolved_scope JSON, diagram_mermaid TEXT, run_usage JSON, estimated_cost DOUBLE);
CREATE INDEX idx_activities_timestamp ON activities(timestamp DESC);
CREATE INDEX idx_activities_thread_id ON activities(thread_id);
CREATE INDEX idx_workflow_runs_started_at ON workflow_runs(started_at DESC);
"""


def build(path: Path, runs: int) -> None:
    conn = duckdb.connect(str(path))
    conn.execute("SET TimeZone = 'UTC'")
    conn.execute(OLD_TABLES)
    start = datetime(2026, 1, 1)
    code = "x = 1\n" * 1700  # ~10 KB
    log = "node read-a-line: page done\n" * 740  # ~20 KB
    timeline = json.dumps({"events": [{"type": "node_end", "node_id": f"n{i}", "page_id": f"p{i}"}
                                      for i in range(60)]})  # ~5 KB
    snapshot = json.dumps({"nodes": [{"id": f"n{i}", "tool": "read"} for i in range(40)]})
    rows = []
    for n in range(runs):
        status = ("running" if n % 1000 == 0 else "paused" if n % 1000 == 1 else
                  "failed" if n % 250 == 2 else "completed")
        rows.append((f"run-{n:06d}", f"wf-{n % 20}", f"Workflow {n % 20}", code, log, status,
                     start + timedelta(minutes=n), None if status in ("running", "paused") else
                     start + timedelta(minutes=n, seconds=30), 30000.0, "a page failed" if status == "failed" else None,
                     snapshot, json.dumps({"n1": "Read"}), timeline, json.dumps({"documents": [f"d{n}"]}),
                     "graph TD; a-->b", json.dumps({"cost_usd": 0.01}), 0.01))
        if len(rows) == 500:
            conn.executemany("INSERT INTO workflow_runs VALUES (" + ", ".join("?" * 17) + ")", rows)
            rows = []
    if rows:
        conn.executemany("INSERT INTO workflow_runs VALUES (" + ", ".join("?" * 17) + ")", rows)
    events = []
    for n in range(runs * 10):
        events.append((f"ev-{n:07d}", "node_completed", "info", start + timedelta(seconds=6 * n), "a node ended",
                       f"wf-{n % 20}", None, f"run-{n // 10:06d}", f"n{n % 60}", None, 12.0, None))
        if len(events) == 2000:
            conn.executemany("INSERT INTO activities VALUES (" + ", ".join("?" * 12) + ")", events)
            events = []
    if events:
        conn.executemany("INSERT INTO activities VALUES (" + ", ".join("?" * 12) + ")", events)
    conn.close()


class Counter:
    """SQL statements issued, at both seams: the store's own connections (before) and the managed Database (after)."""

    def __init__(self):
        self.n = 0

    def install(self):
        from fichero_server.db import Database
        from fichero_server.workflows import activity_store

        counter = self
        real_execute = Database._execute

        def counted(db, sql, params=None, *args, **kwargs):
            counter.n += 1
            return real_execute(db, sql, params, *args, **kwargs)

        Database._execute = counted
        if hasattr(activity_store, "connect_utc"):
            real_connect = activity_store.connect_utc

            class Proxy:
                def __init__(self, conn):
                    self._conn = conn

                def execute(self, *a, **k):
                    counter.n += 1
                    return self._conn.execute(*a, **k)

                def __getattr__(self, name):
                    return getattr(self._conn, name)

            activity_store.connect_utc = lambda *a, **k: Proxy(real_connect(*a, **k))


def measure(name, fn, counter: Counter, repeats: int) -> dict:
    times, statements, peaks = [], [], []
    for _ in range(repeats):
        counter.n = 0
        tracemalloc.start()
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
        peaks.append(tracemalloc.get_traced_memory()[1] / 1e6)
        tracemalloc.stop()
        statements.append(counter.n)
    times.sort()
    return {"name": name, "median_ms": round(statistics.median(times), 2),
            "p95_ms": round(times[max(0, int(len(times) * 0.95) - 1)], 2),
            "statements": statistics.median(statements), "peak_mb": round(max(peaks), 2)}


def main() -> None:
    import fichero_server.api.main  # noqa: F401  (the app's own import order; importing db first is circular)

    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="perf5645-"))
    try:
        package = root / "Big.fichero"
        package.mkdir()
        path = package / "fichero.duckdb"
        t0 = time.perf_counter()
        build(path, args.runs)
        report = {"runs": args.runs, "events": args.runs * 10, "build_s": round(time.perf_counter() - t0, 1),
                  "results": []}

        from fichero_server.db.manager import db_manager

        tracemalloc.start()
        t0 = time.perf_counter()
        db = db_manager.get_database(package)
        report["first_open_s"] = round(time.perf_counter() - t0, 2)
        report["first_open_peak_mb"] = round(tracemalloc.get_traced_memory()[1] / 1e6, 1)
        tracemalloc.stop()

        from fichero_server.api.routes.system.activity import list_background_jobs
        from fichero_server.workflows.activity import get_activity_tracker
        from fichero_server.workflows.activity_types import Activity, ActivityLevel, ActivityType

        store = get_activity_tracker(str(db.path)).store
        counter = Counter()
        counter.install()
        run = asyncio.run
        results = report["results"]
        results.append(measure("activity_jobs_list", lambda: run(list_background_jobs(db=db)), counter, args.repeats))
        results.append(measure("runs_list_50", lambda: run(store.list_workflow_runs(limit=50)), counter, args.repeats))
        results.append(measure("get_big_run", lambda: run(store.get_workflow_run("run-000500")), counter,
                               args.repeats))
        timeline = {"events": [{"type": "node_end", "node_id": f"n{i}"} for i in range(60)]}
        for label, size in (("10KB", 10_000), ("1MB", 1_000_000), ("2MB", 2_000_000)):
            thread = f"run-00{size % 997:04d}"
            whole = "x" * size
            run(store.update_workflow_run(thread_id=thread, execution_log=whole))

            def flush(thread=thread, whole=whole):
                if hasattr(store, "flush_node_boundary"):
                    run(store.flush_node_boundary(thread, progress_timeline=timeline, log_text="a line", replace=False))
                else:
                    run(store.update_workflow_run(thread_id=thread, progress_timeline=timeline,
                                                  execution_log=whole + "a line\n"))

            results.append(measure(f"node_flush_{label}_log", flush, counter, args.repeats))
        made = iter(range(10**9))

        def thousand_events():
            for _ in range(1000):
                store.save_now(Activity(id=f"perf-{next(made)}", type=ActivityType.NODE_COMPLETED,
                                        level=ActivityLevel.INFO, timestamp=datetime.now(), message="perf"))

        results.append(measure("save_now_x1000", thousand_events, counter, max(3, args.repeats // 5)))
        db_manager.close_database(package) if hasattr(db_manager, "close_database") else db.close()
        t0 = time.perf_counter()
        db_manager.get_database(package)
        report["second_open_s"] = round(time.perf_counter() - t0, 2)
        args.out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
