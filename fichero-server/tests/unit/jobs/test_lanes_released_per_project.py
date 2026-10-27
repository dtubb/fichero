"""The lanes are shared, the holds are not (#6213): a row a dead process left running holds no lane, a job stuck in a lane
thread does not keep its slot from another project, and a release refuses only a run alive in this engine
(`recipes-run.restart.releases-lanes`, `recipes-run.isolation.one-project-never-blocks-another`,
`recipes-run.isolation.release-never-refused-by-a-phantom`)."""
from __future__ import annotations

import time

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs

THUMB = "thumbnail-6213"


@pytest.fixture
def thumbs(monkeypatch):
    monkeypatch.setitem(jobs.KINDS, THUMB, jobs.Kind(run=lambda db, subject: None, model=None, lane="images",
                                                     name="Make thumbnails", first=True))
    monkeypatch.setattr("fichero_server.db.storage.has_thumbnail", lambda doc_id, package_path=None: False)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)


@pytest.fixture
def other(tmp_path, db):
    """A second project open on the same engine."""
    package = tmp_path / "other.fichero"
    for sub in ("", "lance", "storage", "files"):
        (package / sub).mkdir(exist_ok=True)
    other_db = db_manager.get_database(package)
    jobs._ensure(other_db)
    return other_db


@pytest.fixture
def images(monkeypatch):
    lane = jobs._scheduler.lanes["images"]
    monkeypatch.setattr(lane, "running", {})
    monkeypatch.setattr(lane, "started", {})
    return lane


def _left_running(db, subject, seconds_ago=600) -> str:
    job_id = jobs._insert(db, THUMB, subject, None, "automatic")
    db.execute(f"UPDATE jobs SET state = 'running', attempts = 1, started_at = now() - INTERVAL {seconds_ago} SECOND "
               "WHERE id = ?", [job_id])
    return job_id


def test_a_row_a_dead_process_left_running_holds_no_lane_for_another_project(db, other, thumbs, images, monkeypatch):
    jobs._ensure(db)
    _left_running(db, "a-page-1")
    _left_running(db, "a-page-2")
    fresh = jobs._insert(other, THUMB, "b-page-1", None, "automatic")
    monkeypatch.setattr(images, "libraries", {jobs._key(db), jobs._key(other)})

    picked = jobs._scheduler._next(images)

    assert picked is not None and picked[2][0] == fresh
    assert images.may_start(THUMB, None)


def test_jobs_stuck_in_the_lane_past_the_deadline_give_back_their_slots(db, other, thumbs, images):
    jobs._ensure(db)
    stuck = [_left_running(db, f"a-page-{n}") for n in range(2)]
    for job_id in stuck:  # two lane threads of this engine, each stuck on a page of project A
        images.running[job_id] = None
        images.started[job_id] = time.monotonic() - jobs.STUCK_IMAGE_JOB_SECONDS - 1
    fresh = jobs._insert(other, THUMB, "b-page-1", None, "automatic")

    assert images.may_start(THUMB, None)  # project B's thumbnail starts
    assert images.threads_wanted == images.slots + 2  # on a thread of its own: the stuck ones are still blocked
    reason = jobs.waiting_reason(other, fresh, THUMB)
    assert "another project" not in reason and not reason.startswith("Waiting for the thumbnail lane:")


def test_a_job_running_within_the_deadline_still_holds_its_slot(db, thumbs, images):
    jobs._ensure(db)
    for n in range(2):
        job_id = _left_running(db, f"a-page-{n}", seconds_ago=1)
        images.running[job_id] = None
        images.started[job_id] = time.monotonic()

    assert not images.may_start(THUMB, None)
    assert images.threads_wanted == images.slots


def test_a_release_is_not_refused_by_a_run_row_no_live_thread_runs(db, monkeypatch):
    jobs._ensure(db)
    jobs._insert(db, "workflow", "run-phantom", None, "automatic")
    db.execute("UPDATE jobs SET state = 'running', detail = '{\"name\": \"Detect Segments (Kraken)\"}' WHERE kind = 'workflow'")
    monkeypatch.setattr("fichero_server.execution.runner._running_workflows", {})

    runs, _running, _waiting = jobs.live_work(db)

    assert runs == []


def test_a_release_refused_by_a_live_run_names_it_and_its_state(db, monkeypatch):
    jobs._ensure(db)
    run_id = jobs._insert(db, "workflow", "run-live", None, "automatic")
    db.execute("UPDATE jobs SET state = 'running', detail = '{\"name\": \"Detect Segments (Kraken)\"}' WHERE id = ?", [run_id])
    monkeypatch.setattr("fichero_server.execution.runner._running_workflows", {run_id: {"status": "running"}})

    runs, _running, _waiting = jobs.live_work(db)

    assert runs == [f"Detect Segments (Kraken), {run_id}, running"]


@pytest.fixture
def model_lane(monkeypatch):
    lane = jobs._scheduler.lanes["local-ml"]
    monkeypatch.setattr(lane, "running", {})
    monkeypatch.setattr(lane, "started", {})
    monkeypatch.setattr(lane, "heard", {})
    monkeypatch.setattr(lane, "live_calls", set())
    monkeypatch.setattr(lane, "kinds", {})
    monkeypatch.setattr(lane, "slots", 1)
    monkeypatch.setitem(jobs.KINDS, "says-every-page", jobs.Kind(run=None, model=None, says_per_item=True))
    return lane


