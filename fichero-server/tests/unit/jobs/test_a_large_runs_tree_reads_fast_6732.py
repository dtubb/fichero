"""#6732: the tree of a run with thousands of pages reads in under a second (it took 23 s on the owner's library)."""
from __future__ import annotations

import time

from fichero_server.execution import jobs

PAGES = 6000


def test_a_run_of_thousands_of_pages_has_its_tree_in_under_a_second(db):
    jobs._ensure(db)
    run = jobs._insert(db, "workflow", "run-6732", None, "owner")
    step = jobs._insert(db, "workflow-step", "run-6732:read", None, "owner")
    jobs.set_parent(db, step, run)
    db.execute(
        "INSERT INTO jobs (id, kind, subject, state, parent_id, created_at, started_by) "
        "SELECT 'leaf-6732-' || i, 'read-a-page', 'doc-6732-' || i, 'done', ?, now(), 'owner' FROM range(?) t(i)",
        [step, PAGES],
    )
    started = time.perf_counter()
    tree = jobs.tree(db, run)
    took = time.perf_counter() - started
    assert tree["total"] == PAGES
    assert took < 1.0, f"get_job_tree's tree took {took:.2f} s for {PAGES} pages"
