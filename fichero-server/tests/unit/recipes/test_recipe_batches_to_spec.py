"""A recipe run on one folder, and in batches at archive scale (#5540), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md; rule 9 of compute/jobs-and-fine-tuning.md).

Behaviours: `source.recipe.folder-scoped-start`, `source.recipe.batch-at-archive-scale`,
`source.recipe.batch-checkpoint`, `activity.run.progress-per-folder`. WHY: a recipe run was project-wide only, and
handed every unfinished page of a step to the workflow at once: 800 folders of 200 pages queued 160,000 page jobs
per step, nothing was readable until every page had been through every step, and there was no "run the whole recipe
on this folder".

Through the public routes (`GET|POST /api/recipes/project/start`, `GET /api/recipes/project/runs/{id}`) and the
real scheduler (a fresh one per test). Stubbed only at the boundary: each step's workflow run
(`runner._run_workflow`), which writes the step's job row as a real run does and records the pages it was handed.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from fichero_server.execution import jobs

CLOUD = {"cloud": "openai", "model": "gpt-5"}
SPACY = {"spacy": "es_core_news_sm", "version": "3.8.0"}
#: Two cards (finding and reading lines, as one; then names). The stubbed runs leave no lines, readings or names on a
#: page, so neither can tell it has done a page (`source.recipe.done-is-not-redone`): a card run again on a page
#: shows here as a second call.
RECIPE = [
    {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
    {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}},
    {"id": "names", "job": "find-names-tag-words", "model": SPACY},
]


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


class Steps:
    """The workflow cards, stubbed: each records (step, pages handed) and the run's reason at that moment, writes its
    own job row under the recipe's, and ends done; `interrupt` makes one call end as the project closing would
    (the row left running, carried on at the next open)."""

    def __init__(self):
        self.ran: list[tuple[str, list[str]]] = []
        self.reasons: list[str] = []
        self.interrupt: tuple[str, int] | None = None  # (step, which call of it)

    def run(self, db, card, documents, parent):
        step = card["steps"][0]
        self.reasons.append(jobs.read_job(db, parent)["reason"])
        calls = sum(1 for s, _ in self.ran if s == step)
        if self.interrupt == (step, calls):
            self.interrupt = None
            raise jobs.JobOutOfReach("Interrupted: the project was closed; carries on when it opens again")
        self.ran.append((step, list(documents)))
        child = f"thread-{uuid.uuid4().hex[:12]}"
        jobs._record(db, child, kind="workflow", subject=child, parent_id=None, state="done", reason=None,
                     name=card["workflow"])
        jobs.set_parent(db, child, parent)
        return child, "done", None


@pytest.fixture
def steps(monkeypatch):
    from fichero_server.recipes import runner

    stub = Steps()
    monkeypatch.setattr(runner, "_run_workflow", stub.run)
    return stub


def _png(path: Path) -> Path:
    from PIL import Image

    Image.new("RGB", (32, 32), (250, 250, 250)).save(str(path), format="PNG")
    return path


def _folder(db, name, parent=None):
    from fichero_server.models import DocType, Document

    folder = Document(name=name, doc_type=DocType.folder, parent_id=parent)
    db.save(folder)
    return folder.id


def _photos(db, tmp_path, folder, n):
    """`n` photographs in the folder, each already carrying its text."""
    from fichero_server.models import DocType, Document, FileType

    ids = []
    for _ in range(n):
        name = f"{uuid.uuid4().hex[:8]}.png"
        doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, parent_id=folder,
                       path=str(_png(tmp_path / name)), page_content="Don Juan de Mosquera vendió una casa.")
        db.save(doc)
        ids.append(doc.id)
    return ids


@pytest.fixture
def archive(db, tmp_path):
    """Folder A (2 photographs, and folder A1 inside it with 1), folder B (2), and 1 photograph in no folder."""
    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    a = _folder(db, "A")
    a1 = _folder(db, "A1", parent=a)
    b = _folder(db, "B")
    return {"A": a, "A1": a1, "B": b, "a": _photos(db, tmp_path, a, 2), "a1": _photos(db, tmp_path, a1, 1),
            "b": _photos(db, tmp_path, b, 2), "loose": _photos(db, tmp_path, None, 1)}


def _save(client):
    recipe = {"fichero_recipe": 1, "id": "t/batches", "version": "0.1.0", "title": "t", "steps": RECIPE}
    r = client.put("/api/recipes/project", json={"answers": {"purpose": "transcribe", "cloud_allowed": True},
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


def test_a_folder_start_covers_only_that_folders_pages(client, db, archive, steps):
    """source.recipe.folder-scoped-start: the plan, its estimate and the run cover the folder's live pages, those of
    its folders inside it included, and no page outside it. WHY: Start ran the whole project or nothing."""
    _save(client)
    inside = set(archive["a"] + archive["a1"])

    plan = client.get("/api/recipes/project/start", params={"folder_id": archive["A"]}).json()
    assert plan["folder_id"] == archive["A"] and plan["estimate"]["pages"] == 3, plan["estimate"]
    assert all(r["of"] == 3 for r in plan["runs"]), plan["runs"]
    assert client.get("/api/recipes/project/start").json()["estimate"]["pages"] == 6, "the whole project unchanged"

    started = _start(client, folder_id=archive["A"])
    assert started["started"]["folder_id"] == archive["A"] and started["started"]["pages"] == 3
    run = _finished(client, started["started"]["job_id"])
    assert run["state"] == "done" and run["folder_id"] == archive["A"], run
    touched = {page for _step, pages in steps.ran for page in pages}
    assert touched == inside, "the run touched pages outside the folder, or missed one inside it"


def test_a_folder_not_in_the_project_is_refused(client, db, archive, steps):
    """source.recipe.folder-scoped-start: a folder not in the project is refused (422), plan and Start; a folder
    with no pages refuses Start, and nothing is queued."""
    _save(client)
    assert client.get("/api/recipes/project/start", params={"folder_id": "nope"}).status_code == 422
    assert client.post("/api/recipes/project/start", json={"folder_id": "nope"}).status_code == 422
    empty = _folder(db, "Empty")
    plan = client.get("/api/recipes/project/start", params={"folder_id": empty}).json()
    assert "the folder has no pages to run on" in plan["refusals"]
    r = client.post("/api/recipes/project/start", json={"folder_id": empty})
    assert r.status_code == 422 and "no pages" in r.text
    assert not jobs.find_jobs(db, kinds=["run-a-recipe"])


def test_every_step_finishes_a_batch_before_the_next_batch(client, db, archive, steps, monkeypatch):
    """source.recipe.batch-at-archive-scale: a batch is one folder or at most BATCH_PAGE_LIMIT pages, whichever is
    smaller, and every step finishes on it before the next batch starts. WHY: each step was handed every page of
    the project at once, so no volume was readable until all of them had been through every step."""
    from fichero_server.recipes import runner

    monkeypatch.setattr(runner, "BATCH_PAGE_LIMIT", 1)
    _save(client)
    run = _finished(client, _start(client, folder_id=archive["B"])["started"]["job_id"])

    assert run["state"] == "done", run
    b1, b2 = archive["b"]
    assert steps.ran == [("lines", [b1]), ("names", [b1]), ("lines", [b2]), ("names", [b2])], (
        "step 2 ran on batch 1 before step 1 ran on batch 2")


def test_a_folder_is_one_batch_under_the_limit(client, db, archive, steps):
    """source.recipe.batch-at-archive-scale: under the page limit a batch is the folder: no step is handed two
    folders' pages at once; pages in no folder are a folder of their own."""
    _save(client)
    run = _finished(client, _start(client)["started"]["job_id"])

    assert run["state"] == "done", run
    folders = [set(archive["a"]), set(archive["a1"]), set(archive["b"]), set(archive["loose"])]
    handed = [set(pages) for step, pages in steps.ran if step == "lines"]
    assert sorted(map(sorted, handed)) == sorted(map(sorted, folders)), handed
    assert [s for s, _ in steps.ran] == ["lines", "names"] * 4