def test_a_slow_live_model_job_keeps_its_slot_past_the_deadline(model_lane):
    """A model call still waiting on its answer is slow, not stuck: a page read for ten minutes keeps the one-slot lane,
    and a second heavy model never starts beside it (#6000, #5938), nor does the lane want a thread beside it."""
    lane = model_lane
    lane.running["slow-read"] = "mlx:a-big-reader"
    lane.started["slow-read"] = time.monotonic() - jobs.STUCK_MODEL_JOB_SECONDS * 10
    lane.live_calls.add("slow-read")

    assert lane.stuck() == set()
    assert "slow-read" in lane.holding()
    assert not lane.may_start("read-a-line", "mlx:another-big-reader")
    from fichero_server.llm.local_inference import LOCAL_READS_CEILING

    assert lane.threads_wanted == max(1, LOCAL_READS_CEILING)


def test_a_model_job_with_no_progress_past_the_deadline_lets_the_lane_go(model_lane):
    """A job on the one-slot model lane that has said nothing for the stuck-lane deadline, and is no live model call, is
    stuck: it holds no slot, so another project's job starts (#6213)."""
    lane = model_lane
    lane.running["wedged"] = "kraken:segment"
    lane.kinds["wedged"] = "says-every-page"
    lane.started["wedged"] = time.monotonic() - jobs.STUCK_MODEL_JOB_SECONDS - 1

    assert lane.stuck() == {"wedged"}
    assert lane.holding() == {}
    assert lane.may_start("read-a-line", "mlx:another-reader")


def test_a_slow_model_job_that_still_makes_progress_keeps_the_lane(db, model_lane):
    """Running past the deadline is not stuck while the job still says how it goes on its row (`jobs.say`,
    `jobs.save_detail`): each word is a sign of progress, and the deadline counts from the last one (#6213)."""
    lane = model_lane
    jobs._ensure(db)
    job_id = jobs._insert(db, "compare-line-finders", "samples", None, "automatic")
    lane.running[job_id] = None
    lane.kinds[job_id] = "says-every-page"
    lane.started[job_id] = time.monotonic() - jobs.STUCK_MODEL_JOB_SECONDS * 5

    jobs.say(db, job_id, "Page 7 of 20")
    assert lane.stuck() == set() and not lane.may_start("read-a-line", "mlx:another-reader")

    lane.heard[job_id] = time.monotonic() - jobs.STUCK_MODEL_JOB_SECONDS - 1
    jobs.save_detail(db, job_id, "{}", reason="Page 8 of 20")
    assert lane.stuck() == set()


@pytest.mark.parametrize("handed", ["to the lane", "in place"])
def test_a_kraken_page_silent_past_the_deadline_keeps_its_slot(db, model_lane, monkeypatch, handed):
    """A Kraken page is one call that writes nothing to its row while it computes (about 39 s a page on the M4, minutes on
    a 4-core Mac, #5846): handed to the lane, or run in place by a job already on it, it is a live call, slow and never
    stuck, so the one-heavy hold stays while Kraken computes (#6213)."""
    lane = model_lane
    lane.running["kraken-page"] = "kraken:blla"
    lane.started["kraken-page"] = time.monotonic() - jobs.STUCK_MODEL_JOB_SECONDS * 5
    monkeypatch.setattr(jobs._current, "job_id", "kraken-page", raising=False)
    monkeypatch.setattr(jobs._current, "lane", "local-ml", raising=False)
    seen: list[set[str]] = []

    def segment_lines():  # kraken_runtime.segment_lines, silent past the deadline
        seen.append(lane.stuck())
        return "lines"

    if handed == "to the lane":
        assert jobs._scheduler._work(db, "kraken-page", None, "page", (segment_lines, None, "local-ml", None)) == "lines"
    else:
        assert jobs.run_on_lane_blocking(None, "find-regions", "page", model="kraken:blla", fn=segment_lines) == "lines"
    assert seen == [set()]
    assert "kraken-page" not in lane.live_calls  # the call over, its silence counts again


def test_a_training_job_silent_past_the_deadline_keeps_the_heavy_hold(model_lane):
    """Local Kraken training says how it goes only at an epoch's end, and an epoch takes longer than the deadline: a kind
    that declares no per-item words is never let go by silence alone (only a dead claim frees it), so no reader or Kraken
    page starts beside ketos (#6000, b20)."""
    from fichero_server.training import local

    lane = model_lane
    lane.running["ketos"] = local.MODEL
    lane.kinds["ketos"] = local.KIND
    lane.started["ketos"] = time.monotonic() - jobs.STUCK_MODEL_JOB_SECONDS * 10

    assert lane.stuck() == set()
    assert "ketos" in lane.holding()
    assert not lane.may_start("read-a-line", "mlx:a-reader")


def test_the_trainer_beats_at_its_batches(db, model_lane, monkeypatch):
    """The trainer's batches are its heartbeat: the lane hears from it between epochs (b20)."""
    from fichero_server.training import local

    lane = model_lane
    lane.running["ketos"] = local.MODEL
    lane.heard["ketos"] = 0.0
    monkeypatch.setattr(local.Gentle, "verdict", lambda self: None)
    gentle = local.Gentle(db, "ketos", {})
    gentle.on_batch()

    assert lane.heard["ketos"] > time.monotonic() - 5


def test_saying_nothing_clears_the_reason(db):
    """`say(db, id, "")` leaves no words on the row: NULL, not an empty string a reader would show (b20)."""
    jobs._ensure(db)
    job_id = jobs._insert(db, "compare-line-finders", "samples", None, "automatic")
    jobs.say(db, job_id, "Page 1 of 2")
    jobs.say(db, job_id, "")
    assert jobs.read_job(db, job_id)["reason"] is None
