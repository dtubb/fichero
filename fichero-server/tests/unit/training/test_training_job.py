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
from tests.unit.training.test_kraken_training_set import TEACHER, _page

NOTEBOOK_FLAVOR = "t4-small"


class FakeHub:
    """Answers like Hugging Face Jobs; records what Fichero asked."""

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
    assert "Qwen/Qwen2.5-VL-7B-Instruct" in submitted["script_args"]
    assert on_lane == [(mlx_landing.CONVERT_KIND, mlx_landing.CONVERT_MODEL)]
    status = training_job.status(db, started["job_id"])
    assert status["card"] == "vision-lora" and status["model_id"] == model_id == "fichero-trained/sergio-qwen7b"
    assert status["training_set"]["line_pairs"] > 0
    card = store.trained_card(model_id)
    assert card["base"] == "Qwen/Qwen2.5-VL-7B-Instruct" and card["base_licence"] == "Apache-2.0"
    assert card["teacher"] == TEACHER and card["not_for_release"] is True


def test_the_conversion_frees_kraken_first():
    """WHY: a 7B conversion beside a resident Kraken model can exhaust a 16 GB Mac; switching the local
    lane to it must free the heavy model already loaded."""
    from fichero_server.training.mlx_landing import CONVERT_MODEL

    assert jobs._heavy_switch("kraken:kraken-mccatmus", CONVERT_MODEL)
    assert jobs._heavy_switch("embedder", CONVERT_MODEL)
