"""Everything automatic after Start, seen by the person (review 2026-10-07), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md, section 7b's "Everything automatic after Start").

Behaviours: `source.onboard.auto.plan-shows-what-will-not-run` (#5573), `source.onboard.auto.on-add-refusal-said`
(#5575), `source.onboard.auto.lands-on-the-run` (#5576), `source.onboard.auto.results-summary` (#5577). Through the
public routes the app calls (`GET /api/recipes/project/start`, `GET /api/activity/jobs[/{id}]`,
`GET /api/recipes/project/runs[/{id}[/summary]]`, the import route, the read-again route) and the real scheduler.
The models are stubbed at their boundary only, as in `test_recipe_execution_to_spec.py` (its fixtures are used here).

With FICHERO_UPDATE_FIXTURES=1 the answers are recorded for the app's tests
(`fichero/Tests/Fixtures/recipes/*.route.json`); otherwise the recorded answers must still have the engine's shape.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fichero_server.execution import jobs
from tests.unit.recipes.test_diary_entries_step import splitter  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures: engine, pages)
    _finished,
    _import,
    _recipe,
    _run_status,
    _runs,
    _save,
    _start,
    _steps,
    _wait,
    engine,
    pages,
)

REPO = next(p for p in Path(__file__).resolve().parents if (p / "fichero" / "Tests").is_dir())
FIXTURES = REPO / "fichero" / "Tests" / "Fixtures" / "recipes"
SPACY = {"spacy": "es_core_news_sm", "version": "3.8.0"}


def _shape(value):
    """The keys of an answer, all the way down: what the app decodes, without the ids and times."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def _record(name: str, response: dict) -> None:
    """Keep the engine's answer for the app's tests, or check the kept one still has its shape."""
    path = FIXTURES / f"{name}.route.json"
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        path.write_text(json.dumps({"request": None, "status": 200, "response": response}, indent=1) + "\n")
    kept = json.loads(path.read_text())["response"]
    assert set(kept) == set(response), f"{path.name} drifted from the engine's answer; rerun with FICHERO_UPDATE_FIXTURES=1"


def test_source_onboard_auto_plan_shows_what_will_not_run(client, db, pages, tmp_path, monkeypatch):
    """source.onboard.auto.plan-shows-what-will-not-run: "Ready lists every step the Start plan skips (`skipped`)
    with its reason and fix button, and every model that must be fetched (`downloads`) with its size and a Download
    button." The plan names each skipped step's fix as setup's buttons name it, and each download as the action
    that fetches it."""
    from fichero_server.llm import local_models

    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: False)
    steps = _steps(tmp_path)
    steps[4] = {"id": "names", "job": "find-names-tag-words", "model": SPACY}
    steps.append({"id": "nameless", "job": "correct"})
    steps.append({"id": "authorities", "job": "link-to-authorities"})
    _save(client, _recipe(tmp_path, *steps), cloud_allowed=False)
    plan = client.get("/api/recipes/project/start").json()

    fix = {s["step"]: s["fix"] for s in plan["skipped"]}
    assert fix["check"] == "allow-cloud", "a cloud step in a project that keeps its pages here: let them leave"
    assert fix["nameless"] == "choose-model", "a step with no model: choose one"
    assert fix["authorities"] is None, "no card runs it yet: nothing in setup fixes it, the why says what does"
    assert all(s["why"] for s in plan["skipped"])
    download = next(d for d in plan["downloads"] if d["model"] == "es_core_news_sm")
    assert download["runtime"] == "spacy" and download["steps"] == ["names"]
    assert download["action"] == "model.download" and download["params"] == {"runtime": "spacy",
                                                                              "model": "es_core_news_sm"}
    assert any("es_core_news_sm" in r for r in plan["refusals"]), "Start waits for the download"
    _record("start_plan_skips_and_downloads", plan)


