"""Taking back a Work Out Dates run puts each page's previous date back (#5597).

Spec: docs/contributor_manual/specs/source/source-model.md, `source.extract.date-run-taken-back`.

WHY: Work Out Dates saved a page's date columns with a bare ``db.save``, so nothing recorded the
write under the run and taking the run back left the dates it set. Its writes now go through the
audited ``document.write_extracted_date`` action under the run's id, the same way a run's readings
go through ``representation.create``; taking the run back is undoing those rows through
``POST /api/actions/audit/{id}/undo``, newest first. A person's date wins throughout.

Nothing is stubbed: the shipped Work Out Dates preset (it uses no model) runs through the real
runner, as ``POST /execute`` does, on a real library; the person's date and the take-back go
through the routes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest
from fichero_server.db import db_manager
from fichero_server.execution import runner
from fichero_server.histdate import gregorian_to_jdn
from fichero_server.models import ActionAudit, DocType, Document, FileType, Workflow
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.selection import SelectionKind, WorkflowSelection

import fichero_server.workflows.tools  # noqa: F401

PRIOR = {
    "date_original": "1926",
    "date_jdn": gregorian_to_jdn(1926, 1, 1),
    "date_jdn_end": gregorian_to_jdn(1926, 12, 31),
    "date_meta": {"status": "dated", "source": "extracted", "precision": "year"},
}
EMPTY = {"date_original": None, "date_jdn": None, "date_jdn_end": None, "date_meta": None}


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


def _dates(db, doc_id: str) -> dict:
    doc = db.get(Document, doc_id)
    return {n: getattr(doc, n) for n in EMPTY}


def _page(db, doc_id: str, text: str, **dates) -> None:
    source = Path(db.path).parent / f"{doc_id}.txt"
    source.write_text(text, encoding="utf-8")
    db.save(Document(id=doc_id, name=source.name, path=str(source), doc_type=DocType.file,
                     file_type=FileType.text, page_content=text, **dates))


def _run_work_out_dates(library_path, thread_id: str, ids: list[str]) -> None:
    preset = next(p for p in _load_preset_files() if p["name"] == "Work Out Dates")
    workflow = Workflow(id="work-out-dates-5597", name=preset["name"], nodes=preset["nodes"],
                        edges=preset["edges"], config=preset.get("config", {}))
    runner._set_workflow_state(thread_id, {
        "workflow_id": workflow.id, "workflow_name": workflow.name, "status": "accepted",
        "events": runner.WorkflowEventHub(), "error": None, "final_state": None,
    })
    request = ExecuteWorkflowRequest(workflow_id=workflow.id, inputs={}, thread_id=thread_id,
                                     selection=WorkflowSelection(kind=SelectionKind.documents, ids=ids),
                                     skip_cache=True)
    try:
        asyncio.run(runner._run_workflow_in_background(
            thread_id, workflow, request, db_manager.get_database(library_path)))
    finally:
        runner._remove_workflow_state(thread_id)


def _take_back(client, db, run_id: str) -> list[dict]:
    """Undo every write the run recorded, newest first, through the undo route."""
    rows = sorted(db.query(ActionAudit, run_id=run_id), key=lambda a: (a.created_at, a.chain_seq or 0),
                  reverse=True)
    assert rows, "the run recorded nothing under its id"
    results = []
    for row in rows:
        response = client.post(f"/api/actions/audit/{row.id}/undo")
        assert response.status_code == 200, response.text
        results.append(response.json()["result"])
    return results


def _set_by_person(client, doc_id: str, date: str) -> None:
    response = client.post("/api/actions/invoke",
                           json={"name": "document.set_date", "params": {"doc_id": doc_id, "date_original": date}})
    assert response.status_code == 200, response.text


def test_taking_back_the_run_restores_each_page_and_never_touches_a_persons_date(client, db, test_package):
    _page(db, "prior", "MONDAY, JANUARY 10, 1927\nWent in to Cali today.", **PRIOR)
    _page(db, "empty", "FRIDAY, SEPTEMBER 4, 1931\nOn board train")
    _page(db, "person", "SATURDAY, SEPTEMBER 5, 1931\nArrived at New York")
    _set_by_person(client, "person", "1 May 1930")
    persons = _dates(db, "person")

    _run_work_out_dates(test_package, "dates-run-5597", ["prior", "empty", "person"])

    # Preconditions: the run dated both pages, and recorded its disagreement beside the person's date.
    assert _dates(db, "prior")["date_jdn"] == gregorian_to_jdn(1927, 1, 10)
    assert _dates(db, "empty")["date_jdn"] == gregorian_to_jdn(1931, 9, 4)
    after_run = _dates(db, "person")
    assert {n: after_run[n] for n in ("date_original", "date_jdn", "date_jdn_end")} == \
        {n: persons[n] for n in ("date_original", "date_jdn", "date_jdn_end")}, "the run moved a person's date"
    assert after_run["date_meta"]["source"] == "user"
    assert after_run["date_meta"]["extraction_conflict"]["candidate"]["date_jdn"] == gregorian_to_jdn(1931, 9, 5)
    written = db.query(ActionAudit, run_id="dates-run-5597")
    assert {a.action_name for a in written} == {"document.write_extracted_date"}
    assert {t for a in written for t in a.target_ids} == {"prior", "empty", "person"}

    _take_back(client, db, "dates-run-5597")

    assert _dates(db, "prior") == PRIOR
    assert _dates(db, "empty") == EMPTY
    assert _dates(db, "person") == persons, "the take-back changed a person's date"


def test_a_date_a_person_set_after_the_run_is_kept_when_the_run_is_taken_back(client, db, test_package):
    _page(db, "prior", "MONDAY, JANUARY 10, 1927\nWent in to Cali today.", **PRIOR)
    _page(db, "empty", "FRIDAY, SEPTEMBER 4, 1931\nOn board train")

    _run_work_out_dates(test_package, "dates-run-5597-later", ["prior", "empty"])
    _set_by_person(client, "empty", "3 September 1931")
    persons = _dates(db, "empty")

    results = _take_back(client, db, "dates-run-5597-later")

    assert _dates(db, "prior") == PRIOR
    assert _dates(db, "empty") == persons
    assert [r["kept"] for r in results if r["document_id"] == "empty"] == \
        ["the page's date changed since; it is kept"]


def test_redoing_the_take_back_puts_the_runs_date_back(client, db, test_package):
    _page(db, "empty", "FRIDAY, SEPTEMBER 4, 1931\nOn board train")
    _run_work_out_dates(test_package, "dates-run-5597-redo", ["empty"])
    dated = _dates(db, "empty")
    _take_back(client, db, "dates-run-5597-redo")
    assert _dates(db, "empty") == EMPTY

    inverse = next(a for a in db.all(ActionAudit)
                   if a.inverse_of and db.get(ActionAudit, a.inverse_of).run_id == "dates-run-5597-redo")
    assert client.post(f"/api/actions/audit/{inverse.id}/undo").status_code == 200
    assert _dates(db, "empty") == dated


def test_a_machine_write_never_replaces_a_persons_date(client, db):
    _page(db, "person", "x")
    _set_by_person(client, "person", "1 May 1930")
    persons = _dates(db, "person")

    response = client.post("/api/actions/invoke", json={"name": "document.write_extracted_date", "params": {
        "doc_id": "person", "date_original": "1931", "date_jdn": 1, "date_jdn_end": 2,
        "date_meta": {"source": "extracted"}}})

    assert response.status_code == 200, response.text
    assert response.json()["result"]["kept"] == "a person set this page's date; it is kept"
    assert _dates(db, "person") == persons
