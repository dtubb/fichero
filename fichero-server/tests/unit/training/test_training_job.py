"""Training a Kraken reader on Hugging Face Jobs, as one job row (#5398, `compute.job.one-state-machine`).

The place it runs is replaced by a fake that answers like Hugging Face; everything Fichero does on
this side (the set, the row, the phases, the landing) is real.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime as kr
from fichero_server.training import job as training_job
from fichero_server.training.hf_jobs import FarStatus
from fichero_server.training.job import PagesMayNotLeave, TrainKrakenRequest
from fichero_server.training.model_nodes import belongs_to, project_of
from tests.unit.training.test_kraken_training_set import TEACHER, _page

NOTEBOOK_FLAVOR = "t4-small"


class FakeHub:
    """Answers like Hugging Face Jobs; records what Fichero asked."""

    bucket = "historian/fichero-training"

    def __init__(self, stages=("waiting", "running", "done"), message=None):
        self.stages = list(stages)
        self.message = message
        self.sent, self.submitted, self.cancelled, self.fetched = [], [], [], []

    def price_per_hour(self, flavor):
        return {NOTEBOOK_FLAVOR: 0.4, "l4x1": 0.8}.get(flavor)

    def cheapest(self, flavors):
        return "l4x1"

    def send(self, local_dir, job_key):
        self.sent.append(sorted(p.name for p in local_dir.rglob("*") if p.is_file()))

    def submit(self, job_key, **kw):
        self.submitted.append(kw)
        return "hf-job-1"

    def status(self, far_id):
        state = self.stages.pop(0) if len(self.stages) > 1 else self.stages[0]
        return FarStatus(state=state, stage=state.upper(), message=self.message)

    def last_lines(self, far_id, n=20):
        return ["epoch 9 val_accuracy 0.93", "CUDA out of memory"] if self.message else ["done"]

    def cancel(self, far_id):
        self.cancelled.append(far_id)

    def fetch(self, job_key, local_dir):
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "sergio_best.safetensors").write_bytes(b"trained weights")
        for part in ("adapter", "merged"):  # what the vision-model trainer writes
            (local_dir / part).mkdir(exist_ok=True)
            (local_dir / part / "weights.safetensors").write_bytes(part.encode())
        self.fetched.append(job_key)
        return local_dir


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    monkeypatch.setattr(training_job, "_work_dir", lambda job_id: tmp_path / "work" / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # these tests run the job themselves


@pytest.fixture
def notebook(db, tmp_path):
    from fichero_server.models import DocType, Document

    folder = Document(name="SM_NPQ_C09", doc_type=DocType.folder)
    db.save(folder)
    _page(db, tmp_path, "SM_NPQ_C09_001", folder)
    test_page = _page(db, tmp_path, "SM_NPQ_C09_002", folder)
    return SimpleNamespace(folder=folder, test_page=test_page)


def _request(notebook, **over):
    return TrainKrakenRequest(**{"scope_ids": [notebook.folder.id], "teacher": TEACHER,
                                 "held_out_ids": [notebook.test_page.id], "name": "sergio",
                                 "flavor": NOTEBOOK_FLAVOR, "pages_may_leave": True, **over})


def _start(db, notebook, hub, **over):
    return training_job.start(db, _request(notebook, **over), started_by="historian", target_factory=lambda: hub)


def _subject(db, job_id):
    return db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [job_id])[0]


def test_a_training_job_goes_out_runs_and_comes_home_as_a_reader(db, notebook):
    """WHY: the whole loop, as one row a person can follow: the set leaves (held-out page kept home),
    the Job runs on the chosen hardware, the reader lands, and the row says so at each step."""
    hub = FakeHub()
    started = _start(db, notebook, hub)
    reader = training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)

    assert started["price_per_hour_usd"] == 0.4
    (sent,) = hub.sent
    assert "SM_NPQ_C09_001.xml" in sent and not any("SM_NPQ_C09_002" in name for name in sent)
    assert hub.submitted[0]["flavor"] == NOTEBOOK_FLAVOR and hub.submitted[0]["timeout"] == "4h"
    status = training_job.status(db, started["job_id"])
    assert [h["phase"] for h in status["history"]] == [
        "waiting", "preparing", "sending", "submitted", "queued", "running", "fetching", "landing", "done"]
    assert status["far_id"] == "hf-job-1" and status["reader_id"] == reader
    assert status["yes"]["by"] == "historian"
    card = kr.trained_reader_card(reader)
    assert card["teacher"] == TEACHER and card["not_for_release"] is True and card["far_id"] == "hf-job-1"
    assert belongs_to(card, project_of(db)), "the card names the project it was trained in (#5483)"


def test_a_job_resumed_after_a_restart_watches_the_same_job_and_sends_nothing_again(db, notebook):
    """WHY: the app can quit while a Job trains (`compute.job.survives-the-app-quitting`). Sending the
    set and starting a second Job on resume would pay twice for one model."""
    hub = FakeHub()
    started = _start(db, notebook, hub)
    state, detail = training_job._row(db, started["job_id"])
    detail["far_id"] = "hf-job-1"
    db.execute("UPDATE jobs SET detail = ? WHERE id = ?", [json.dumps(detail | {"training_set": {
        "pages": 1, "lines": 44, "held_out": []}}), started["job_id"]])

    training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)
    assert hub.sent == [] and hub.submitted == [] and hub.fetched == [started["job_id"]]


def test_a_failed_job_says_why_with_the_last_lines(db, notebook):
    """WHY (`compute.job.fails-with-a-reason`): "failed" alone sends a person to read logs on another
    site; the service's reason and the Job's last lines belong on the row."""
    hub = FakeHub(stages=("running", "failed"), message="Job exited with code 1")
    started = _start(db, notebook, hub)
    with pytest.raises(RuntimeError, match="exited with code 1.*out of memory"):
        training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)
    assert "CUDA out of memory" in training_job.status(db, started["job_id"])["last_lines"]


def test_stopping_a_running_job_cancels_it_on_hugging_face(db, notebook):
    """WHY (`compute.job.cancel-everywhere`): a stopped job that kept running there would keep
    costing; the cancel reaches the Job and the row ends cancelled, not failed."""
    hub = FakeHub(stages=("running",))
    started = _start(db, notebook, hub)
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [started["job_id"]])

    def cancel_while_running(_seconds):
        assert training_job.request_cancel(db, started["job_id"]) == "running"

    with pytest.raises(jobs.JobCancelled):
        training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=cancel_while_running)
    assert hub.cancelled == ["hf-job-1"]


def test_a_waiting_job_is_stopped_at_once(db, notebook):
    started = _start(db, notebook, FakeHub())
    assert training_job.request_cancel(db, started["job_id"]) == "cancelled"
    assert training_job.status(db, started["job_id"])["state"] == "cancelled"


def test_nothing_leaves_without_a_yes(db, notebook):
    """WHY (`compute.leave.one-gate`): an archive's pages go to another company's computers only after
    a person said yes for them; without it nothing is queued at all."""
    with pytest.raises(PagesMayNotLeave):
        _start(db, notebook, FakeHub(), pages_may_leave=False)
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [training_job.KIND])[0] == 0


def test_a_base_reader_that_is_not_installed_is_refused_before_queueing(db, notebook):
    """WHY: discovering on Hugging Face, after the set was sent, that the base reader was never on this
    Mac wastes a send and a Job."""
    with pytest.raises(RuntimeError, match="not downloaded"):
        _start(db, notebook, FakeHub(), base="kraken-mccatmus")
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [training_job.KIND])[0] == 0


def test_a_training_job_never_holds_the_local_model_lane():
    """WHY: a Job on Hugging Face runs for hours while this Mac waits on the network; holding the local
    ML lane would stop every Kraken page and every embed for that long."""
    training_job.register_job_kinds()
    kind = jobs.KINDS[training_job.KIND]
    assert kind.lane == "remote" and kind.model is None and jobs.LANES["remote"] >= 1


def test_the_api_refuses_without_a_yes_and_answers_for_an_unknown_job(client):
    """WHY: the refusal must reach the app, CLI and MCP as a sentence with its own status, not a 500."""
    r = client.post("/api/training/kraken", json={"scope_ids": ["x"], "teacher": TEACHER})
    assert r.status_code == 403 and "yes" in r.json()["detail"]
    assert client.get("/api/training/jobs/nope").status_code == 404


def test_the_scheduler_ends_a_stopped_job_cancelled_not_failed(db, monkeypatch):
    """WHY: Activity shows failures as problems to fix; a job a person stopped is not one. The
    scheduler must record `JobCancelled` as cancelled, with its words."""
    from fichero_server.db.manager import db_manager

    def stopped(_db, _subject):
        raise jobs.JobCancelled("Stopped by you; the Job on Hugging Face was cancelled")

    monkeypatch.setitem(jobs.KINDS, "test-remote-stop", jobs.Kind(run=stopped, model=None, lane="remote"))
    job_id = jobs.enqueue_remote(db, "test-remote-stop", "s1", target="huggingface-jobs", detail="{}",
                                 reason="Waiting", started_by="historian")
    row = db.execute_fetchone("SELECT id, kind, subject, model, created_at FROM jobs WHERE id = ?", [job_id])
    monkeypatch.setattr(db_manager, "open_database", lambda key: db)
    jobs._scheduler._run(jobs._scheduler.lanes["remote"], "key", db, row, None)
    assert db.execute_fetchone("SELECT state, reason, target FROM jobs WHERE id = ?", [job_id]) == (
        "cancelled", "Stopped by you; the Job on Hugging Face was cancelled", "huggingface-jobs")


# --- the vision-model card -----------------------------------------------------------------------


@pytest.fixture
def full_size_notebook(db, tmp_path):
    from fichero_server.models import DocType, Document
    from tests.unit.training.test_line_pairs import PAGE_SIZE

    folder = Document(name="SM_NPQ_C10", doc_type=DocType.folder)
    db.save(folder)
    _page(db, tmp_path, "SM_NPQ_C10_001", folder, size=PAGE_SIZE)
    test_page = _page(db, tmp_path, "SM_NPQ_C10_002", folder, size=PAGE_SIZE)
    return SimpleNamespace(folder=folder, test_page=test_page)


def test_the_vision_card_trains_on_line_pairs_and_lands_through_the_local_lane(db, full_size_notebook, tmp_path,
                                                                             monkeypatch):
    """WHY: the vision student learns from the same set as the Kraken student (line pictures and the
    teacher's answers), on the cheapest GPU that fits, and its conversion for MLX is heavy LOCAL work:
    it must go to the local ML lane, never run beside a Kraken page from the remote lane's thread."""
    from fichero_server.llm import mlx_model_store as store_module
    from fichero_server.llm.mlx_model_store import MLXModelStore
    from fichero_server.training import hf_jobs, mlx_landing
    from fichero_server.training.job import TrainVisionLoraRequest

    store = MLXModelStore(root=tmp_path / "mlx")
    monkeypatch.setattr(store_module, "get_mlx_model_store", lambda: store)

    def convert(merged, dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "model.safetensors").write_bytes(b"4-bit")

    monkeypatch.setattr(mlx_landing, "convert_for_mlx", convert)
    on_lane = []

    def run_on_lane_blocking(library_path, kind, subject, *, model, fn):
        on_lane.append((kind, model))
        return fn()

    monkeypatch.setattr(jobs, "run_on_lane_blocking", run_on_lane_blocking)
    hub = FakeHub()
    request = TrainVisionLoraRequest(scope_ids=[full_size_notebook.folder.id], teacher=TEACHER,
                                     held_out_ids=[full_size_notebook.test_page.id], name="sergio-qwen7b",
                                     language="Spanish", pages_may_leave=True)
    started = training_job.start(db, request, started_by="historian", target_factory=lambda: hub)
    model_id = training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)

    assert started["flavor"] == "l4x1" and started["price_per_hour_usd"] == 0.8
    (sent,) = hub.sent
    assert "pairs.jsonl" in sent and any(name.startswith("SM_NPQ_C10_001_") for name in sent)
    assert not any("SM_NPQ_C10_002" in name for name in sent), "held-out pages never leave"
    submitted = hub.submitted[0]
    assert submitted["script"] == hf_jobs.LORA_TRAINER and submitted["timeout"] == "8h"
    assert "Qwen/Qwen3-VL-8B-Instruct" in submitted["script_args"], "Qwen3-VL 8B is the default base"
    assert on_lane == [(mlx_landing.CONVERT_KIND, mlx_landing.CONVERT_MODEL)]
    status = training_job.status(db, started["job_id"])
    assert status["card"] == "vision-lora" and status["model_id"] == model_id == "fichero-trained/sergio-qwen7b"
    assert status["training_set"]["line_pairs"] > 0
    card = store.trained_card(model_id)
    assert card["base"] == "Qwen/Qwen3-VL-8B-Instruct" and card["base_licence"] == "Apache-2.0"
    assert card["teacher"] == TEACHER and card["not_for_release"] is True
    assert belongs_to(card, project_of(db)), "the student's card names the project it was trained in (#5483)"
    hf = card["builds"]["hf"]
    assert (hf["bucket"], hf["merged"], hf["adapter"]) == (
        "historian/fichero-training", f"{started['job_id']}/out/merged", f"{started['job_id']}/out/adapter")
    assert card["builds"]["mlx"]["model_id"] == model_id


