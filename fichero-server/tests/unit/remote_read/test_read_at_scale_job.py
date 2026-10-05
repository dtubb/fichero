"""Reading at scale on Hugging Face Jobs, as ONE job row of many shards (#5398 slice 2).

Hugging Face is replaced by a fake that runs Fichero's real runner on each shard (with a fake reader:
Kraken and vision models run only where the Job runs) and answers `list_jobs` like the service. The
package, the row, the shard states, the PAGE files and their landing as passes are all real.
"""
from __future__ import annotations

import io
import json
import shutil

import pytest
from PIL import Image

from fichero_server.execution import jobs
from fichero_server.models import DocType, Document, FileType, Segment, SegmentPass
from fichero_server.remote_read import job as read_job
from fichero_server.remote_read import runner
from fichero_server.remote_read.job import PagesMayNotLeave, ReadAtScaleRequest
from fichero_server.training.hf_jobs import FarStatus

HOST = "https://iiif.archive.example"
CANVAS = (4000, 6000)
FETCHED = (1000, 1500)  # what the IIIF server gives at the reader's size


def fake_reader(image):
    """One line a tenth of the way in, in the pixels of the image it was given."""
    w, h = image.size
    x0, x1, y0, y1 = w * 0.1, w * 0.5, h * 0.2, h * 0.25
    return [{"polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "baseline": [[x0, y1], [x1, y1]],
             "text": "En la ciudad"}]


def fake_iiif(url, timeout):
    data = io.BytesIO()
    Image.new("RGB", FETCHED, (220, 210, 200)).save(data, format="JPEG")
    return 200, {}, data.getvalue()


class FakeHub:
    """Answers like Hugging Face Jobs. A shard listed in `fail` fails on its first try only."""

    bucket = "historian/fichero-training"

    def __init__(self, fail=()):
        self.fail = set(fail)
        self.package = None
        self.jobs: dict[str, dict] = {}  # far id -> {shard, polls}
        self.cancelled: list[str] = []
        self.list_calls = 0

    def price_per_hour(self, flavor):
        return 0.4

    def send(self, local_dir, job_key):
        self.package = local_dir.parent / "sent"
        if self.package.exists():
            shutil.rmtree(self.package)
        shutil.copytree(local_dir, self.package)

    def submit(self, job_key, *, script, script_args, labels, **kw):
        assert script.name == "runner.py"
        far_id = f"far-{len(self.jobs)}"
        shard = labels["fichero-shard"]
        tries = sum(1 for j in self.jobs.values() if j["shard"] == shard)
        self.jobs[far_id] = {"shard": shard, "polls": 0, "fails": shard in self.fail and tries == 0}
        return far_id

    def statuses(self, job_key):
        self.list_calls += 1
        out = {}
        for far_id, j in self.jobs.items():
            j["polls"] += 1
            state = "running" if j["polls"] < 2 else ("failed" if j["fails"] else "done")
            out[far_id] = FarStatus(state=state, stage=state.upper(), message="CUDA error" if j["fails"] else None)
        return out

    def status(self, far_id):
        raise AssertionError("every Job is in the one listing")

    def last_lines(self, far_id, n=20):
        return ["RuntimeError: CUDA error"]

    def cancel(self, far_id):
        self.cancelled.append(far_id)

    def fetch_part(self, job_key, part, local_dir):
        shard = int(part.split("-")[1])
        runner.run_shard(self.package, shard, local_dir.parent, reader=fake_reader, get=fake_iiif)
        return local_dir


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(read_job, "_work_dir", lambda job_id: tmp_path / "work" / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # these tests run the job themselves
    monkeypatch.setattr(read_job, "resolve_step", lambda request, bucket: {
        "reader": "vlm", "card": request.card, "model": "/work/models/student", "prompt": "Read the line.",
        "lines_per_call": 1, "language": "es"})


@pytest.fixture
def archive(db, tmp_path):
    """Four photos here and three canvases served over IIIF."""
    folder = Document(name="EAP000", doc_type=DocType.folder)
    db.save(folder)
    (tmp_path / "photos").mkdir()
    for i in range(4):
        path = tmp_path / "photos" / f"p{i}.jpg"
        Image.new("RGB", (300, 400), (200 + i, 200, 190)).save(path)
        db.save(Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                         parent_id=folder.id, sequence=i))
    for i in range(4, 7):
        db.save(Document(name=f"f. {i}", doc_type=DocType.page, parent_id=folder.id, sequence=i,
                         metadata={"iiif_service": f"{HOST}/img/{i}", "width": CANVAS[0], "height": CANVAS[1]}))
    return folder


