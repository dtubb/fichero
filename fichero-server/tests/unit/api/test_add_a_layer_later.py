"""Adding a layer to a project later (`source.onboard.add-layer`, #5470).

Why it matters: a historian who started with "Just transcribe" and later wants the names found must not
have to set the project up again, and must not have the engine quietly run a new model over a thousand
pages. So adding the layer is one audited, undoable action through the recipe: the layer's steps join
the recipe (the person's own model choices stay), the jobs it needs for the pages ALREADY in the project
are proposed in the Start plan with the plan's estimate (pages, where it runs, cost) and each job's
explanation from the topic registry, nothing runs until the person presses Start, Start runs exactly
those jobs through the job queue, and undoing (or removing the layer before Start) takes the layer and
its proposed jobs away. Everything goes through the real routes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.models import ActionAudit, Document, DocType

MCCATMUS = {"zenodo": "10.5281/zenodo.13788177"}
NAMES = "find-names-tag-words"


@pytest.fixture(autouse=True)
def hold_the_run(monkeypatch):
    """Runs are queued, never executed here: these tests pin what is queued and when, not the models.
    The Spanish spaCy pipeline and the recipe's local models count as present on this Mac (which
    models a Mac can serve is test_local_model_choice.py's), so the plan's only refusal would be ours
    to find."""
    from fichero_server.execution import jobs
    from fichero_server.llm import local_models
    from fichero_server.recipes import start

    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: True)
    monkeypatch.setattr(start, "local_models_this_mac_cannot_serve", lambda runs: [])
    monkeypatch.setattr(start, "local_models_to_download", lambda runs: [])  # #5583: a missing model is a download


@pytest.fixture
def project(client, db):
    """Three pages already imported (two of a PDF, one image), set up to "Just transcribe" in Spanish with
    the reader swapped to McCATMuS (a person's choice in the Inspector)."""
    pdf = Document(name="deed.pdf", doc_type=DocType.file)
    db.save(pdf)
    for n in (1, 2):
        db.save(Document(name=f"p{n}", doc_type=DocType.page, parent_id=pdf.id, sequence=n))
    db.save(Document(name="letter.jpg", doc_type=DocType.file))
    answers = {"purpose": "transcribe", "languages": ["es"], "scripts": ["Latn"], "material": "handwriting",
               "mac_memory_gb": 16}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    for step in recipe["steps"]:
        if step["job"] == "read-a-line":
            step["model"] = MCCATMUS
    r = client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe})
    assert r.status_code == 200, r.text
    return recipe


def _start(client):
    r = client.post("/api/recipes/project/start")
    assert r.status_code == 200, r.text
    return r.json()


def _runs(client):
    return client.get("/api/recipes/project/runs").json()["items"]


def _add(client, **body):
    return client.post("/api/recipes/project/layers", json=body)


def test_adding_a_layer_proposes_its_jobs_for_the_pages_already_there_with_an_estimate(client, project):
    """After the first yes, adding the entities layer proposes finding names on the 3 units already
    imported, on this Mac, free, each job explained by its topic; the transcription steps already run
    are not proposed again, and the person's reader stays."""
    _start(client)
    r = _add(client, layers=["entities"])
    assert r.status_code == 200, r.text
    plan = r.json()
    assert [run["steps"] for run in plan["runs"]] == [[NAMES]]
    assert plan["refusals"] == []
    assert plan["estimate"]["pages"] == 3
    [row] = plan["estimate"]["runs"]
    assert row["where"] == "this-mac" and row["pages"] == 3 and row["cost_usd"] == 0.0
    [step] = plan["proposed"]["steps"]
    topic = client.get(f"/api/topics/{NAMES}").json()
    assert plan["proposed"]["layers"] == ["entities"]
    assert step["layer"] == "entities" and step["topic"] == NAMES
    assert step["title"] == topic["title"] and step["explanation"] == f"{topic['short']} {topic['long']}"
    saved = client.get("/api/recipes/project").json()
    assert saved["answers"]["layers"] == ["entities"]
    assert [s["job"] for s in saved["recipe"]["steps"]] == ["find-lines", "read-a-line", "correct", NAMES]
    assert next(s for s in saved["recipe"]["steps"] if s["job"] == "read-a-line")["model"] == MCCATMUS


