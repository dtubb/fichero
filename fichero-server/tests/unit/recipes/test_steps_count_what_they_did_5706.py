"""Each step's account counts what it did, the plan counts a page done once its step ran on it, and an offer says
the step's own verb (#5706), tested to the spec: `source.recipe.done-is-not-redone` and
`source.onboard.auto.results-summary` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: the operator's real run (integration 88b81f01e): Names found 1,193 mentions on 87 pages and its account said
`pages_done 0, pages_left 92`, offering "Read the 92 pages not done"; Dates the same; the plan said Names was
"already done on 77 of 92" after every run, and Prepare "already done on 4 of 92" after reporting 88 clear.
"""

from __future__ import annotations

from fichero_server.recipes import runner
from fichero_server.recipes.done import split_done
from fichero_server.recipes.run_view import offer_words
from fichero_server.workflows.run_account import build_account
from tests.unit.finddocs.boxes import istmina_box
from tests.unit.recipes.test_find_documents_step import _project

NAMES = {"steps": ["names"], "job": "find-names-tag-words", "card": "workflow", "workflow": "w", "workflow_id": "w",
         "provider_override": "spacy", "model_override": "es_core_news_sm", "takes": ["text"],
         "gives": ["entities"]}
PREPARE = {"steps": ["prepare"], "job": "prepare-the-image", "card": "prepare", "takes": ["page_image"],
           "gives": ["page_image"]}


def test_a_run_that_read_every_page_in_one_call_counts_every_page_done():
    state = {"files": ["a.png", "b.png", "c.png"], "outputs": {"names": {"summary": {"documents_processed": 3}}}}
    account = build_account(status="completed", reason=None, state=state)
    assert (account.pages_total, account.pages_done, account.pages_left) == (3, 3, 0)
    assert account.offer is None


def test_an_offer_says_the_steps_own_verb():
    assert offer_words("find-names-tag-words", "Read the 92 pages not done") == "Find names on the 92 pages not done"
    assert offer_words("work-out-dates", "Read the 3 pages that failed") == "Work out dates on the 3 pages that failed"
    assert offer_words("read-a-line", "Read the 3 pages that failed") == "Read the 3 pages that failed"


def test_a_page_a_step_ran_on_and_found_nothing_on_is_done_next_time(db, tmp_path, jobs_run_by_the_test,
                                                                     monkeypatch):
    """source.recipe.step-counts-its-pages: a step that left no trace on a page still keeps the page as done."""
    pages = istmina_box()[0][:4]
    _folder, ids = _project(db, tmp_path, pages)
    written = [ids[p.id] for p in pages if not p.blank]
    monkeypatch.setattr(runner, "_run_workflow", lambda db_, card, documents, parent, adopt=None: ("thread", "done", None))
    monkeypatch.setattr(runner, "_run_prepare", lambda db_, documents, parent, step: (None, "done", None))
    for card in (NAMES, PREPARE):
        assert split_done(db, card, written)[1] == 0, "nothing done before the run"
        job_id = runner.enqueue(db, {"runs": [card], "skipped": []}, documents=written, started_by="owner")
        _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
        step = runner.run(db, subject)["steps"][0]
        assert step.get("ran_on") == written, step
        db.execute("UPDATE jobs SET state = 'done' WHERE id = ?", [job_id])  # as the scheduler ends it
        todo, done = split_done(db, card, written)
        assert (todo, done) == ([], len(written)), card["job"]