def test_the_conversion_frees_kraken_first():
    """WHY: a 7B conversion beside a resident Kraken model can exhaust a 16 GB Mac; switching the local
    lane to it must free the heavy model already loaded."""
    from fichero_server.training.mlx_landing import CONVERT_MODEL

    assert jobs._heavy_switch("kraken:kraken-mccatmus", CONVERT_MODEL)
    assert jobs._heavy_switch("embedder", CONVERT_MODEL)


# --- another engine adopts a job it cannot reach (#5449) -----------------------------------------
# `compute.job.another-engine-never-fails-what-it-cannot-reach`. The real `HfJobsTarget` is used with
# a fake API client (no network) and a stubbed provider key (never the Keychain).


class FakeHfApi:
    """The `HfApi` calls a watched Job makes; records cancels."""

    def __init__(self):
        self.cancelled: list[str] = []

    def inspect_job(self, job_id, token):
        return SimpleNamespace(status=SimpleNamespace(stage="RUNNING", message=None))

    def cancel_job(self, job_id, token):
        self.cancelled.append(job_id)


class RefusedToken(RuntimeError):
    """What `huggingface_hub` raises for a token the service refuses (an HTTP error with a response)."""

    response = SimpleNamespace(status_code=401)


@pytest.fixture
def engine(monkeypatch):
    """This engine: whether it can read a Hugging Face token, and the Hub it would reach."""
    from fichero_server import llm
    from fichero_server.db.manager import db_manager
    from fichero_server.training import hf_jobs

    real = hf_jobs.HfJobsTarget
    state = SimpleNamespace(api=FakeHfApi(), token=None, db=None)
    monkeypatch.setattr(llm, "get_api_key", lambda provider: state.token if provider == "huggingface" else None)
    monkeypatch.setattr(hf_jobs, "HfJobsTarget", lambda: real(api=state.api))
    monkeypatch.setattr(db_manager, "open_database", lambda key: state.db)
    training_job.register_job_kinds()
    return state


