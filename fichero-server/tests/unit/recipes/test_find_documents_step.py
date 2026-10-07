"""Find the documents as a recipe step (spec: docs/contributor_manual/specs/source/finding-documents.md, #5550).

`finddocs.recipe-step`: setup adds the step for loose pages, after reading, with Fichero's own rules (no model to
choose) and the project's setting `accept_above` (default: propose, accept by itself only at very high
confidence); the Start plan carries it as its own card; a recipe run runs that card as a Find the Documents job
under the recipe's row. Through `POST /api/recipes/assemble`, `plan_start` and `runner.run`.
"""
from __future__ import annotations

from fichero_server import finddocs
from fichero_server.execution import jobs
from fichero_server.finddocs import job as finddocs_job
from fichero_server.recipes import runner
from fichero_server.recipes.assemble import AUTO_ACCEPT_ABOVE, STEP_ORDER
from fichero_server.recipes.jobs import READING, get_job
from fichero_server.recipes.start import plan_start
from tests.unit.finddocs.boxes import correspondence_box
from tests.unit.finddocs.test_find_documents_to_spec import _project


def _assemble(client, **answers):
    body = {"languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 16, **answers}
    r = client.post("/api/recipes/assemble", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_loose_pages_add_the_step_after_reading_with_its_default(client):
    plain = _assemble(client, purposes=["transcribe"])
    assert "find-documents-in-a-folder" not in [s["job"] for s in plain["steps"]]
    loose = _assemble(client, purposes=["transcribe"], loose_pages=True)
    jobs_in_order = [s["job"] for s in loose["steps"]]
    assert jobs_in_order[-1] == "find-documents-in-a-folder"
    assert jobs_in_order.index("find-documents-in-a-folder") > jobs_in_order.index("read-a-line")
    (step,) = [s for s in loose["steps"] if s["job"] == "find-documents-in-a-folder"]
    assert step["model"] == {"builtin": "document-finder"} and step["runs_on"] == "this-mac"
    assert step["settings"] == {"accept_above": AUTO_ACCEPT_ABOVE} and AUTO_ACCEPT_ABOVE == finddocs.AUTO_ACCEPT_ABOVE
    assert step["gap"] is None and loose["problems"] == []
    # Reading before cataloguing: it sits after correcting and before names.
    assert STEP_ORDER.index("correct") < STEP_ORDER.index("find-documents-in-a-folder") < STEP_ORDER.index(
        "find-names-tag-words")
    assert get_job("find-documents-in-a-folder").takes == frozenset({READING})
    # Loose pages that nothing reads add nothing: the step reads the text.
    assert "find-documents-in-a-folder" not in [s["job"] for s in _assemble(client, loose_pages=True)["steps"]]


def test_start_plan_runs_it_as_its_own_card(client):
    recipe = _assemble(client, purposes=["transcribe"], loose_pages=True)
    plan = plan_start(recipe, stays_local=True)
    (card,) = [r for r in plan["runs"] if r["job"] == "find-documents-in-a-folder"]
    assert card["card"] == "find-documents" and card["accept_above"] == AUTO_ACCEPT_ABOVE
    assert card["takes"] == [READING] and card["gives"] == ["document_groups"]
    assert not [s for s in plan["skipped"] if s["step"] == "find-documents-in-a-folder"]
    # The project's setting off: every proposal waits for the person.
    for step in recipe["steps"]:
        if step["job"] == "find-documents-in-a-folder":
            step["settings"] = {}
    (card,) = [r for r in plan_start(recipe, stays_local=True)["runs"] if r["job"] == "find-documents-in-a-folder"]
    assert card["accept_above"] is None


def test_a_recipe_run_finds_the_documents_under_its_row(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    pages, truth, _groups = correspondence_box()
    folder, ids = _project(db, tmp_path, pages)
    started = finddocs_job.start

    def start_and_run(db_, request, **kw):
        """The scheduler, by hand: the card's job runs to its end before the recipe waits on it."""
        job_id = started(db_, request, **kw)
        kind, subject = db_.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
        db_.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [job_id])
        jobs.KINDS[kind].run(db_, subject)
        db_.execute("UPDATE jobs SET state = 'done' WHERE id = ?", [job_id])
        return job_id

    monkeypatch.setattr(finddocs_job, "start", start_and_run)
    recipe = _assemble(client, purposes=["transcribe"], loose_pages=True)
    plan = plan_start(recipe, stays_local=True)
    plan["runs"] = [r for r in plan["runs"] if r["job"] == "find-documents-in-a-folder"]
    job_id = runner.enqueue(db, plan, documents=[ids[p.id] for p in pages], started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    result = runner.run(db, subject)
    (step,) = result["steps"]
    assert step["state"] == "done" and step["child_id"]
    child = jobs.read_job(db, step["child_id"])
    assert child["kind"] == "find-documents-in-a-folder"
    assert db.execute_fetchone("SELECT parent_id FROM jobs WHERE id = ?", [step["child_id"]])[0] == job_id
    (proposal,) = finddocs_job.proposals(db, folder.id)
    assert [d.page_ids for d in proposal.documents] == [[ids[p] for p in doc] for doc in truth]
    accepted = [d.index for d in proposal.documents if d.state == "accepted"]
    assert accepted == [d.index for d in proposal.documents if d.confidence >= AUTO_ACCEPT_ABOVE]


def test_on_by_default_for_a_project_holding_loose_pages(client, db, tmp_path, jobs_run_by_the_test):
    """§7b "Everything automatic after Start": a box of loose page images is organised as a stage of the run, unless
    the answers say it is not loose pages."""
    assert "find-documents-in-a-folder" not in [s["job"] for s in _assemble(client, purposes=["transcribe"])["steps"]]
    pages, _truth, _groups = correspondence_box()
    _project(db, tmp_path, pages)
    assert "find-documents-in-a-folder" in [s["job"] for s in _assemble(client, purposes=["transcribe"])["steps"]]
    off = _assemble(client, purposes=["transcribe"], loose_pages=False)
    assert "find-documents-in-a-folder" not in [s["job"] for s in off["steps"]]


def test_blank_versos_are_not_read(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    """#5579: the backs of leaves, blank as their images show before anything is read, are left out of the cards
    that line and read pages; the first page and the written pages are read."""
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    versos = {ids[p.id] for p in pages if p.blank}
    assert finddocs_job.blank_versos(db, list(ids.values())) == versos
    seen: list[list[str]] = []

    def workflow(db_, card, documents, parent):
        seen.append(documents)
        return "thread", "done", None

    monkeypatch.setattr(runner, "_run_workflow", workflow)
    card = {"steps": ["read"], "job": "read-a-line", "card": "workflow", "workflow": "w", "workflow_id": "w",
            "provider_override": None, "model_override": None, "takes": ["lines"], "gives": ["line_readings"]}
    job_id = runner.enqueue(db, {"runs": [card], "skipped": []}, documents=list(ids.values()), started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    (step,) = runner.run(db, subject)["steps"]
    assert seen == [[ids[p.id] for p in pages if not p.blank]] and step["blank_versos"] == len(versos)
