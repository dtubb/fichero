"""Recipe execution (#5390), tested to the spec (docs/contributor_manual/specs/source/models-chains-and-projects.md).

Behaviours: `source.recipe.start-runs-the-steps`, `source.recipe.step-skipped-says-why`,
`source.project.automatic-after-first-yes`, `source.onboard.just-do-it`, `source.onboard.tools-not-automation`.
Each test is named after its behaviour and quotes it. Everything goes through the public surface: the project
routes (`PUT /api/recipes/project`, `GET|POST /api/recipes/project/start`, `GET /api/recipes/project/runs/{id}`),
the import route, the activity tree, and the real job scheduler (a fresh one per test). The cards are stubs at
the model boundary only: a Kraken reader (at the Kraken runtime) and a checker that answer from memory (the real models wait for
credit); the import's thumbnails, embeds and NLP draft are no-ops (they load models).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from fichero_server.execution import jobs

CLOUD = {"cloud": "openai", "model": "gpt-5"}  # the checker's model (a stub answers for it)


def _png(path: Path) -> Path:
    from PIL import Image

    Image.new("RGB", (32, 32), (250, 250, 250)).save(str(path), format="PNG")
    return path


class Cards:
    """The stub models: a Kraken reader on this Mac (at the Kraken runtime) and a checker (chat).
    `fail_reading` makes the reader fail."""

    def __init__(self):
        self.read: list[str] = []
        self.checked: list[str] = []
        self.fail_reading = False
        self.times: dict[str, list[float]] = {"read": [], "check": []}

    def recognize(self, image_path, model_path, *, model_id=None, rendition_id=None, home=None):
        from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

        if self.fail_reading:
            raise RuntimeError("the reader could not be loaded")
        self.read.append(Path(image_path).name)
        self.times["read"].append(time.monotonic())
        text = "Yten dixo el testigo"
        return OCRGeometryResult(
            text=text, provider="kraken", model="kraken-mccatmus", source="kraken-htr",
            boxes=[OCRGeometryBox(text=text, bbox=[0.1, 0.1, 0.8, 0.05], level=OCRGeometryLevel.LINE,
                                  provider="kraken", model="kraken-mccatmus", source="kraken-htr",
                                  char_start=0, char_end=len(text),
                                  metadata={"baseline_px": [[3.0, 9.0], [28.0, 9.0]]})])

    async def chat(self, prompt, config, **kw):
        self.checked.append(prompt if isinstance(prompt, str) else json.dumps(prompt))
        self.times["check"].append(time.monotonic())
        return json.dumps({"verdict": "confirm", "why": "the passage says so", "correction": None})


@pytest.fixture(autouse=True)
def engine(monkeypatch, app_db):
    """A fresh scheduler, the pause off, the cards stubbed, the import's model-loading stages no-ops."""
    import fichero_server.llm as llm
    from fichero_server.importers import derivatives
    from fichero_server.llm import kraken_runtime
    from fichero_server.workflows import validation

    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(False)
    derivatives.register_job_kinds()
    for kind in (derivatives.THUMBNAIL_KIND, derivatives.EMBED_KIND, derivatives.NLP_KIND):
        monkeypatch.setitem(jobs.KINDS, kind, jobs.Kind(run=lambda db, subject: None, model=None))
    cards = Cards()
    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", cards.recognize)
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model",
                        lambda ref: ("/models/mccatmus.mlmodel", "kraken-mccatmus"))
    monkeypatch.setattr(llm, "chat", cards.chat)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    yield cards
    jobs.set_paused(False)


@pytest.fixture
def pages(db, tmp_path):
    """Two photographs, and one statement found on the first; the shipped workflows installed, as the engine
    installs them at start."""
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.models.knowledge import KnowledgeClaim
    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)

    docs = []
    for i in range(2):
        doc = Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image,
                       path=str(_png(tmp_path / f"p{i}.png")))
        db.save(doc)
        docs.append(doc)
    db.save(KnowledgeClaim(text="Juan sold a house.", svo_subject="Juan", svo_verb="sold", svo_object="a house",
                           source_document_id=docs[0].id, source_excerpt="vendió Juan una casa"))
    return docs