def test_source_onboard_auto_on_add_refusal_said(client, db, pages, tmp_path, monkeypatch, engine):
    """source.onboard.auto.on-add-refusal-said: "an import after Start whose recipe cannot run (the plan has
    refusals, or nothing runs) leaves a row in Activity saying why and what fixes it." Here the names step's
    spaCy pipeline left this Mac after Start: the import's pages are not read, and Activity says so."""
    from fichero_server.llm import local_models

    steps = _steps(tmp_path)[1:3]  # find the lines and read them
    _save(client, _recipe(tmp_path, *steps))
    _finished(client, _start(client))
    _save(client, _recipe(tmp_path, *steps, {"id": "names", "job": "find-names-tag-words", "model": SPACY}))
    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: False)
    engine.read = []

    _import(client, tmp_path, "arrived.png")
    assert _wait(lambda: len(_runs(client)) == 2), "the import leaves a row"
    row = next(r for r in _runs(client) if r["documents"] is not None)
    assert row["state"] == "failed" and row["started_by"] == "import" and row["steps"] == []
    assert any("es_core_news_sm" in r and "download" in r for r in row["refusals"])
    assert "Not run on the 1 new page this import brought" in row["reason"] and "download it first" in row["reason"]

    listed = client.get("/api/activity/jobs").json()["jobs"]
    shown = next(j for j in listed if j["id"] == row["job_id"])
    assert shown["state"] == "failed" and shown["reason"] == row["reason"], "Activity lists it, saying why"
    assert engine.read == [], "the new page is not read"


def test_source_onboard_auto_lands_on_the_run(client, db, pages, tmp_path):
    """source.onboard.auto.lands-on-the-run: "after Start, the project window shows the run: each stage, pages
    done and left, time left, and what is waiting and why (memory, a download, another run)." The recipe run's
    node in Activity (the details the app opens on) carries its stages in order, each workflow stage with its run's
    account; while it waits, its reason says for what."""
    _save(client, _recipe(tmp_path, *_steps(tmp_path)))
    jobs.set_paused(True)
    job_id = _start(client)
    waiting = _run_status(client, job_id)
    assert waiting["state"] == "waiting" and waiting["waiting_for"], "a waiting run says what it waits for"
    tree = client.get(f"/api/activity/jobs/{job_id}").json()
    assert [s["steps"] for s in tree["stages"]] == [["lines", "read"], ["check"], ["export"]]
    assert all(s["state"] == "waiting" and s["account"] is None for s in tree["stages"])
    assert tree["summary"] is None, "no summary before it ends"
    jobs.set_paused(False)

    run = _finished(client, job_id)
    read = run["steps"][0]
    assert read["job"] == "read-a-line" and read["account"]["pages_done"] == 2
    assert read["account"]["pages_left"] == 0 and read["account"]["state"] == "done"
    tree = client.get(f"/api/activity/jobs/{job_id}").json()
    stage = tree["stages"][0]
    child = next(c for c in tree["children"] if c["id"] == stage["child_id"])
    assert stage["account"]["pages_done"] == child["account"]["pages_done"] == 2, "the stage is its run's account"
    assert [s["state"] for s in tree["stages"]] == ["done", "done", "done"]
    _record("recipe_run_tree", tree)


