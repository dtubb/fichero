"""Everything automatic after Start (#5574, #5478), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md, section 7b, "Everything automatic after Start").

Behaviours: `source.onboard.auto.every-proposed-step-runs`, `source.onboard.auto.runs-by-itself-honoured`,
`source.onboard.auto.job-answers-read`, and the plan's `skipped` saying why and the fix. Everything goes through the
public surface: `POST /api/recipes/assemble`, `PUT /api/recipes/project`, `GET|POST /api/recipes/project/start`, the
recipe runs, the import route, the activity tree and the real job scheduler. The stubs are the ones the recipe
execution tests use, at the model boundary only (a Kraken reader, a checker); the page embed is recorded at the
library's `embed`, which loads the embedding model.
"""
from __future__ import annotations

import time

import pytest

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _import,
    _recipe,
    _runs,
    _start,
    _wait,
    engine,
    pages,
)

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}


def _search(model: str | None = None) -> dict:
    from fichero_server.db.embeddings import search_embedder

    return {"id": "search", "job": "make-a-vector", "model": {"hf": model or search_embedder(), "revision": "main"}}


def _save(client, recipe, **answers):
    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["search"], **answers}, "recipe": recipe})
    assert r.status_code == 200, r.text


def _plan(client):
    r = client.get("/api/recipes/project/start")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def embedded(monkeypatch):
    """The pages the library embedded (the embedding model itself is not loaded)."""
    from fichero_server.db import Database

    seen: list[str] = []

    def embed(self, doc, *, mode="passage"):
        seen.append(doc.id)
        return True

    monkeypatch.setattr(Database, "embed", embed)
    return seen


