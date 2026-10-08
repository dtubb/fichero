"""Stop on a recipe run reaches the step it is running whatever its kind (#5609,
`activity.recipe-run.stop-reaches-its-step`, docs/contributor_manual/specs/ui/activity-and-automatic-work.md).

Before: Stop reached a workflow run, a check and a search step, but a Find the Documents step (its job had no Stop)
and the steps the run does itself (entries, prepare, publish) ran to their end before the run stopped.

Through the public surface with the real scheduler: `PUT /api/recipes/project`, `POST /api/recipes/project/start`,
Stop through `POST /api/activity/jobs/{id}/cancel`, read back through the run's status. Each step is held on its
first page (a gate around the page's own work) while Stop is pressed; then let go, it stops before its next page.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

import threading

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.finddocs import job as finddocs_job
from fichero_server.finddocs import store as finddocs_store
from fichero_server.recipes import prepare
from fichero_server.workflows.tools import diary_entries
from tests.unit.finddocs.boxes import correspondence_box
from tests.unit.finddocs.test_find_documents_to_spec import _project
from tests.unit.recipes.test_diary_entries_step import ENTRIES, splitter  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _run_status,
    _start,
    engine,
    pages,
)

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}
PREP = {"id": "prep", "job": "prepare-the-image", "model": {"builtin": "image-preparer"}}
FIND = {"id": "find", "job": "find-documents-in-a-folder", "model": {"builtin": "document-finder"}}


class Gate:
    """Wraps `module.name`: the first call waits (saying it entered) until let go; every call is counted."""

    def __init__(self, monkeypatch, module, name):
        self.entered, self.release, self.calls = threading.Event(), threading.Event(), 0
        real = getattr(module, name)

        def held(*args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                self.entered.set()
                assert self.release.wait(30), "the test never let the step go"
            return real(*args, **kwargs)

        monkeypatch.setattr(module, name, held)


def _save(client, recipe):
    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"], "cloud_allowed": True},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text


def _stop(client, job_id) -> str:
    r = client.post(f"/api/activity/jobs/{job_id}/cancel")
    assert r.status_code == 200, r.text
    return r.json()["state"]


def _stop_while_held(client, gate) -> dict:
    """Start the saved recipe, Stop it while its step is held on its first page, let go; the run as it ended."""
    job_id = _start(client)
    assert gate.entered.wait(60), _run_status(client, job_id)
    assert _stop(client, job_id) == "stopping"
    gate.release.set()
    run = _finished(client, job_id)
    assert run["state"] == "cancelled", run
    return run


def test_stop_reaches_prepare__it_stops_before_its_next_page(client, db, pages, tmp_path, engine, monkeypatch):
    """The prepare step looks at no page after Stop; its account counts the one it looked at; no step after it
    runs, and the row ends cancelled."""
    gate = Gate(monkeypatch, prepare, "contrast_spread")
    try:
        _save(client, _recipe(tmp_path, PREP, LINES, READ))
        run = _stop_while_held(client, gate)
    finally:
        gate.release.set()
    prep, read = run["steps"]
    assert (prep["state"], prep["why"]) == ("cancelled", "Stopped by you"), prep
    assert gate.calls == 1 and sum(prep["prepared"].values()) == 1, prep
    assert read["state"] == "not run" and engine.read == []
    row = jobs.read_job(db, run["job_id"])
    assert row["reason"].startswith("Stopped by you; 0 of 2 steps done"), row


def test_stop_reaches_the_entries_step__it_splits_no_page_after(client, db, pages, tmp_path, engine, splitter,
                                                                 monkeypatch):
    """The entries step splits no page after Stop; its account says how many it split."""
    gate = Gate(monkeypatch, diary_entries, "split_page_into_entries")
    try:
        _save(client, _recipe(tmp_path, LINES, READ, ENTRIES))
        run = _stop_while_held(client, gate)
    finally:
        gate.release.set()
    read, entries = run["steps"]
    assert read["state"] == "done"
    assert (entries["state"], entries["why"]) == ("cancelled", "Stopped by you"), entries
    assert gate.calls == 1 and entries["entries"]["pages"] == 1 and len(splitter) == 1, entries
    assert jobs.read_job(db, run["job_id"])["reason"].startswith("Stopped by you; 1 of 2 steps done")


def test_stop_reaches_publish__the_site_is_not_finished(client, db, pages, tmp_path, engine, monkeypatch):
    """The publish step writes no page after Stop and leaves the site unfinished (no index)."""
    from fichero_server import export_service

    site = tmp_path / "site"
    gate = Gate(monkeypatch, export_service, "_render_eleventy_item")
    try:
        export = {"id": "export", "job": "export", "settings": {"formats": ["pagexml"], "folder": str(tmp_path / "ed")}}
        _save(client, _recipe(tmp_path, LINES, READ, export,
                              {"id": "site", "job": "publish", "settings": {"where": str(site)}}))
        run = _stop_while_held(client, gate)
    finally:
        gate.release.set()
    publish = run["steps"][-1]
    assert (publish["steps"], publish["state"], publish["why"]) == (["site"], "cancelled", "Stopped by you"), publish
    assert gate.calls == 1 and not (site / "src" / "index.md").exists()


def test_stop_reaches_find_the_documents__its_own_stop_and_the_runs(client, test_package, tmp_path, engine,
                                                                    monkeypatch):
    """Find the Documents has its own Stop (it answered `running` and read every folder before): Stop on the recipe
    run reaches it through that Stop, it reads no page after (and proposes nothing for the folder), and its row and the step end cancelled."""
    from fichero_server.workflows.default_workflows import seed_default_workflows

    db = db_manager.get_database(test_package)
    seed_default_workflows(db)
    box, _truth, _groups = correspondence_box()
    folder, _ids = _project(db, tmp_path, box)
    # Held as it starts its folder (the names on its pages are looked up before any page is looked at).
    gate = Gate(monkeypatch, finddocs_job, "_names")
    try:
        _save(client, _recipe(tmp_path, LINES, READ, FIND))
        run = _stop_while_held(client, gate)
    finally:
        gate.release.set()
    find = run["steps"][-1]
    assert find["steps"] == ["find"], run
    assert find["state"] == "cancelled", find
    child = jobs.read_job(db, find["child_id"])
    assert (child["kind"], child["state"], child["reason"]) == (finddocs_job.KIND, "cancelled", "Stopped by you")
    assert gate.calls == 1 and finddocs_store.proposals(db, folder.id) == [], "no page was read after Stop"
    assert _stop(client, find["child_id"]) == "cancelled", "Stop again on a stopped run says so"


def test_find_the_documents_own_stop__a_waiting_run_ends_at_once(jobs_run_by_the_test, client, db, tmp_path):
    """Stop on a Find the Documents run that has not started ends it cancelled at once."""
    finddocs_job.register_job_kinds()
    box, _truth, _groups = correspondence_box()
    folder, _ids = _project(db, tmp_path, box)
    r = client.post("/api/find-documents/runs", json={"scope_ids": [folder.id]})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    assert jobs.read_job(db, job_id)["state"] == "waiting"
    assert _stop(client, job_id) == "cancelled"
    assert jobs.read_job(db, job_id)["state"] == "cancelled"
