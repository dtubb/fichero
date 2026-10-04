"""Training a Kraken reader on this Mac, gently (`compute.tune.on-this-mac`, `compute.tune.measured-on-16gb`, #5397).

Spec: docs/contributor_manual/specs/compute/jobs-and-fine-tuning.md and ui/activity-and-automatic-work.md
(`activity.throttle.power-heat-memory`). The maintainer wants long training on his own Mac that never
makes it unusable. The job runs on the local-model lane, holds while he uses the Mac, lets memory go
when it is tight, steps aside for work he is waiting for, and comes back without repeating an epoch.

Most tests drive the real job, lane and scheduler with a fake trainer that walks epochs and batches
through the same callbacks Kraken's trainer calls (fast and exact). The last runs Kraken itself, in
this process, on a tiny set: a stop after epoch 0 and a resume train epoch 1 only.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from fichero_server.execution import jobs, throttle
from fichero_server.training import job as remote_job
from fichero_server.training import local
from fichero_server.training.local import TrainKrakenHereRequest
from tests.unit.training.test_kraken_training_set import TEACHER, _page


class FakeKetos:
    """Walks epochs and batches like Kraken's trainer, through the job's own callbacks; stops between
    epoch 0 and 1 until the test lets it go, so the test can change the Mac's state there."""

    def __init__(self):
        self.epochs_run: list[int] = []
        self.calls = 0
        self.after_first_epoch = threading.Event()
        self.go = threading.Event()

    def __call__(self, argv, out: Path, gentle):
        self.calls += 1
        out.mkdir(parents=True, exist_ok=True)
        total = int(argv[argv.index("-N") + 1])
        start = 0
        if "--resume" in argv:
            start = json.loads(Path(argv[argv.index("--resume") + 1]).read_text())["epoch"] + 1
        for epoch in range(start, total):
            if epoch == 1:
                self.after_first_epoch.set()
                assert self.go.wait(30)
            for _ in range(3):
                gentle.on_batch()
            self.epochs_run.append(epoch)
            (out / f"checkpoint_{epoch:02d}-0.5000.ckpt").write_text("x")
            (out / "last.ckpt").write_text(json.dumps({"epoch": epoch}))
            gentle.on_epoch_end(epoch)
        (out / "best_0.5000.safetensors").write_bytes(b"weights")


@pytest.fixture
def mac(monkeypatch, tmp_path):
    """The Mac's signals, switchable; training's folders kept in tmp; checks without delay."""
    state = {"memory": False, "in_use": False}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    monkeypatch.setattr(remote_job, "_work_dir", lambda job_id: tmp_path / "work" / job_id)
    monkeypatch.setattr(throttle, "PROBES", [
        (lambda: throttle.MEMORY_REASON if state["memory"] else None, True),
        (lambda: "Waiting: you're using the Mac" if state["in_use"] else None, False),
    ])
    monkeypatch.setattr(jobs, "THROTTLE_LOOK_AGAIN_SECONDS", 0.05)
    # Setting up the pages queues their embeds, so the lane has the embedder loaded; the quiet spell
    # before a heavy-model switch is pinned in test_kraken_on_the_lane.py, not here.
    monkeypatch.setattr(jobs, "SWITCH_AFTER_QUIET_SECONDS", 0.0)
    monkeypatch.setattr(local, "CHECK_SECONDS", 0.0)
    monkeypatch.setattr(local, "HOLD_SECONDS", 0.02)
    return state


@pytest.fixture
def ketos(monkeypatch):
    fake = FakeKetos()
    monkeypatch.setattr(local, "TRAINER", fake)
    return fake


@pytest.fixture
def notebook(db, tmp_path, monkeypatch):
    from fichero_server.models import DocType, Document

    # The pages' own embeds run on the same lane first; a real embedder load would only slow these.
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: True)

    folder = Document(name="SM_NPQ_C09", doc_type=DocType.folder)
    db.save(folder)
    _page(db, tmp_path, "SM_NPQ_C09_001", folder)
    held = _page(db, tmp_path, "SM_NPQ_C09_002", folder)
    return folder, held