def test_nothing_runs_until_start_and_start_runs_the_proposed_jobs_through_the_queue(client, project):
    """The add queues nothing; Start queues one recipe run over all the material whose only card is the
    added layer's, and the proposal is then done with."""
    _start(client)
    before = _runs(client)
    _add(client, layers=["entities"])
    assert _runs(client) == before
    plan = _start(client)
    assert plan["proposed"] is None
    [newest, *_] = _runs(client)
    assert len(_runs(client)) == len(before) + 1
    assert newest["documents"] is None  # all the project's material, not only new pages
    assert [s["steps"] for s in newest["steps"]] == [[NAMES]]
    assert newest["state"] in ("queued", "waiting")


def test_undo_takes_the_layer_and_its_proposed_jobs_away_and_the_audit_names_the_action(client, db, project,
                                                                                    test_package):
    """The add is in the audit log by name and is undone like every change: answers, recipe and the
    proposal are back as they were."""
    _start(client)
    original = client.get("/api/recipes/project").json()
    _add(client, layers=["entities"])
    assert (Path(test_package) / "recipe" / "proposed.yaml").is_file()
    [audit] = [a for a in db.query(ActionAudit) if a.action_name == "project.add_layer"]
    assert client.post(f"/api/actions/audit/{audit.id}/undo").status_code == 200
    assert client.get("/api/recipes/project").json() == original
    plan = client.get("/api/recipes/project/start").json()
    assert plan["proposed"] is None
    assert not (Path(test_package) / "recipe" / "proposed.yaml").exists()


def test_removing_the_layer_before_start_withdraws_its_proposed_jobs(client, project):
    """Changed one's mind before pressing Start: the layer leaves the recipe and nothing stays proposed."""
    _start(client)
    _add(client, layers=["entities"])
    r = _add(client, layers=["entities"], remove=True)
    assert r.status_code == 200, r.text
    assert r.json()["proposed"] is None
    saved = client.get("/api/recipes/project").json()
    assert NAMES not in [s["job"] for s in saved["recipe"]["steps"]] and saved["answers"]["layers"] == []


def test_before_the_first_yes_the_added_layer_runs_with_the_whole_recipe(client, project):
    """A project not yet started shows the whole recipe, the added layer in it; Start runs it all once and
    clears the proposal, so the names are not run a second time."""
    plan = _add(client, layers=["entities"]).json()
    assert [run["steps"] for run in plan["runs"]] == [["find-lines", "read-a-line"], ["correct"], [NAMES]]
    assert plan["proposed"]["layers"] == ["entities"]
    assert _start(client)["proposed"] is None


def test_a_language_added_proposes_the_recipe_again_and_nothing_for_the_pages_there(client, project):
    """A language, as the Inspector's field does, re-proposes the recipe from the answers; re-reading
    what is already there stays Start's or a run's (the 2026-10-04 default)."""
    plan = _add(client, languages=["la"]).json()
    assert plan["proposed"] is None
    assert client.get("/api/recipes/project").json()["answers"]["languages"] == ["es", "la"]


def test_what_cannot_be_added_is_refused_in_words(client, db):
    """No setup yet, an unknown layer, or a layer the purpose already has: 422, saying why, and nothing
    written."""
    r = _add(client, layers=["entities"])
    assert r.status_code == 422 and "set up" in r.text
    client.put("/api/recipes/project", json={"answers": {"purpose": "entities", "languages": ["es"],
                                                         "scripts": ["Latn"]}, "recipe": None})
    r = _add(client, layers=["poetry"])
    assert r.status_code == 422 and "entities" in r.text  # names the layers it can add
    r = _add(client, layers=["entities"])
    assert r.status_code == 422 and "already" in r.text
    assert not [a for a in db.query(ActionAudit) if a.action_name == "project.add_layer"]
    assert "layers" not in client.get("/api/recipes/project").json()["answers"]


def test_setup_assembles_an_added_layer_too(client):
    """The app re-proposes from the saved answers; an added layer in them keeps its steps, in order."""
    r = client.post("/api/recipes/assemble", json={"purpose": "transcribe", "languages": ["es"],
                                                   "scripts": ["Latn"], "layers": ["entities"]})
    assert [s["job"] for s in r.json()["steps"]] == ["find-lines", "read-a-line", "correct", NAMES]


def test_the_plan_says_which_layers_can_be_added_now(client, project):
    """WHY: the app offers exactly the engine's list (#5470). If this breaks, the Inspector offers layers
    the engine refuses, or works the rule out itself (a second path). Adding one takes it off the list."""
    before = _start(client)["addable"]
    assert before and "entities" in before
    assert all(layer not in before for layer in ("check", "output", "train"))
    after = _add(client, layers=["entities"]).json()["addable"]
    assert "entities" not in after and set(after) < set(before)