def test_the_run_says_how_many_folders_are_done(client, db, archive, steps):
    """activity.run.progress-per-folder: the run's row says "N of M folders done" as it goes and how many folders
    when it ends; its status carries folders_done and folders_total. WHY: one figure for 400,000 pages says
    nothing a person can act on."""
    _save(client)
    run = _finished(client, _start(client)["started"]["job_id"])

    assert (run["folders_done"], run["folders_total"]) == (4, 4), run
    assert steps.reasons[0] == "Running step lines, read: 0 of 4 folders done"
    assert steps.reasons[2] == "Running step lines, read: 1 of 4 folders done", steps.reasons


def test_a_resumed_run_redoes_nothing(client, db, archive, steps, monkeypatch):
    """source.recipe.batch-checkpoint: every finished batch, and every step finished on the batch being run, is a
    checkpoint; an interrupted run carries on at the next unfinished step of the unfinished batch and runs no
    finished one again, even a step that cannot tell what it has done. WHY: a stop, quit or crash at folder 700 of
    800 must not read 700 folders again."""
    from fichero_server.recipes import runner

    monkeypatch.setattr(runner, "BATCH_PAGE_LIMIT", 1)
    _save(client)
    steps.interrupt = ("names", 1)  # the project closes as names starts on batch 2
    job_id = _start(client, folder_id=archive["B"])["started"]["job_id"]
    assert _wait(lambda: _status(client, job_id)["reason"].startswith("Interrupted")), _status(client, job_id)
    assert _status(client, job_id)["folders_done"] == 0
    b1, b2 = archive["b"]
    assert steps.ran == [("lines", [b1]), ("names", [b1]), ("lines", [b2])]

    jobs.resume(db)  # the project opens again
    run = _finished(client, job_id)

    assert run["state"] == "done", run
    assert steps.ran == [("lines", [b1]), ("names", [b1]), ("lines", [b2]), ("names", [b2])], (
        "a finished batch or a step finished on the interrupted batch ran again")
    assert (run["folders_done"], run["folders_total"]) == (1, 1)
