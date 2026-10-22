"""A page a stage leaves out is named with why, and a node counts what it did over all its pages (#5691), tested to
the spec: `source.onboard.auto.blank-pages-not-read` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: the overnight MCP walk: Read covered 91 of 92 pages and said nothing of the one left out (a blank sheet); the
Kraken node said it processed 0 pages after reading 91, under the name "Kraken HTR — baseline + recognition".
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fichero_server.finddocs import job as finddocs_job
from fichero_server.recipes import runner, sorting
from tests.unit.recipes.test_find_documents_step import _project


def test_a_blank_sheet_left_out_of_reading_is_named_with_why(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    from fichero_server.recipes.run_view import summary
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    versos = {ids[p.id] for p in pages if p.blank}
    assert versos and finddocs_job.blank_versos(db, list(ids.values())) == versos
    monkeypatch.setattr(runner, "_run_workflow", lambda db_, card, documents, parent, adopt=None: ("thread", "done", None))
    card = {"steps": ["read"], "job": "read-a-line", "card": "workflow", "workflow": "w", "workflow_id": "w",
            "provider_override": None, "model_override": None, "takes": ["lines"], "gives": ["line_readings"]}
    job_id = runner.enqueue(db, {"runs": [card], "skipped": []}, documents=list(ids.values()), started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])

    (step,) = runner.run(db, subject)["steps"]

    assert {e["page_id"] for e in step["left_out"]} == versos
    assert all(e["page"] and e["why"] == sorting.BLANK_WHY for e in step["left_out"])  # #5705: true anywhere
    said = asyncio.run(summary(db, job_id))
    assert any(line.startswith("Left out: ") for line in said.lines), said.lines


def test_a_node_over_many_pages_counts_what_it_did_over_all_of_them():
    from fichero_server.workflows.builder import _make_aggregation_function

    state = {"parallel_results": {"read": [
        {"index": i, "total": 3, "success": True,
         "result": {"text": "x", "results": [{}], "processed_count": 1, "reused_count": 0}} for i in range(3)]}}
    out = asyncio.run(_make_aggregation_function("read")(state))["outputs"]["read"]
    assert (out["processed_count"], out["reused_count"]) == (3, 0)


def test_the_kraken_reading_node_is_named_as_a_person_says_it():
    path = Path(__file__).parents[3] / "src/fichero_server/resources/default_workflows/transcribe_kraken.json"
    labels = {n["id"]: n["label"] for n in json.loads(path.read_text(encoding="utf-8"))["nodes"]}
    assert labels["kraken-htr"] == "Read the lines with Kraken"