def test_source_onboard_auto_results_summary(client, db, pages, tmp_path, engine):
    """source.onboard.auto.results-summary: "when a run ends, the project says what it made: pages read, lines,
    names by kind, dates, statements, documents and groups proposed, pages failed (with Read Again) and steps
    skipped (with their fixes)." Names and dates are the knowledge graph's own grouping of the run's pages."""
    from fichero_server.models.knowledge import EntityType, KnowledgeEntity

    db.save(KnowledgeEntity(canonical_name="Juan", entity_type=EntityType.person,
                            source_document_ids=[pages[0].id]))
    db.save(KnowledgeEntity(canonical_name="Popayán", entity_type=EntityType.location,
                            source_document_ids=[pages[1].id]))
    _save(client, _recipe(tmp_path, *_steps(tmp_path)), cloud_allowed=False)
    job_id = _start(client)
    _finished(client, job_id)
    summary = client.get(f"/api/recipes/project/runs/{job_id}/summary").json()
    assert summary["finished"] and summary["pages"] == 2 and summary["pages_read"] == 2
    assert {n["label"]: n["count"] for n in summary["names"]} == {"People": 1, "Places": 1}
    assert summary["statements"] == 1 and summary["dates"] == 1  # the claim names no entity: the KG's Dates
    assert summary["failed"] == [] and summary["pages_failed"] == 0
    skipped = {s["step"]: s["fix"] for s in summary["skipped"]}
    assert skipped["check"] == "allow-cloud" and skipped["names"] == "choose-model"
    # In the engine's words, one line per figure, shown as given; no line for a stage the run did not have.
    assert summary["lines"] == ["Read 2 of 2 pages", "Names: 1 People · 1 Places", "1 date · 1 statement"]
    assert (summary["documents_proposed"], summary["groups_proposed"], summary["entries"]) == (None, None, None)
    tree = client.get(f"/api/activity/jobs/{job_id}").json()
    assert tree["summary"] == summary, "Activity's details show the same summary"

    # Pages a stage could not read are counted, with the offer to read them again, which reads them.
    engine.fail_reading = True
    r = client.post("/api/recipes/project/start", json={"redo": ["read"]})
    assert r.status_code == 200, r.text
    again = r.json()["started"]["job_id"]
    _finished(client, again)
    summary = client.get(f"/api/recipes/project/runs/{again}/summary").json()
    assert summary["pages_failed"] == 2 and [f["steps"] for f in summary["failed"]] == [["lines", "read"]]
    stage = summary["failed"][0]
    assert stage["offer"] == "Read the 2 pages that failed" and len(stage["failures"]) == 2
    assert {s["state"] for s in summary["not_run"]} >= {"failed"}
    _record("recipe_run_summary_failed", summary)

    engine.fail_reading = False
    r = client.post(f"/api/workflow-execution/threads/{stage['thread_id']}/read-again")
    assert r.status_code == 202, r.text
    assert r.json()["pages"] == 2 and r.json()["from_thread_id"] == stage["thread_id"], \
        "Read Again starts one run over the stage's failed pages"


def test_summary_of_no_run_is_404(client, db):
    assert client.get("/api/recipes/project/runs/nope/summary").status_code == 404


def test_source_onboard_auto_results_summary__documents_groups_and_entries(client, db, pages, tmp_path, engine,
                                                                           splitter):
    """source.onboard.auto.results-summary (#5577): "documents and groups proposed" by Find the Documents, as its
    proposals stand, and the entries the entries stage split the pages into (#5581), as figures and as lines in the
    engine's words."""
    from fichero_server.finddocs import store as finddocs_store

    entries = {"id": "entries", "job": "split-into-entries", "model": {"cloud": "openai", "model": "gpt-5"},
               "runs_on": "cloud:openai"}
    find = {"id": "find", "job": "find-documents-in-a-folder", "model": {"builtin": "document-finder"},
            "settings": {"accept_above": 0.0}}
    lines = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
    read = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}
    _save(client, _recipe(tmp_path, lines, read, entries, find))
    job_id = _start(client)
    run = _finished(client, job_id)
    assert run["state"] == "done", run
    summary = client.get(f"/api/recipes/project/runs/{job_id}/summary").json()

    proposals = finddocs_store.proposals(db)
    proposed = sum(len(p.documents) for p in proposals)
    groups = sum(len(p.groups) for p in proposals)
    assert proposed >= 1
    assert (summary["documents_proposed"], summary["documents_accepted"], summary["groups_proposed"]) == \
        (proposed, proposed, groups), "accepted by the run's own setting (everything at or above 0)"
    assert summary["entries"] == 4  # two dated entries on each of the two pages
    docs = "document" if proposed == 1 else "documents"
    assert summary["lines"][3:] == [f"{proposed} {docs} proposed, {proposed} accepted",
                                    f"{groups} {'group' if groups == 1 else 'groups'} proposed",
                                    "4 entries from 2 pages"]
    assert client.get(f"/api/activity/jobs/{job_id}").json()["summary"]["lines"] == summary["lines"]
