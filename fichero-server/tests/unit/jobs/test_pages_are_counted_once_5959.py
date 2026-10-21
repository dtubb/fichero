"""A page is one page however many steps read it (#5959, `activity.run.pages-counted-once`): a 92-page run over three stages
read 184 of 276 in the table and 36 of 92 in the live block. The tree counts each page (document) once; a page is done when
every step that read it is done. Rows are written directly; the pages are real documents so the tree can name them."""
from __future__ import annotations

from datetime import datetime

from fichero_server.execution import jobs
from fichero_server.models import DocType, Document, FileType, Status


def _page(db, n):
    doc = Document(id=f"doc-5959-{n}", name=f"p{n}.png", doc_type=DocType.page, file_type=FileType.image,
                   status=Status.completed, metadata={}, created_at=datetime.now(), updated_at=datetime.now())
    db.save(doc)
    return doc.id


def _stage(db, run, name, states):
    step = jobs._insert(db, "workflow-step", f"{run}:{name}", None, "owner")
    jobs.set_parent(db, step, run)
    for n, state in enumerate(states):
        leaf = jobs._insert(db, "read-a-page", _page_id(n), None, "owner")
        jobs.set_parent(db, leaf, step)
        db.execute("UPDATE jobs SET state = ? WHERE id = ?", [state, leaf])
    return step


def _page_id(n):
    return f"doc-5959-{n}"


def test_a_three_stage_run_counts_each_page_once_and_done_means_through_every_stage(db):
    jobs._ensure(db)
    for n in range(4):
        _page(db, n)
    run = jobs._insert(db, "workflow", "run-5959", None, "owner")
    _stage(db, run, "a", ["done", "done", "done", "done"])
    _stage(db, run, "b", ["done", "done", "done", "waiting"])
    _stage(db, run, "c", ["done", "done", "waiting", "waiting"])
    tree = jobs.tree(db, run)
    assert (tree["done"], tree["total"]) == (2, 4), "pages counted once per stage: 12 of 12 style sums are the bug"
    assert "_units" not in tree and "_extra" not in tree


def test_a_step_still_counts_its_own_pages(db):
    jobs._ensure(db)
    for n in range(4):
        _page(db, n)
    run = jobs._insert(db, "workflow", "run-5959b", None, "owner")
    step = _stage(db, run, "a", ["done", "done", "failed", "waiting"])
    node = next(c for c in jobs.tree(db, run)["children"] if c["id"] == step)
    assert (node["done"], node["total"], node["failed"]) == (2, 4, 1)


def test_a_page_is_not_done_while_a_step_that_has_not_finished_has_not_reached_it_682(db):
    """## 682: stage a done on 4 pages, b and c still waiting with no leaves yet: 0 of 4, not 4 of 4."""
    jobs._ensure(db)
    for n in range(4):
        _page(db, n)
    run = jobs._insert(db, "workflow", "run-5959c", None, "owner")
    _stage(db, run, "a", ["done", "done", "done", "done"])
    for name in ("b", "c"):
        step = jobs._insert(db, "workflow-step", f"{run}:{name}", None, "owner")
        jobs.set_parent(db, step, run)
        db.execute("UPDATE jobs SET state = 'waiting' WHERE id = ?", [step])
    tree = jobs.tree(db, run)
    assert (tree["done"], tree["total"]) == (0, 4)


def test_a_page_missing_from_a_finished_step_was_skipped_there_and_does_not_hold_the_run_back_682(db):
    jobs._ensure(db)
    for n in range(4):
        _page(db, n)
    run = jobs._insert(db, "workflow", "run-5959d", None, "owner")
    _stage(db, run, "a", ["done", "done", "done", "done"])
    _stage(db, run, "b", ["done", "done"])  # a finished step that read only two pages
    jobs.tree(db, run)
    for step in jobs.tree(db, run)["children"]:
        db.execute("UPDATE jobs SET state = 'done' WHERE id = ?", [step["id"]])
    assert (jobs.tree(db, run)["done"], jobs.tree(db, run)["total"]) == (4, 4)
