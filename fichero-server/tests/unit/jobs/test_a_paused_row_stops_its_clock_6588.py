"""`activity.pane.row-and-inspector-agree` (#6588): a paused row's Time is the work it did before the pause (its start to
the last work heard under it), not its start to now; a Kraken run paused after 3 minutes read "39 min", then "1 h"."""
from __future__ import annotations

from datetime import timedelta

from fichero_server.core.timeutil import utc_now
from fichero_server.execution import jobs


def _job(db, job_id, *, state, parent=None, kind="workflow", subject="s", started=None, finished=None, created=None):
    db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, started_at, finished_at, "
               "parent_id) VALUES (?, ?, ?, ?, 0, 'person', ?, ?, ?, ?)",
               [job_id, kind, subject, state, created or started or utc_now(), started, finished, parent])


def test_a_paused_run_counts_to_its_last_work_not_to_now(db):
    jobs._ensure(db)
    t0 = (utc_now() - timedelta(hours=2)).replace(tzinfo=None)
    _job(db, "run", state="paused", started=t0)
    _job(db, "p1", state="done", parent="run", kind="kraken", subject="d1", started=t0 + timedelta(seconds=5),
         finished=t0 + timedelta(seconds=90))
    _job(db, "p2", state="done", parent="run", kind="kraken", subject="d2", started=t0 + timedelta(seconds=90),
         finished=t0 + timedelta(seconds=180))
    _job(db, "p3", state="paused", parent="run", kind="kraken", subject="d3", created=t0)
    tree = jobs.tree(db, "run")
    assert abs(tree["seconds"] - 180) < 1


def test_a_running_run_still_counts_to_now(db):
    jobs._ensure(db)
    t0 = (utc_now() - timedelta(minutes=10)).replace(tzinfo=None)
    _job(db, "run", state="running", started=t0)
    _job(db, "p1", state="done", parent="run", kind="kraken", subject="d1", started=t0, finished=t0 + timedelta(seconds=60))
    assert jobs.tree(db, "run")["seconds"] >= 599