def test_every_step_setup_proposes_is_one_start_runs(client):
    """source.onboard.auto.every-proposed-step-runs: "setup never proposes a step that Start has no card for. Each
    registered job either has a card in `start.py` or is not offered as a step that runs by itself." Test: "for
    every purpose, the assembled recipe's steps that have a model all appear in the Start plan's `runs`"; a job the
    purpose brings that Start cannot run is in the plan's `skipped`, with why and the fix, never silent."""
    from fichero_server.recipes.start import START_JOBS

    assert "find-documents-in-a-folder" in START_JOBS  # Find the Documents has its card (#5550)
    purposes = [p["id"] for p in client.get("/api/recipes/purposes").json()["items"] if p["runs_by_itself"]]
    assert "search" in purposes and "map-places" in purposes
    for purpose in purposes:
        answers = {"purposes": [purpose], "languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 64}
        recipe = client.post("/api/recipes/assemble", json=answers).json()
        assert all(s["job"] in START_JOBS for s in recipe["steps"]), (purpose, recipe["steps"])
        _save(client, recipe, purposes=[purpose], languages=["es"], scripts=["Latn"])
        plan = _plan(client)
        running = {sid for run in plan["runs"] for sid in run["steps"]}
        with_a_model = {s["id"] for s in recipe["steps"] if s.get("model") and not s.get("gap")}
        assert with_a_model <= running, (purpose, with_a_model - running, plan["skipped"])
        skipped = {s["step"]: s for s in plan["skipped"]}
        for left in recipe["by_hand"]:
            assert left["job"] in skipped and left["fix"] in skipped[left["job"]]["why"], (purpose, left)
        # the fix is setup's button (#5573) or, with none, said in the why: never silent
        assert all(s["why"] and s["fix"] in (None, "choose-model", "allow-cloud") for s in plan["skipped"]), (
            purpose, plan["skipped"])


def test_search_is_a_step_start_runs_not_one_it_skips(client):
    """source.onboard.auto.every-proposed-step-runs: "Search is the first fix: its step is the embed job that already
    follows every reading, and the plan says so rather than 'skipped'." The rules name the engine's own search
    embedder, so the step runs."""
    answers = {"purposes": ["search"], "languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 64}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    _save(client, recipe, **answers)
    plan = _plan(client)
    assert [(r["steps"], r["card"]) for r in plan["runs"] if r["job"] == "make-a-vector"] == [(["make-a-vector"],
                                                                                              "embed")]
    assert "make-a-vector" not in {s["step"] for s in plan["skipped"]}


def test_search_runs_the_embed_job_for_each_page(client, db, pages, tmp_path, engine, embedded):
    """Start runs the search step as the embed job (`make-a-vector`) for each page, children of the recipe's row in
    Activity, after the pages are read; the run waits for them and says done."""
    _save(client, _recipe(tmp_path, LINES, READ, _search()))
    plan = _plan(client)
    assert [(r["steps"], r["card"]) for r in plan["runs"]] == [(["lines", "read"], "workflow"), (["search"], "embed")]
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    assert [(s["steps"], s["state"]) for s in run["steps"]] == [(["lines", "read"], "done"), (["search"], "done")]
    tree = client.get(f"/api/activity/jobs/{run['job_id']}").json()
    vectors = [c for c in tree["children"] if c["kind"] == "make-a-vector"]
    assert sorted(c["subject"] for c in vectors) == sorted(p.id for p in pages)
    assert all(c["state"] == "done" for c in vectors)
    assert sorted(embedded) == sorted(p.id for p in pages)


def test_a_search_step_naming_another_embedder_is_skipped_with_its_fix(client, tmp_path):
    """A search step whose model is not the one this library searches with is skipped, never run with another
    model: the plan says why and the fix."""
    from fichero_server.db.embeddings import search_embedder

    _save(client, _recipe(tmp_path, LINES, READ, _search("intfloat/multilingual-e5-small")))
    (skip,) = [s for s in _plan(client)["skipped"] if s["step"] == "search"]
    assert "search embeds with" in skip["why"] and search_embedder() in skip["why"]


def test_nothing_runs_automatically_queues_no_run_on_import(client, db, pages, tmp_path, engine, embedded):
    """source.onboard.auto.runs-by-itself-honoured: "With Nothing runs automatically, an import after Start queues no
    recipe run." Start, pressed by hand, still runs the recipe once over the material already there (section 7b,
    screen 8)."""
    _save(client, _recipe(tmp_path, LINES, READ), automatic={"runs": False, "steps": []})
    assert _finished(client, _start(client))["state"] == "done"
    engine.read = []
    _import(client, tmp_path, "later.png")
    time.sleep(1.5)
    assert len(_runs(client)) == 1 and engine.read == [], _runs(client)


def test_new_material_runs_only_the_ticked_steps(client, db, pages, tmp_path, engine, embedded):
    """source.onboard.auto.runs-by-itself-honoured: "otherwise it runs only the ticked steps"; an unticked step is
    in the run's `skipped`, saying it runs only by hand and how to tick it."""
    _save(client, _recipe(tmp_path, LINES, READ, _search()),
          automatic={"runs": True, "steps": ["find-lines", "read-a-line"]})
    _finished(client, _start(client))
    embedded.clear()
    engine.read = []
    _import(client, tmp_path, "arrived.png")
    assert _wait(lambda: len(_runs(client)) == 2), "the import is one more run"
    new = next(_finished(client, r["job_id"]) for r in _runs(client) if r["documents"] is not None)
    assert [s["steps"] for s in new["steps"]] == [["lines", "read"]] and new["state"] == "done"
    (skip,) = new["skipped"]
    assert skip["step"] == "search" and "not ticked" in skip["why"] and "tick it" in skip["why"]
    assert engine.read == ["arrived.png"] and embedded == []


def test_the_kinds_of_names_reach_the_names_step(client, db, pages, tmp_path, engine, embedded, monkeypatch):
    """source.onboard.auto.job-answers-read: "the answers given under a purpose (which kinds of names, ...) are read
    by the steps they configure." The kinds ticked under the purpose become the names step's setting when the recipe
    is assembled, and, read from the saved answers, the sections its entity extraction finds when it runs."""
    from fichero_server.api.routes.workflow import chains
    from fichero_server.llm import local_models

    answers = {"purposes": ["entities"], "languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 64,
               "job_answers": {"entity_kinds": ["people", "organisations"]}}
    assembled = client.post("/api/recipes/assemble", json=answers).json()
    (names,) = [s for s in assembled["steps"] if s["job"] == "find-names-tag-words"]
    assert names["settings"] == {"kinds": ["people", "organisations"]}

    names = {"id": "names", "job": "find-names-tag-words", "model": {"spacy": "es_core_news_sm", "version": "bundled"}}
    _save(client, _recipe(tmp_path, LINES, READ, names), purposes=["entities"],
          job_answers={"entity_kinds": ["people", "organisations"]})
    (run,) = [r for r in _plan(client)["runs"] if r["steps"] == ["names"]]
    assert run["tool_config"] == {"extract_entities_only": {"entity_types": "people,organizations"}}

    # The spaCy pipeline at the model boundary: it finds a person, a place and an organisation on every page.

    from fichero_server.workflows.ner import providers

    class Finder:
        async def extract(self, text, *, language=None):
            return [providers._record(name=n, entity_type=t, provider_name="spacy", model_name=None) for n, t in
                    (("Juan Pérez", "person"), ("Quito", "location"), ("Cabildo de Quito", "organization"))]

    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: True)
    monkeypatch.setattr(providers, "get_ner_provider", lambda provider, model: Finder())
    done = _finished(client, _start(client))
    assert [s["state"] for s in done["steps"]] == ["done", "done"], done
    from fichero_server.models.knowledge import KnowledgeEntity

    assert {e.canonical_name for e in db.query(KnowledgeEntity)} == {"Juan Pérez", "Cabildo de Quito"}