def _start(db, folder, **kw):
    request = ReadAtScaleRequest(scope_ids=[folder.id], reader="vlm", card="fichero-trained/sergio", shard_size=2,
                                 pages_may_leave=True, **kw)
    started = read_job.start(db, request, started_by="owner", target_factory=FakeHub)
    return started["job_id"], db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [started["job_id"]])[0]


def _passes(db, folder):
    pages = [d for d in db.query(Document, parent_id=folder.id)]
    return {d.id: [p for p in db.query(SegmentPass, document_id=d.id)] for d in pages}


def test_pages_do_not_leave_without_a_yes(db, archive):
    """WHY (`compute.consent.*`): reading on Hugging Face sends the pages there; nothing is queued
    until the person says yes."""
    with pytest.raises(PagesMayNotLeave):
        read_job.start(db, ReadAtScaleRequest(scope_ids=[archive.id], card="x"), started_by="owner",
                       target_factory=FakeHub)
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [read_job.KIND])[0] == 0


def test_one_row_many_shards_polled_in_one_call_and_every_page_lands(db, archive):
    """WHY (`compute.job.array-by-shard`, `.poll-is-gentle`, `.one-state-machine`,
    `compute.land.completed-means-landed`): 7 pages in 4 shards are ONE row; at most `max_in_flight`
    run at once; each round asks Hugging Face once, not once per shard; done means every page landed."""
    job_id, subject = _start(db, archive, max_in_flight=2)
    hub = FakeHub()
    counts = read_job.run(db, subject, target=hub, sleep=lambda s: None)

    assert counts == {"pending": 0, "submitted": 0, "landed": 4, "failed": 0}
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [read_job.KIND])[0] == 1
    assert hub.list_calls <= 6  # 4 shards, 2 at a time, 2 polls each: rounds, not shards x polls
    status = read_job.status(db, job_id)
    assert status["landing"]["landed"] == 7 and status["package"] == {"sources": 7, "shards": 4, "skipped": []}
    assert all(len(p) == 1 for p in _passes(db, archive).values())


def test_a_iiif_page_lands_on_its_canvas_not_on_the_fetched_image(db, archive):
    """WHY (EAP by reference): the reader saw a 1000x1500 image; the canvas is 4000x6000. The line the
    reader found 10% in must land 10% in on the canvas (400 px), not at 100 px of a 4000 px page."""
    _job_id, subject = _start(db, archive)
    read_job.run(db, subject, target=FakeHub(), sleep=lambda s: None)
    canvas = next(d for d in db.query(Document, parent_id=archive.id) if d.name == "f. 4")
    pass_row = db.query(SegmentPass, document_id=canvas.id)[0]
    lines = [s for s in db.query(Segment, pass_id=pass_row.id) if s.deleted_at is None and s.bbox_w < 1]
    assert lines, "the read line landed"
    line = min(lines, key=lambda s: s.bbox_w)
    assert line.bbox_x == pytest.approx(0.1, abs=0.002) and line.bbox_w == pytest.approx(0.4, abs=0.002)
    assert round(line.bbox_x * CANVAS[0]) == pytest.approx(400, abs=8)


def test_only_the_failed_shards_are_resent_and_landing_twice_changes_nothing(db, archive):
    """WHY (`compute.job.sparse-resubmit`, `compute.land.idempotent`): shard 1 fails (a GPU error, its
    last lines kept); re-sending sends shard 1 only; a page that landed is not landed again."""
    job_id, subject = _start(db, archive)
    hub = FakeHub(fail={"1"})
    first = read_job.run(db, subject, target=hub, sleep=lambda s: None)
    assert first["failed"] == 1 and first["landed"] == 3
    failed = read_job.status(db, job_id)["failed_shards"]
    assert failed["1"]["why"] == "Hugging Face: CUDA error" and failed["1"]["last_lines"]
    before = _passes(db, archive)

    db.execute("UPDATE jobs SET state = 'failed' WHERE id = ?", [job_id])  # as the scheduler ends it
    assert read_job.resend_failed(db, job_id) == 1
    assert db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0] == "waiting"
    sent = len(hub.jobs)
    second = read_job.run(db, subject, target=hub, sleep=lambda s: None)
    assert second == {"pending": 0, "submitted": 0, "landed": 4, "failed": 0}
    assert [j["shard"] for j in list(hub.jobs.values())[sent:]] == ["1"]
    after = _passes(db, archive)
    assert sum(len(v) for v in after.values()) == sum(len(v) for v in before.values()) + 2

    # The same shard's results landed again: counted, not landed.
    folder = read_job._work_dir(job_id) / "out" / "shard-00000"
    again = read_job.land_shard(db, job_id, folder, pass_name="again", actor="owner")
    assert again == {"landed": 0, "already": 2, "unread": 0, "set_aside": 0}
    assert _passes(db, archive) == after