def _left_running_by_another_engine(db, notebook):
    """A job another engine sent: its Job's id is stored and the row was running when that engine quit."""
    started = _start(db, notebook, FakeHub())
    job_id = started["job_id"]
    _state, detail = training_job._row(db, job_id)
    detail.update(far_id="hf-job-1", phase="running", training_set={"pages": 1, "lines": 44, "held_out": []})
    db.execute("UPDATE jobs SET state = 'running', attempts = 1, detail = ? WHERE id = ?",
               [json.dumps(detail), job_id])
    return job_id


def _adopt(db, job_id):
    """What an engine does on opening the library: resume, then the scheduler runs the job."""
    jobs.resume(db)
    # The scheduler's claim, as `_Scheduler._claim` writes it.
    db.execute("UPDATE jobs SET state = 'running', attempts = attempts + 1 WHERE id = ? AND state = 'waiting'",
               [job_id])
    row = db.execute_fetchone("SELECT id, kind, subject, model, created_at FROM jobs WHERE id = ?", [job_id])
    jobs._scheduler._run(jobs._scheduler.lanes["remote"], "key", db, row, None)


def _refuse(*_args, **_kw):
    raise RefusedToken("Invalid user token.")


@pytest.mark.parametrize("why", ["no token", "token refused"])
def test_an_engine_that_cannot_reach_an_adopted_job_keeps_it_tracked_not_failed(db, notebook, engine, why):
    """WHY (#5449): a sandboxed engine without the token failed two rows while their Jobs kept running
    and billing on Hugging Face, and a failed row could not be cancelled. The row must stay running,
    keep its Job's id, say why in words, and not spend an attempt (three opens would set it aside)."""
    engine.db = db
    if why == "token refused":
        engine.token = "hf_test_not_a_real_token"
        engine.api.inspect_job = _refuse
    job_id = _left_running_by_another_engine(db, notebook)

    _adopt(db, job_id)

    state, reason, attempts = db.execute_fetchone("SELECT state, reason, attempts FROM jobs WHERE id = ?", [job_id])
    assert state == "running" and reason.startswith("Needs attention: this engine can't read the Hugging Face token")
    assert attempts == 1  # the adoption did not count against it
    status = training_job.status(db, job_id)
    assert status["far_id"] == "hf-job-1" and status["out_of_reach"]
    # Opened again and again on engines without the token, it is never set aside as failed.
    db.execute("UPDATE jobs SET attempts = ? WHERE id = ?", [jobs.MAX_ATTEMPTS + 2, job_id])
    jobs.resume(db)
    assert db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0] == "waiting"