def _start(db, notebook):
    folder, held = notebook
    local.register_job_kinds()
    request = TrainKrakenHereRequest(scope_ids=[folder.id], teacher=TEACHER, held_out_ids=[held.id],
                                     name="sergio", epochs=2)
    return local.start(db, request, started_by="historian")["job_id"]


def _row(db, job_id):
    row = jobs.read_job(db, job_id)
    return row["state"], row["reason"]


def _wait_for(predicate, seconds=30.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_two_epochs_under_the_lane_wait_out_memory_pressure_and_resume_without_repeating_one(db, notebook, mac, ketos):
    """WHY (the spec's own test): under memory pressure a training run must let go of its memory,
    not hold it while the Mac swaps; and when it comes back it must carry on from its last
    finished epoch, never train one twice."""
    job_id = _start(db, notebook)
    assert ketos.after_first_epoch.wait(30)
    mac["memory"] = True
    ketos.go.set()
    assert _wait_for(lambda: _row(db, job_id)[0] == "waiting")
    assert ketos.epochs_run == [0]
    assert "memory is tight" in _row(db, job_id)[1]

    mac["memory"] = False
    assert _wait_for(lambda: _row(db, job_id)[0] == "done")
    assert ketos.epochs_run == [0, 1]
    assert ketos.calls == 2

    detail = json.loads(jobs.read_job(db, job_id)["detail"])
    assert detail["measured"]["epochs_done"] == 2
    assert detail["phase"] == "done" and detail["reader_id"].startswith("kraken-trained-")


def test_the_landed_card_carries_what_the_run_measured(db, notebook, mac, ketos):
    """WHY (`compute.tune.measured-on-16gb`): whether a reader is worth training here depends on what
    it cost this Mac; the figures come from the run, never typed by hand."""
    from fichero_server.llm.kraken_runtime import _marker_path

    ketos.go.set()
    job_id = _start(db, notebook)
    assert _wait_for(lambda: _row(db, job_id)[0] == "done")
    reader = json.loads(jobs.read_job(db, job_id)["detail"])["reader_id"]
    card = json.loads(_marker_path(reader).read_text())["trained"]
    assert card["target"] == "this-mac" and card["model_file"] == "sergio.safetensors"
    measured = card["measured"]
    assert measured["device"] == "cpu" and measured["threads"] >= 1 and measured["epochs_done"] == 2
    assert measured["peak_resident_mb"] > 0 and measured["seconds"] >= 0


def test_while_the_mac_is_in_use_training_holds_where_it_is_and_loses_nothing(db, notebook, mac, ketos):
    """WHY: someone typing is a reason to stop using the CPU, not to throw away the epoch in hand.
    Training holds at the batch it is on, says so, and carries on in the same run."""
    job_id = _start(db, notebook)
    assert ketos.after_first_epoch.wait(30)
    mac["in_use"] = True
    ketos.go.set()
    assert _wait_for(lambda: "you're using the Mac" in (_row(db, job_id)[1] or ""))
    assert _row(db, job_id)[0] == "running" and ketos.epochs_run == [0]
    mac["in_use"] = False
    assert _wait_for(lambda: _row(db, job_id)[0] == "done")
    assert ketos.epochs_run == [0, 1] and ketos.calls == 1


def test_training_steps_aside_for_a_page_someone_is_waiting_for(db, notebook, mac, ketos):
    """WHY: training holds the lane for hours; a Kraken page from a run the person just pressed
    must not wait for all of it. Training stops at the next batch, the page runs, training resumes."""
    job_id = _start(db, notebook)
    assert ketos.after_first_epoch.wait(30)
    page = jobs.submit(db, "find-lines", "asked-for", model="kraken:blla", fn=lambda: "lines")
    ketos.go.set()
    assert page.result(30) == "lines"
    assert _wait_for(lambda: _row(db, job_id)[0] == "done")
    assert ketos.epochs_run == [0, 1] and ketos.calls == 2


def test_cancel_stops_training_at_the_next_batch(db, client, notebook, mac, ketos):
    """WHY: a person stopping a run that holds the Mac must see it stop, not run its epochs out."""
    job_id = _start(db, notebook)
    assert ketos.after_first_epoch.wait(30)
    r = client.post(f"/api/activity/jobs/{job_id}/cancel")
    assert r.status_code == 200 and r.json()["state"] == "running"  # stops at its next batch
    ketos.go.set()
    assert _wait_for(lambda: _row(db, job_id)[0] == "cancelled")
    assert ketos.epochs_run == [0]


def test_the_api_starts_it_and_follows_it_with_what_it_measured(db, client, notebook, mac, ketos):
    """WHY: the app, the CLI and MCP start and follow it through the same audited action and the
    same status the Hugging Face card uses; the status carries the run's measurements."""
    folder, held = notebook
    ketos.go.set()
    r = client.post("/api/training/kraken/here", json={"scope_ids": [folder.id], "teacher": TEACHER,
                                                       "held_out_ids": [held.id], "name": "sergio", "epochs": 2})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    assert _wait_for(lambda: _row(db, job_id)[0] == "done")
    status = client.get(f"/api/training/jobs/{job_id}").json()
    assert status["phase"] == "done" and status["measured"]["epochs_done"] == 2
    bad = client.post("/api/training/kraken/here", json={"scope_ids": [folder.id], "teacher": TEACHER,
                                                         "base": "kraken-not-installed"})
    assert bad.status_code == 422


def test_kraken_7s_best_model_file_lands(tmp_path):
    """WHY: Kraken 7's `ketos train` names its best model `best_<score>.safetensors` in its output
    folder; landing looked only for `<name>_best.*` (Kraken 5 and 6) and would refuse every model
    Kraken 7 trains, here or on Hugging Face."""
    from fichero_server.training.landing import best_model_file

    (tmp_path / "checkpoint_01-0.9100.ckpt").write_text("x")
    (tmp_path / "best_0.9100.safetensors").write_bytes(b"weights")
    assert best_model_file(tmp_path, "sergio").name == "best_0.9100.safetensors"


def test_kraken_itself_stops_after_an_epoch_and_resumes_with_the_next(tmp_path):
    """WHY: the fake above trusts that Kraken's trainer calls our callbacks and resumes from
    `last.ckpt` at the next epoch. This runs Kraken 7 in this process on twelve tiny lines: a stop
    at the first batch of epoch 1, then a resume, trains epochs 0 and 1 once each."""
    pytest.importorskip("kraken")
    from PIL import Image, ImageDraw

    data = tmp_path / "lines"
    data.mkdir()
    for i, text in enumerate(["vecino de la ciudad", "de Santa Fe", "en el año", "del Señor", "mil seiscientos",
                              "y dos años", "ante mi", "parecio", "Juan Perez", "vendio", "la casa", "por cien"]):
        image = Image.new("L", (400, 48), 255)
        ImageDraw.Draw(image).text((8, 14), text, fill=0)
        image.save(data / f"line{i:02d}.png")
        (data / f"line{i:02d}.gt.txt").write_text(text)
    out = tmp_path / "out"
    lines = sorted(str(p) for p in data.glob("*.png"))
    argv = ["-d", "cpu", "--threads", "2", "--workers", "0", "-v", "train", "-f", "path", "-q", "fixed", "-N", "2",
            "-B", "4", "-o", str(out)]

    class Gentle:
        def __init__(self, stop_after):
            self.stop_after, self.epochs = stop_after, []

        def on_batch(self):
            if self.stop_after is not None and self.stop_after in self.epochs:
                raise local._Stop("defer", throttle.MEMORY_REASON)

        def on_epoch_end(self, epoch):
            self.epochs.append(epoch)

    first = Gentle(stop_after=0)
    with pytest.raises(local._Stop):
        local.train_in_process(argv + lines, out, first)
    assert first.epochs == [0] and (out / "last.ckpt").exists()

    second = Gentle(stop_after=None)
    local.train_in_process(argv + ["--resume", str(out / "last.ckpt")] + lines, out, second)
    assert second.epochs == [1]
    assert any(p.name.startswith("best_") for p in out.glob("*.safetensors"))
