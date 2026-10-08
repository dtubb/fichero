"""Diaries and registers split into dated entries as a recipe step (#5581), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md, section 7b, "Everything automatic after Start",
`source.onboard.auto.diary-entries`).

Through the public surface: `PUT /api/recipes/project`, `GET|POST /api/recipes/project/start`, the recipe run's
status and the real job scheduler. The models are stubs at their boundary only: the Kraken reader the recipe
execution tests use, and the splitter's structured chat call (`diary_entries.chat_structured`).
"""
from __future__ import annotations

import pytest

from fichero_server.models import Document
from fichero_server.recipes.jobs import READING
from fichero_server.workflows.tools import diary_entries
from fichero_server.workflows.tools.diary_entries import DiaryEntry, DiaryPageSplit
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _start,
    engine,
    pages,
)

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}
MODEL = {"cloud": "openai", "model": "gpt-5"}
ENTRIES = {"id": "entries", "job": "split-into-entries", "model": MODEL, "runs_on": "cloud:openai"}


@pytest.fixture
def splitter(monkeypatch):
    """The splitter's model: two dated entries on every page it is asked about; the pages and models it was given."""
    asked: list[tuple[str, str, str]] = []

    async def chat_structured(prompt, schema, config, **kw):
        asked.append((prompt, config.provider, config.model))
        return DiaryPageSplit(entries=[
            DiaryEntry(date_text="8 de enero de 1795", date_iso="1795-01-08", text="8 de enero de 1795\nLlovió."),
            DiaryEntry(date_text="9 de enero de 1795", date_iso="1795-01-09", text="9 de enero de 1795\nNada."),
        ])

    monkeypatch.setattr(diary_entries, "chat_structured", chat_structured)
    return asked


def _save(client, recipe):
    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"], "cloud_allowed": True},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text


def _plan(client):
    r = client.get("/api/recipes/project/start")
    assert r.status_code == 200, r.text
    return r.json()


def _entries(db, page_id):
    return sorted((d for d in db.query(Document, parent_id=page_id) if not d.deleted_at and d.node_kind == "entry"),
                  key=lambda d: d.sequence)


def test_the_step_is_a_card_start_runs_after_reading_with_its_own_model(client, tmp_path):
    """"At Start: the step is a card of its own (`entries`), after reading: it takes the pages' reading [...] It needs
    a model, the step's own (a cloud or local text model as the run's provider and model, never another); a step
    with none is skipped with "choose-model"." """
    _save(client, _recipe(tmp_path, LINES, READ, ENTRIES))
    plan = _plan(client)
    (card,) = [r for r in plan["runs"] if r["job"] == "split-into-entries"]
    assert card["card"] == "entries" and card["steps"] == ["entries"]
    assert (card["provider"], card["model"]) == ("openai", "gpt-5")
    assert card["takes"] == [READING] and card["gives"] == ["entries"]
    assert [r["card"] for r in plan["runs"]] == ["workflow", "entries"]  # after the reading
    assert "entries" not in {s["step"] for s in plan["skipped"]}

    _save(client, _recipe(tmp_path, LINES, READ, {"id": "entries", "job": "split-into-entries"}))
    (skip,) = [s for s in _plan(client)["skipped"] if s["step"] == "entries"]
    assert skip["fix"] == "choose-model" and "no model" in skip["why"]


def test_start_splits_each_read_page_into_dated_entries(client, db, pages, tmp_path, engine, splitter):
    """"Each page is split by the Diary Entries workflow's own splitter [...]: one `entry` child per dated entry, its
    date as the `date` attribute, in the page's order [...] The step's account in the run status (`entries`) says
    how many pages it split [...] and how many entries it made". Run again, it matches the entries it made rather
    than making them twice; the entries are not pages, so the material and the readers do not see them."""
    _save(client, _recipe(tmp_path, LINES, READ, ENTRIES))
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    lines_read, split = run["steps"]
    assert split["steps"] == ["entries"] and split["state"] == "done"
    assert split["entries"] == {"pages": 2, "without_text": 0, "created": 4, "unchanged": 0, "updated": 0,
                                "removed": 0}
    assert {(provider, model) for _p, provider, model in splitter} == {("openai", "gpt-5")}
    for page in pages:
        made = _entries(db, page.id)
        assert [(e.name, e.attributes.get("date")) for e in made] == [("1795-01-08", "1795-01-08"),
                                                                      ("1795-01-09", "1795-01-09")]
        assert [e.page_content for e in made] == ["Llovió.", "Nada."]
    # The entries are not material: the count and the pages a run works on are the pages.
    assert sorted(db.unit_of_work_ids()) == sorted(p.id for p in pages) and db.unit_of_work_count() == 2

    engine.read = []
    again = _finished(client, _start(client))
    assert again["state"] == "done", again
    assert again["steps"][-1]["entries"]["created"] == 0 and again["steps"][-1]["entries"]["unchanged"] == 4
    assert engine.read == []  # nothing new to read: the entries are not pages
    assert all(len(_entries(db, p.id)) == 2 for p in pages)


def test_only_pages_with_text_are_split(jobs_run_by_the_test, client, db, pages, tmp_path, splitter):
    """"It runs only on the pages that have text; the rest are left alone and counted." The plan's entries card, run
    by the recipe runner over a page with text and one without."""
    from fichero_server.recipes import runner
    from fichero_server.recipes.start import plan_start

    first, second = pages
    first.page_content = "8 de enero de 1795\nLlovió.\n9 de enero de 1795\nNada."
    db.save(first)
    plan = plan_start(_recipe(tmp_path, LINES, READ, ENTRIES), stays_local=False)
    plan["runs"] = [r for r in plan["runs"] if r["card"] == "entries"]
    job_id = runner.enqueue(db, plan, documents=[first.id, second.id], started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    (split,) = runner.run(db, subject)["steps"]
    assert split["state"] == "done", split
    assert split["entries"]["pages"] == 1 and split["entries"]["without_text"] == 1
    assert split["entries"]["created"] == 2
    assert len(splitter) == 1 and first.page_content in splitter[0][0]
    assert len(_entries(db, first.id)) == 2 and _entries(db, second.id) == []


def test_a_failed_reading_stops_the_step(client, db, pages, tmp_path, engine, splitter):
    """"it takes the pages' reading [...], so a failed read stops it": the step says not run, and why."""
    engine.fail_reading = True
    _save(client, _recipe(tmp_path, LINES, READ, ENTRIES))
    run = _finished(client, _start(client))
    split = run["steps"][-1]
    assert split["state"] == "not run" and "no earlier step gave" in split["why"]
    assert splitter == [] and all(_entries(db, p.id) == [] for p in pages)