def test_activity_shows_the_adopted_job_with_why_it_cannot_be_followed(db, notebook, engine):
    """WHY: the person must see, in Activity, that paid work may still run elsewhere and what to do,
    not a silent "running" nor a "failed" that hides a live Job."""
    engine.db = db
    job_id = _left_running_by_another_engine(db, notebook)
    _adopt(db, job_id)

    (row,) = [r for r in jobs.snapshot(db) if r["id"] == job_id]
    assert row["state"] == "running"
    assert "can't read the Hugging Face token" in row["reason"] and "hf-job-1" in row["reason"]


def test_cancel_from_an_engine_with_the_token_reaches_hugging_face(db, notebook, engine):
    """WHY: nothing on this engine follows an out-of-reach row, so a cancel that only set a flag would
    leave the Job billing. An engine with the token cancels it on Hugging Face at once."""
    engine.db = db
    job_id = _left_running_by_another_engine(db, notebook)
    _adopt(db, job_id)  # no token: out of reach

    engine.token = "hf_test_not_a_real_token"
    assert jobs.cancel_job(db, job_id) == "cancelled"
    assert engine.api.cancelled == ["hf-job-1"]
    assert db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [job_id]) == (
        "cancelled", training_job.CANCELLED_THERE)


def test_a_row_failed_while_its_job_still_ran_can_still_be_cancelled_there(db, notebook, engine):
    """WHY (#5449): the rows already failed by the bug answered `failed` to a cancel and cancelled
    nothing; the Job was stopped by hand on Hugging Face after 44 minutes."""
    engine.db = db
    engine.token = "hf_test_not_a_real_token"
    job_id = _left_running_by_another_engine(db, notebook)
    db.execute("UPDATE jobs SET state = 'failed', reason = 'Invalid user token.' WHERE id = ?", [job_id])

    assert jobs.cancel_job(db, job_id) == "cancelled"
    assert engine.api.cancelled == ["hf-job-1"]


