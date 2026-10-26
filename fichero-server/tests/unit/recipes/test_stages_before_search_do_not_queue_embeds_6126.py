"""`activity.run.stages-before-search-do-not-embed` (#6126): while a recipe run is going and its Search stage has not embedded a
page, that page's earlier stages do not queue its own embed; Search embeds it once. A page outside the run still embeds at once,
and a page the run saved but Search never reached (the run stopped or failed first) is queued when the run ends.
WHY: inside one run a page was embedded after Read, again after Correct, and only the last counted; but a skipped embed that
is never made leaves the page unsearchable (review ## 1321)."""
from __future__ import annotations

from fichero_server.importers.derivatives import EMBED_KIND, queue_embedding
from fichero_server.recipes import runner

REEMBED = "make-a-vector"


def _count(db, kind):
    return db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [kind])[0]


def _save(db, doc):
    queue_embedding(doc, library_path=str(db.path), db=db)


def test_a_page_of_the_run_leaves_its_embed_to_search_and_another_page_still_embeds(db):
    runner.start_search_watch("run-1", {"p1", "p2"})
    try:
        _save(db, "p1")
        assert _count(db, EMBED_KIND) == 0
        _save(db, "elsewhere")  # a separate workflow on other pages: Search never embeds it
        assert _count(db, EMBED_KIND) == 1
    finally:
        runner.end_search_watch(db, "run-1", "owner")


def test_a_page_search_has_embedded_embeds_again_when_a_later_stage_saves_it(db):
    runner.start_search_watch("run-2", {"p1"})
    try:
        runner.search_embedded("run-2", ["p1"])
        _save(db, "p1")
        assert _count(db, EMBED_KIND) == 1
    finally:
        runner.end_search_watch(db, "run-2", "owner")


def test_a_run_that_ends_before_search_queues_the_pages_it_saved(db):
    runner.start_search_watch("run-3", {"p1", "p2", "p3"})
    _save(db, "p1")
    _save(db, "p2")
    runner.search_embedded("run-3", ["p2"])  # Search got to p2 only
    runner.end_search_watch(db, "run-3", "owner")  # stopped or failed here
    assert _count(db, REEMBED) == 1
    docs = db.execute_fetchone("SELECT detail FROM jobs WHERE kind = ?", [REEMBED])[0]
    assert '"p1"' in docs and '"p2"' not in docs and '"p3"' not in docs  # saved and not searched: only p1
    _save(db, "p1")  # the run is over: the immediate embed is back
    assert _count(db, EMBED_KIND) == 1


def test_a_run_that_finished_leaves_nothing_to_catch_up(db):
    runner.start_search_watch("run-4", {"p1"})
    _save(db, "p1")
    runner.search_embedded("run-4", ["p1"])
    runner.end_search_watch(db, "run-4", "owner")
    assert _count(db, REEMBED) == 0