def test_stopping_cancels_the_running_shards_on_hugging_face(db, archive):
    """WHY (`compute.job.cancel-reaches-the-far-side`): a stopped run does not keep paying for GPUs."""
    job_id, subject = _start(db, archive, max_in_flight=3)
    hub = FakeHub()

    def stop_after_first_round(_seconds):
        db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [job_id])
        assert read_job.request_cancel(db, job_id) == "running"

    with pytest.raises(jobs.JobCancelled):
        read_job.run(db, subject, target=hub, sleep=stop_after_first_round)
    assert sorted(hub.cancelled) == ["far-0", "far-1", "far-2"]
    assert json.loads(db.execute_fetchone("SELECT detail FROM jobs WHERE id = ?", [job_id])[0])["cancel"]


def test_an_engine_without_the_token_keeps_a_run_whose_shards_may_still_run(db, archive, monkeypatch):
    """WHY (#5449, `compute.job.another-engine-never-fails-what-it-cannot-reach`): an engine that opens
    the library without the Hugging Face token must not fail a run whose shards are running and billing
    there; it stays running, keeps every shard's Job id, and says why."""
    from fichero_server import llm
    from fichero_server.db.manager import db_manager
    from fichero_server.training import hf_jobs

    job_id, subject = _start(db, archive, max_in_flight=2)
    hub = FakeHub()

    def quit_after_first_round(_seconds):
        raise KeyboardInterrupt  # the engine that sent them goes away

    with pytest.raises(KeyboardInterrupt):
        read_job.run(db, subject, target=hub, sleep=quit_after_first_round)
    db.execute("UPDATE jobs SET state = 'running', attempts = 1 WHERE id = ?", [job_id])

    monkeypatch.setattr(llm, "get_api_key", lambda provider: None)  # never the Keychain
    real = hf_jobs.HfJobsTarget  # the real refusal, with an API client that is never reached
    monkeypatch.setattr(hf_jobs, "HfJobsTarget", lambda: real(api=object()))
    monkeypatch.setattr(db_manager, "open_database", lambda key: db)
    read_job.register_job_kinds()
    jobs.resume(db)
    db.execute("UPDATE jobs SET state = 'running', attempts = attempts + 1 WHERE id = ?", [job_id])
    row = db.execute_fetchone("SELECT id, kind, subject, model, created_at FROM jobs WHERE id = ?", [job_id])
    jobs._scheduler._run(jobs._scheduler.lanes["remote"], "key", db, row, None)

    state, reason = db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [job_id])
    assert state == "running" and "can't read the Hugging Face token" in reason and "2 shards" in reason
    detail = json.loads(db.execute_fetchone("SELECT detail FROM jobs WHERE id = ?", [job_id])[0])
    assert sorted(s["far_id"] for s in detail["shards"].values() if s["state"] == "submitted") == ["far-0", "far-1"]


def test_the_api_refuses_without_a_yes_and_answers_for_an_unknown_run(client):
    """WHY: the refusal must reach the app, CLI and MCP as a sentence with its own status, not a 500;
    an unknown run is a 404 on every route that names one."""
    r = client.post("/api/reading-at-scale", json={"scope_ids": ["x"], "card": "k"})
    assert r.status_code == 403 and "yes" in r.json()["detail"]
    assert client.get("/api/reading-at-scale/jobs/nope").status_code == 404
    assert client.post("/api/reading-at-scale/jobs/nope/resend-failed").status_code == 404


def test_a_reading_run_waits_on_the_remote_lane(db):
    """WHY: a run on Hugging Face waits on the network for hours; on the local ML lane it would hold
    every Kraken page and embed on this Mac for that long."""
    read_job.register_job_kinds()
    kind = jobs.KINDS[read_job.KIND]
    assert kind.lane == "remote" and kind.model is None
