"""One blank rule for the recipe's left-out pages and Find the Documents (#5705), tested to the spec:
`source.onboard.auto.blank-pages-not-read` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: a 92-page run left out a written recto (51_Hoja_555_Recto) as "a blank sheet, the back of a written leaf"
and never read it, while Find the Documents on the same page said "a written page (its image holds ink)". The
recipe's sorting had marked it blank under the ink measure #5676 replaced, and never looked again. The two rules
also drew the line at different inks. The run's summary said "Read 92 of 92 pages" with 5 pages left out, and the CLI
printed the reason twice.
"""

from __future__ import annotations

import asyncio

from fichero_server.finddocs import job as finddocs_job
from fichero_server.finddocs import propose
from fichero_server.models import Document
from fichero_server.recipes import runner, sorting
from tests.unit.finddocs.boxes import istmina_box
from tests.unit.finddocs.test_find_documents_to_spec import _project


def _box(db, tmp_path):
    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    return pages, ids


def test_the_recipe_leaves_out_exactly_the_pages_find_the_documents_calls_blank(db, tmp_path):
    pages, ids = _box(db, tmp_path)
    docs = [db.get(Document, ids[p.id]) for p in pages]

    found = {i.id for i in finddocs_job.page_inputs(db, docs) if propose._is_blank(i)}

    assert found and finddocs_job.blank_versos(db, list(ids.values())) == found


def test_a_page_sorted_blank_by_an_older_rule_is_looked_at_again_and_read(db, tmp_path):
    """source.sort.written-recto-is-read: a written page is never left sorted blank and out of every later run."""
    pages, ids = _box(db, tmp_path)
    written = next(ids[p.id] for p in pages if not p.blank)
    doc = db.get(Document, written)
    doc.attributes = {sorting.KIND: sorting.BLANK, sorting.SET_BY: sorting.BY_SORTING}
    db.save(doc)

    kinds = sorting.kinds(db, [written], [])

    assert kinds.get(written) != sorting.BLANK
    assert sorting.KIND not in (db.get(Document, written).attributes or {}), "the stale kind is not kept"


def test_a_page_a_person_called_blank_stays_blank(db, tmp_path):
    pages, ids = _box(db, tmp_path)
    written = next(ids[p.id] for p in pages if not p.blank)
    doc = db.get(Document, written)
    doc.attributes = {sorting.KIND: sorting.BLANK, sorting.SET_BY: sorting.BY_PERSON}
    db.save(doc)

    assert sorting.kinds(db, [written], []) == {written: sorting.BLANK}


def test_a_left_out_page_is_said_once_with_a_true_reason_and_the_counts_add_up(db, tmp_path, jobs_run_by_the_test,
                                                                                monkeypatch):
    from fichero_cli.formatters import _line
    from fichero_server.models import Artifact
    from fichero_server.recipes.run_view import summary

    pages, ids = _box(db, tmp_path)
    blank = {ids[p.id] for p in pages if p.blank}
    # A blank page an earlier run gave a reading: it is left out of this one, and not counted as read.
    db.save(Artifact(document_id=next(iter(blank)), artifact_type="transcription", content="-", model="m",
                     provider="openrouter"))
    monkeypatch.setattr(runner, "_run_workflow", lambda db_, card, documents, parent, adopt=None: ("thread", "done", None))
    card = {"steps": ["read"], "job": "read-a-line", "card": "workflow", "workflow": "w", "workflow_id": "w",
            "provider_override": None, "model_override": None, "takes": ["lines"], "gives": ["line_readings"]}
    job_id = runner.enqueue(db, {"runs": [card], "skipped": []}, documents=list(ids.values()), started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])

    (step,) = runner.run(db, subject)["steps"]

    assert {e["page_id"] for e in step["left_out"]} == blank
    # Not "the back of a written leaf": a blank is caught anywhere in its folder (#5676), after a blank too.
    assert all(e["why"] == sorting.BLANK_WHY for e in step["left_out"])
    said = asyncio.run(summary(db, job_id))
    assert said.pages_read == len(ids) - len(blank), "a page left out is not counted as read"
    printed = _line(said.left_out[0].model_dump(), 0)
    assert printed.count(sorting.BLANK_WHY) == 1, printed
