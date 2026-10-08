"""The list and the tree give a row the same state and reason; a page's reason is words, its server's output is
in the job's log (#5606, `activity.list-and-tree-agree`, `compute.memory.server-death-said`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md and
docs/contributor_manual/specs/compute/jobs-and-fine-tuning.md. Seen live after an engine restart: a recipe
run's tree said "waiting — Interrupted; carries on" while `GET /api/activity/jobs` listed the same row as
running with no reason; and a page failed with "The local model server stopped while reading: 2026-10-07
23:47:43,151 - INFO - Decode progress: …", the MLX server's own log as its reason, though the engine had
stopped the server as it shut down.

Through the routes with the real lanes and the real job rows: the recipe run is a real `run-a-recipe` row,
interrupted by the engine's own `resume` and run again by the recipes lane (only its work is a stub); a
model call holds a real slot on the model lane under a real run, and its server is a stand-in process the
engine's server registry holds.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from fichero_server import llm
from fichero_server.api.routes.ai import local_inference as servers
from fichero_server.execution import jobs
from fichero_server.recipes import runner

HOLD_KIND = "hold-the-recipe-lane"
LOG_TAIL = ("2026-10-07 23:47:43,151 - INFO - Decode progress: request=7 generated_tokens=1110 | "
            "[METAL] Command buffer execution failed: Insufficient Memory")


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _listed(client, job_id):
    rows = [j for j in client.get("/api/activity/jobs").json()["jobs"] if j["id"] == job_id]
    assert len(rows) == 1, rows
    return rows[0]["state"], rows[0]["reason"]


def _tree(client, job_id):
    node = client.get(f"/api/activity/jobs/{job_id}").json()
    return node["state"], node["reason"]


@pytest.fixture
def recipe_kind(monkeypatch):
    """The recipe kind on the real recipes lane, its work a stub that holds until released; and another kind on
    the same lane that holds its one slot until released, so the run waits for its lane for as long as the
    test reads it (#5610: read while the lane was free to pick it, the list and the tree were asked at two
    moments, either side of the pick)."""
    release, lane_free = threading.Event(), threading.Event()
    ran: list[str] = []

    def run(db, subject):
        job_id = jobs.job_id_for(db, runner.KIND, subject)
        detail = json.loads(jobs.read_job(db, job_id)["detail"])
        jobs.save_detail(db, job_id, json.dumps(detail), reason="Running step read")
        ran.append(subject)
        release.wait(30)

    def hold(db, subject):
        ran.append(subject)
        lane_free.wait(30)

    monkeypatch.setitem(jobs.KINDS, runner.KIND, jobs.Kind(run=run, model=None, lane="recipes",
                                                          name="Run the recipe"))
    monkeypatch.setitem(jobs.KINDS, HOLD_KIND, jobs.Kind(run=hold, model=None, lane="recipes",
                                                        name="Hold the recipe lane"))
    yield SimpleNamespace(release=release, lane_free=lane_free, ran=ran)
    lane_free.set()  # a failed assertion leaves no lane thread waiting out its 30 s
    release.set()


def test_an_interrupted_then_resumed_recipe_run_reads_the_same_in_the_list_and_the_tree(db, client, recipe_kind):
    """WHY (#5606): after the restart the run's tree said "waiting — Interrupted; carries on" and the list
    said "running", reason null. Each surface read the row its own way; now both read it from one place."""
    jobs.set_paused(True)  # nothing runs while the run is set up as the engine left it
    holder = jobs.enqueue(db, HOLD_KIND, "the lane", watched=True)  # first on the lane once it runs
    detail = {"runs": [{"steps": ["read"], "card": "workflow"}],
              "steps": [{"steps": ["read"], "card": "workflow", "state": "running", "child_id": None}]}
    job_id = jobs.enqueue(db, runner.KIND, "project", started_by="owner", detail=json.dumps(detail))
    db.execute("UPDATE jobs SET state = 'running', reason = 'Running step read' WHERE id = ?", [job_id])

    jobs.resume(db)  # the engine starts again: the run was interrupted
    assert db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [job_id]) == (
        "waiting", "Interrupted; carries on")
    listed, tree = _listed(client, job_id), _tree(client, job_id)
    assert listed == tree == ("waiting", "Paused by you")

    jobs.set_paused(False)  # the lane runs again; its one slot is held, so the run waits for it
    assert _wait_for(lambda: recipe_kind.ran == ["the lane"])
    listed, tree = _listed(client, job_id), _tree(client, job_id)
    assert listed == tree == ("waiting", "Waiting for the recipe lane: Hold the recipe lane is running")

    recipe_kind.lane_free.set()  # the lane is free: the run carries on
    assert _wait_for(lambda: recipe_kind.ran == ["the lane", "project"])
    assert _wait_for(lambda: jobs.read_job(db, holder)["state"] == "done")
    listed, tree = _listed(client, job_id), _tree(client, job_id)
    assert listed == tree == ("running", "Running step read")
    recipe_kind.release.set()
    assert _wait_for(lambda: jobs.read_job(db, job_id)["state"] == "done")


class _Server:
    """A model server the engine started: running until it is stopped or dies."""

    def __init__(self):
        self._process = object()
        self.running = True
        self.last_error = None

    def is_running(self):
        return self.running

    def output_tail(self, lines=3):
        return LOG_TAIL


@pytest.fixture
def server(monkeypatch):
    process = _Server()

    async def stop():
        process.running = False

    manager = SimpleNamespace(profile=SimpleNamespace(managed_by_app=True), process=process, stop=stop)
    monkeypatch.setattr(servers, "_MANAGERS", {"local-omlx": manager})
    monkeypatch.setattr(llm, "_SERVER_EXIT_GRACE_SECONDS", 0.0)
    return process


def _read_a_page_when(db, test_package, before) -> str:
    """A run whose page's model call holds the model lane; `before` happens to its server mid-read. The
    page's call row id."""
    jobs.record_child_run(db, "run-read", parent_step=None, name="Paleographer Review")
    jobs.record_step(db.path, "run-read", "read", status="running", name="Read the page")
    row: dict[str, str] = {}

    async def go():
        with pytest.raises(Exception) as raised:
            async with jobs.lane_slot(test_package, "ask-a-model", "SM_NPQ_C01_004.jpg",
                                      model="omlx:mlx-community/reader", run_id="run-read"):
                row["id"] = jobs._call_row.get()[1]
                jobs.set_parent(db, row["id"], "run-read:read")
                await before()
                exc = httpx.RemoteProtocolError("Server disconnected without sending a response.")
                raise await llm._local_server_stopped(exc) or exc
        return raised.value

    error = asyncio.run(go())
    assert _wait_for(lambda: jobs.read_job(db, row["id"])["state"] == "failed")
    assert jobs.read_job(db, row["id"])["reason"] == str(error)
    return row["id"]


def _node(tree, job_id):
    if tree["id"] == job_id:
        return tree
    for child in tree["children"]:
        found = _node(child, job_id)
        if found is not None:
            return found
    return None


def test_a_model_server_death_is_said_in_words_and_its_output_is_in_the_job_log(db, client, test_package, server):
    """WHY (#5606): the page's reason was the MLX server's own log line. The reason says what happened; the
    server's last output is in the job's log, where a person reading why looks next."""
    async def dies():
        server.running = False

    call = _read_a_page_when(db, test_package, dies)
    page = _node(client.get("/api/activity/jobs/run-read").json(), call)
    assert (page["state"], page["reason"]) == ("failed", llm.SERVER_STOPPED_REASON)
    assert "Decode progress" not in page["reason"] and "INFO" not in page["reason"]
    log = client.get("/api/activity/jobs/run-read/log").json()["lines"]
    kept = [line for line in log if line["job_id"] == call and "Decode progress" in line["message"]]
    assert kept and "Insufficient Memory" in kept[0]["message"] and kept[0]["timestamp"]


def test_a_server_stopped_as_the_engine_shuts_down_says_the_engine_was_shutting_down(
        db, client, test_package, server):
    """WHY (#5606): the server was stopped by the engine's own shutdown, and the page said the server had
    stopped, with its log. It says the engine was shutting down."""
    call = _read_a_page_when(db, test_package, servers.shutdown_managed_local_inference_services)
    page = _node(client.get("/api/activity/jobs/run-read").json(), call)
    assert (page["state"], page["reason"]) == ("failed", "Stopped: the engine was shutting down")
    log = client.get("/api/activity/jobs/run-read/log").json()["lines"]
    assert any(line["job_id"] == call and "Decode progress" in line["message"] for line in log)