def _recipe(tmp_path, *steps):
    return {"fichero_recipe": 1, "id": "t/run", "version": "0.1.0", "title": "t", "steps": list(steps)}


def _steps(tmp_path):
    return [
        {"id": "split", "job": "split-pages", "model": {"builtin": "page-splitter"}},
        {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
        {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}},
        {"id": "check", "job": "check", "settings": {"layer": "claims"}, "model": CLOUD, "runs_on": "cloud:openai"},
        {"id": "names", "job": "find-names-tag-words"},
        {"id": "export", "job": "export", "settings": {"formats": ["pagexml"], "folder": str(tmp_path / "edition")}},
    ]


def _save(client, recipe, *, purpose="transcribe", cloud_allowed=True):
    r = client.put("/api/recipes/project", json={"answers": {"purpose": purpose, "cloud_allowed": cloud_allowed},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text


def _wait(condition, seconds=60.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.1)
    return False


def _runs(client):
    r = client.get("/api/recipes/project/runs")
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _run_status(client, job_id):
    r = client.get(f"/api/recipes/project/runs/{job_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _finished(client, job_id):
    assert _wait(lambda: _run_status(client, job_id)["state"] in ("done", "failed", "cancelled")), \
        _run_status(client, job_id)
    return _run_status(client, job_id)


def _start(client):
    r = client.post("/api/recipes/project/start")
    assert r.status_code == 200, r.text
    return r.json()["started"]["job_id"]


def test_source_recipe_start_runs_the_steps(client, db, pages, tmp_path, engine):
    """source.recipe.start-runs-the-steps: "pressing Start runs the recipe over the project's material: its
    steps in order, each as the job its card names (a shipped workflow run for finding lines, reading a line
    or a page, correcting, finding names and finding statements; a check run for `check`; the project's synced
    folder for `export`), together as one `run-a-recipe` job in Activity whose children are those runs; a step
    starts only when the one before it has finished, and a step that fails stops the steps after it, saying
    which.\""""
    _save(client, _recipe(tmp_path, *_steps(tmp_path)))
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    assert [(s["steps"], s["card"], s["state"]) for s in run["steps"]] == [
        (["lines", "read"], "workflow", "done"), (["check"], "check", "done"), (["export"], "export", "done")]
    assert sorted(engine.read) == ["p0.png", "p1.png"] and len(engine.checked) == 1  # both pages, the statement

    tree = client.get(f"/api/activity/jobs/{run['job_id']}").json()
    children = {c["id"]: c for c in tree["children"]}
    read, check = (children[s["child_id"]] for s in run["steps"][:2])
    assert (read["kind"], read["state"], check["kind"], check["state"]) == ("workflow", "done", "check", "done")
    assert min(engine.times["check"]) > max(engine.times["read"]), "a step starts when the one before it finished"
    assert _wait(lambda: len(list((tmp_path / "edition").glob("*/*.page.xml"))) == 2), "the synced folder is written"

    # A step that fails stops the steps after it, and says which.
    engine.fail_reading, engine.checked = True, []
    failed = _finished(client, _start(client))
    assert failed["state"] == "failed" and "lines, read" in failed["reason"]
    assert [(s["steps"], s["state"]) for s in failed["steps"]] == [(["lines", "read"], "failed"),
                                                                   (["check"], "not run"), (["export"], "not run")]
    assert engine.checked == []


def test_source_recipe_step_skipped_says_why(client, db, pages, tmp_path, engine):
    """source.recipe.step-skipped-says-why: "a step Start cannot run (no model, a condition Start cannot honour
    yet, a cloud step in a project that keeps its pages on this Mac, a job no card runs yet) is skipped, and the
    plan and the recipe run name the step and why; the other steps still run. A recipe with nothing runnable, or
    one that fails the recipe check, never starts.\""""
    steps = _steps(tmp_path) + [{"id": "maybe", "job": "find-lines", "model": {"kraken": "blla",
                                                                               "kraken_version": "bundled"},
                                 "when": {"spreads_detected": True}}]
    _save(client, _recipe(tmp_path, *steps), cloud_allowed=False)
    plan = client.get("/api/recipes/project/start").json()
    why = {s["step"]: s["why"] for s in plan["skipped"]}
    assert set(why) == {"split", "check", "names", "maybe"} and plan["refusals"] == []
    assert "no card runs" in why["split"] and "off this Mac" in why["check"] and "no model" in why["names"]
    assert "condition" in why["maybe"]
    run = _finished(client, _start(client))
    assert [s["steps"] for s in run["steps"]] == [["lines", "read"], ["export"]] and run["state"] == "done"
    assert {s["step"] for s in run["skipped"]} == set(why) and engine.checked == []

    _save(client, _recipe(tmp_path, {"id": "split", "job": "split-pages", "model": {"builtin": "page-splitter"}}))
    r = client.post("/api/recipes/project/start")
    assert r.status_code == 422 and "nothing" in r.json()["detail"]
    _save(client, _recipe(tmp_path, {"id": "x", "job": "no-such-job", "model": CLOUD}))
    assert client.post("/api/recipes/project/start").status_code == 422


def _import(client, tmp_path, name):
    path = _png(tmp_path / name)
    r = client.post("/api/ingest/files", json={"paths": [str(path)]})
    assert r.status_code == 200, r.text
    return path


def test_source_project_automatic_after_first_yes(client, db, pages, tmp_path, engine):
    """source.project.automatic-after-first-yes: "nothing in a project runs by itself until the person presses
    Start at the end of setup (the first yes), which shows what will run, on how many pages, with an estimate".
    Before the yes, new material runs nothing; the yes runs the recipe."""
    _save(client, _recipe(tmp_path, *_steps(tmp_path)))
    _import(client, tmp_path, "before.png")
    time.sleep(1.0)
    assert _runs(client) == [] and engine.read == []
    plan = client.get("/api/recipes/project/start").json()
    assert plan["estimate"]["pages"] == 3
    assert [r["steps"] for r in plan["runs"]] == [["lines", "read"], ["check"], ["export"]]
    run = _finished(client, _start(client))
    assert run["state"] == "done" and sorted(engine.read) == ["before.png", "p0.png", "p1.png"]


def test_source_onboard_just_do_it(client, db, pages, tmp_path, engine):
    """source.onboard.just-do-it: "on a "just do it" purpose, after Start, new material runs through the
    recipe's automatic steps with no further question: each import is one `run-a-recipe` job over the pages it
    brought, and nothing runs for material already there.\""""
    _save(client, _recipe(tmp_path, *_steps(tmp_path)))
    _finished(client, _start(client))
    engine.read = []
    _import(client, tmp_path, "arrived.png")
    assert _wait(lambda: len(_runs(client)) == 2), "the import is one more run, in Activity"
    runs = [_finished(client, j["job_id"]) for j in _runs(client)]
    new = next(r for r in runs if r["documents"] is not None)
    from fichero_server.models import Document

    named = {db.get(Document, d).name for d in new["documents"]}
    assert named == {"arrived.png"} and new["state"] == "done" and engine.read == ["arrived.png"]


def test_source_onboard_tools_not_automation(client, db, pages, tmp_path, engine):
    """source.onboard.tools-not-automation: "on a "tools" purpose (edit, decipher, train, not sure), nothing
    runs at import that the person did not ask for, and that purpose's tools are offered first." Start still
    runs what the person pressed it for; material that arrives later runs nothing."""
    _save(client, _recipe(tmp_path, *_steps(tmp_path)), purpose="edit-corpus")
    _finished(client, _start(client))
    engine.read = []
    _import(client, tmp_path, "later.png")
    time.sleep(1.5)
    assert len(_runs(client)) == 1 and engine.read == []
