"""Recipe runs (#5497, #5498), tested to the spec (docs/contributor_manual/specs/source/models-chains-and-projects.md).

Behaviours: `source.recipe.start-runs-the-steps`, `source.recipe.failed-step-offered-again`,
`source.recipe.run-status-is-activity`, `source.onboard.estimate-before-start`. Found by the operator running the
app end to end (2026-10-05): the names step said its workflow "is not in this build" though it ran by name; Correct
failing stopped names, which does not need it; after a failed run the plan dropped the failed steps; run-status,
Activity and Start's response disagreed; the page count went from 5 to 9 without a word.

Through the public routes (`PUT /api/recipes/project`, `GET|POST /api/recipes/project/start`,
`GET /api/recipes/project/runs/{id}`, `GET /api/activity/jobs/{id}`) and the real scheduler (a fresh one per test).
Stubs only at the boundary: spaCy's NER call (the names test), and, where the test is about the order of steps and
not what they make, the step's workflow run itself (`runner._run_workflow`), which writes the step's job row as a
real run does.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from fichero_server.execution import jobs

CLOUD = {"cloud": "openai", "model": "gpt-5"}
SPACY = {"spacy": "es_core_news_sm", "version": "3.8.0"}


@pytest.fixture(autouse=True)
def engine(monkeypatch, app_db):
    """A fresh scheduler with the pause off; the spaCy pipeline counts as on this Mac; the LLM preflight passes."""
    from fichero_server.llm import local_models
    from fichero_server.workflows import validation

    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(False)
    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: True)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    yield
    jobs.set_paused(False)


def _png(path: Path) -> Path:
    from PIL import Image

    Image.new("RGB", (32, 32), (250, 250, 250)).save(str(path), format="PNG")
    return path


@pytest.fixture
def pages(db, tmp_path):
    """Two photographs that already carry their text."""
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    docs = []
    for i, text in enumerate(["Don Juan de Mosquera vendió una casa en Popayán.", "Ysabel de Rojas fue a Cali."]):
        doc = Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image,
                       path=str(_png(tmp_path / f"p{i}.png")), page_content=text)
        db.save(doc)
        docs.append(doc)
    return docs


def _save(client, steps, *, cloud_allowed=True):
    recipe = {"fichero_recipe": 1, "id": "t/runs", "version": "0.1.0", "title": "t", "steps": steps}
    r = client.put("/api/recipes/project", json={"answers": {"purpose": "transcribe", "cloud_allowed": cloud_allowed},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text


def _wait(condition, seconds=60.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.1)
    return False


def _status(client, job_id):
    r = client.get(f"/api/recipes/project/runs/{job_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _finished(client, job_id):
    assert _wait(lambda: _status(client, job_id)["state"] in ("done", "failed", "cancelled")), _status(client, job_id)
    return _status(client, job_id)


def _start(client, **body):
    r = client.post("/api/recipes/project/start", json=body or None)
    assert r.status_code == 200, r.text
    return r.json()


# --- #5497: the names step finds its shipped workflow ---------------------------------------------------------------


def test_names_step_runs_the_shipped_names_workflow_held_under_an_old_id(client, db, pages, monkeypatch):
    """source.recipe.start-runs-the-steps, for the names step (#5497). WHY: a project (and the global library)
    seeded before preset ids were stable (#4450) holds "Extract Entities" under a random id; Start looked it up only
    by the id minted from its name and said the workflow "is not in this build", though running it by name worked.
    The recipe holds the preset's stable key; the run finds the seeded row by that preset's name when the id misses.
    And no ordering prefix ("2 · ") reaches what people see: the plan, Start's answer, the run."""
    from fichero_server.knowledge import spacy_ner
    from fichero_server.models import Workflow
    from fichero_server.workflows import default_workflows

    # The seeded row under a pre-#4450 random id, and the global library is this project (so it misses too).
    stored = next(w for w in db.all(Workflow) if w.name == "Extract Entities")
    legacy = stored.model_copy(update={"id": str(uuid.uuid4())})
    db.delete(stored)
    db.save(legacy)
    monkeypatch.setattr(default_workflows, "get_global_defaults_database", lambda: db)
    found: list[str] = []

    def extract(text, language=None, model=None):
        found.append(text)
        return [spacy_ner.EntitySpan(text="Popayán", fichero_type="location", start=text.index("Popayán"),
                                     end=text.index("Popayán") + 7, label="LOC")] if "Popayán" in text else []

    monkeypatch.setattr(spacy_ner, "extract_entities", extract)
    # The pages already carry their text: the reading card is stubbed, the names card runs for real.
    from fichero_server.recipes import runner

    real, stub = runner._run_workflow, Steps()
    monkeypatch.setattr(runner, "_run_workflow", lambda db, card, documents, parent: (
        real if card["job"] == "find-names-tag-words" else stub.run)(db, card, documents, parent))
    _save(client, RECIPE[:2] + [{"id": "names", "job": "find-names-tag-words", "model": SPACY}])

    plan = client.get("/api/recipes/project/start").json()
    assert plan["refusals"] == [] and [w["workflow"] for w in plan["workflows"]][-1] == "Extract Entities"
    assert not any("·" in w["workflow"] for w in plan["workflows"])
    started = _start(client)
    assert started["started"]["workflows"][-1] == "Extract Entities"
    run = _finished(client, started["started"]["job_id"])
    assert run["state"] == "done", run
    assert [(s["steps"], s["state"]) for s in run["steps"]][-1] == (["names"], "done")
    assert found, "spaCy read the pages: the shipped names workflow ran"


# --- #5498: runs, with stub steps ------------------------------------------------------------------------------------


class Steps:
    """The workflow cards, stubbed: each writes its own job row under the recipe's (as a run does) and ends as
    `outcome` says (done unless named)."""

    def __init__(self):
        self.ran: list[list[str]] = []
        self.fail: dict[str, str] = {}

    def run(self, db, card, documents, parent):
        child = f"thread-{uuid.uuid4().hex[:12]}"
        self.ran.append(card["steps"])
        why = next((self.fail[s] for s in card["steps"] if s in self.fail), None)
        state = "failed" if why else "done"
        jobs._record(db, child, kind="workflow", subject=child, parent_id=None, state=state, reason=why,
                     name=card["workflow"])
        jobs.set_parent(db, child, parent)
        return child, state, why


@pytest.fixture
def steps(monkeypatch):
    from fichero_server.recipes import runner

    stub = Steps()
    monkeypatch.setattr(runner, "_run_workflow", stub.run)
    return stub


RECIPE = [
    {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
    {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}},
    {"id": "correct", "job": "correct", "model": CLOUD, "runs_on": "cloud:openai"},
    {"id": "names", "job": "find-names-tag-words", "model": SPACY},
    {"id": "statements", "job": "find-statements", "model": CLOUD, "runs_on": "cloud:openai"},
]


def test_a_failed_step_stops_only_the_steps_that_need_it(client, db, pages, steps):
    """source.recipe.start-runs-the-steps (#5498): "a step that fails stops only the steps that need what it would
    have given". WHY: Correct failing (a model too big for the Mac) stopped names, which reads the lines whether
    they were corrected or not, so People and places never got found. Names runs on the uncorrected reading; a
    step that needs what nothing gave (statements need the names) waits, and says which step and why."""
    _save(client, RECIPE)
    steps.fail = {"correct": "the model needs 8 GB free", "names": "spaCy could not load"}
    run = _finished(client, _start(client)["started"]["job_id"])

    assert steps.ran == [["lines", "read"], ["correct"], ["names"]], "names ran after correct failed"
    state = {tuple(s["steps"]): s for s in run["steps"]}
    assert state[("lines", "read")]["state"] == "done" and state[("correct",)]["state"] == "failed"
    assert state[("names",)]["state"] == "failed"
    waiting = state[("statements",)]
    assert waiting["state"] == "not run" and "mentions" in waiting["why"] and "names failed" in waiting["why"]
    assert run["state"] == "failed" and "correct failed" in run["reason"] and "statements not run" in run["reason"]


def test_failed_steps_stay_in_the_plan_to_run_again(client, db, pages, steps):
    """source.recipe.failed-step-offered-again (#5498): "after a run, a step it did not finish stays in the Start
    plan, marked failed (or not run) with why, and Start runs it again". WHY: once a run failed, the plan listed
    only an added layer's step; Transcribe was gone and `--redo` had to be guessed."""
    from fichero_server.recipes.project import write_proposed

    _save(client, RECIPE)
    steps.fail = {"correct": "the model needs 8 GB free"}
    _finished(client, _start(client)["started"]["job_id"])
    # An added layer proposes its step: the plan is then that step AND what did not finish.
    write_proposed(Path(db.path).parent, {"layers": ["entities"], "steps": ["names"]})

    plan = client.get("/api/recipes/project/start").json()
    runs = {tuple(r["steps"]): r for r in plan["runs"]}
    assert set(runs) == {("correct",), ("names",)}, "the done steps are not offered; the failed one is"
    assert runs[("correct",)]["last_run"] == "failed" and "8 GB" in runs[("correct",)]["last_why"]
    assert runs[("correct",)]["note"].startswith("failed last time")
    assert runs[("names",)]["last_run"] is None

    steps.fail, steps.ran = {}, []
    started = _start(client)
    run = _finished(client, started["started"]["job_id"])
    assert [s["steps"] for s in run["steps"]] == [["correct"], ["names"]] and run["state"] == "done"
    assert all(r.get("last_run") is None for r in client.get("/api/recipes/project/start").json()["runs"])


def test_start_answer_names_what_started(client, db, pages, steps):
    """source.recipe.start-runs-the-steps (#5498): Start's answer is the run it started. WHY: its
    `started.workflows` listed one workflow while its `runs` listed three (the plan for next time), so nobody
    could tell what was running."""
    from fichero_server.recipes.project import write_proposed

    _save(client, RECIPE)
    _finished(client, _start(client)["started"]["job_id"])
    write_proposed(Path(db.path).parent, {"layers": ["entities"], "steps": ["names"]})

    answer = _start(client)
    assert answer["started"]["workflows"] == [w["workflow"] for w in answer["workflows"]] == ["Extract Entities"]
    assert [r["steps"] for r in answer["runs"]] == [["names"]]
    run = _finished(client, answer["started"]["job_id"])
    assert [s["steps"] for s in run["steps"]] == [r["steps"] for r in answer["runs"]]


def test_run_status_is_what_activity_shows(client, db, pages, steps):
    """source.recipe.run-status-is-activity (#5498): "a recipe run's step states are its steps' own jobs, the rows
    Activity shows". WHY: run-status said 'waiting' with one step while Activity showed Kraken done and the review
    started: two accounts of one run."""
    _save(client, RECIPE)
    steps.fail = {"correct": "the model needs 8 GB free"}
    run = _finished(client, _start(client)["started"]["job_id"])
    # A step's job is changed where Activity reads it (a person cancels it, a retry ends it): run-status follows.
    names = next(s for s in run["steps"] if s["steps"] == ["names"])
    jobs._record(db, names["child_id"], kind="workflow", subject=names["child_id"], parent_id=None,
                 state="cancelled", reason="Cancelled by you", name=None)

    tree = client.get(f"/api/activity/jobs/{run['job_id']}").json()
    activity = {c["id"]: c["state"] for c in tree["children"]}
    status = _status(client, run["job_id"])
    assert {s["child_id"]: s["state"] for s in status["steps"] if s["child_id"]} == activity
    assert activity[names["child_id"]] == "cancelled"


def test_page_count_says_what_it_counts(db, tmp_path):
    """source.onboard.estimate-before-start (#5498): the plan's page count says what it counts. WHY: the plan said 5
    pages before a run and 9 after, for 4 photographs and 1 PDF page, without a word; the same 4 photographs were
    taken in again as new documents, which the count now names."""
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.recipes.done import material

    folder = Document(name="Notebook 1", doc_type=DocType.folder)
    db.save(folder)
    for i in range(4):
        db.save(Document(name=f"c01_{i}.jpg", doc_type=DocType.file, file_type=FileType.image, parent_id=folder.id,
                         path=str(_png(tmp_path / f"c01_{i}.png"))))
    pdf = Document(name="dialogo.pdf", doc_type=DocType.file, file_type=FileType.pdf)
    db.save(pdf)
    db.save(Document(name="dialogo.pdf — page 1", doc_type=DocType.page, parent_id=pdf.id))

    counted = material(db)
    assert counted["pages"] == 5
    assert counted["sentence"] == ("4 photographs + 1 PDF page = 5 pages; the project holds 7 documents: these, and "
                                   "1 PDF its pages came from, 1 folder")

    for i in range(4):  # the same photographs, taken in a second time
        db.save(Document(name=f"c01_{i}.jpg", doc_type=DocType.file, file_type=FileType.image,
                         path=str(_png(tmp_path / f"again{i}.png"))))
    counted = material(db)
    assert counted["pages"] == 9
    assert counted["sentence"].startswith("8 photographs + 1 PDF page = 9 pages")
    assert counted["sentence"].endswith("8 photographs share a file name with another: copies taken in twice?")