def test_a_stop_pressed_where_the_token_is_missing_is_carried_out_where_it_is(db, notebook, engine):
    """WHY: a person may press Stop on the engine that cannot reach the Job; the stop must not be lost,
    and must not pretend to have happened."""
    engine.db = db
    job_id = _left_running_by_another_engine(db, notebook)
    _adopt(db, job_id)

    assert jobs.cancel_job(db, job_id) == "running"
    assert engine.api.cancelled == []
    assert "Stopping" in db.execute_fetchone("SELECT reason FROM jobs WHERE id = ?", [job_id])[0]

    engine.token = "hf_test_not_a_real_token"  # the library opens where the token is
    _adopt(db, job_id)
    assert engine.api.cancelled == ["hf-job-1"]
    assert db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0] == "cancelled"


def test_a_job_that_failed_on_hugging_face_still_fails(db, notebook, engine):
    """WHY: only an unreachable Job is kept running; a Job the service itself reports failed must
    still end the row failed, with its reason (`compute.job.fails-with-a-reason`)."""
    engine.db = db
    engine.token = "hf_test_not_a_real_token"
    engine.api.inspect_job = lambda job_id, token: SimpleNamespace(
        status=SimpleNamespace(stage="ERROR", message="Job exited with code 1"))
    engine.api.fetch_job_logs = lambda job_id, tail, token: ["CUDA out of memory"]
    job_id = _left_running_by_another_engine(db, notebook)
    _adopt(db, job_id)
    state, reason = db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [job_id])
    assert state == "failed" and "exited with code 1" in reason
