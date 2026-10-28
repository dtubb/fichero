"""The stall watchdog says 'stalled' only when NOTHING moved (#5807).

Live 2026-10-18: "Processing imported pages stalled at 0 of 23" at 07:29:28, completed at 07:29:37, while
thumbnails were landing every 1-3 s. The deadline was pushed out only by an embed completion, so a slow first embed
or a model load read as 0 done. Any landed piece of work (a thumbnail, a page, a stage starting or ending) is movement.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from fichero_server.importers import derivatives


@pytest.fixture
def watched(tmp_path: Path, monkeypatch):
    library = str(tmp_path / "Lib.fichero")
    Path(library).mkdir()
    warnings: list[str] = []
    monkeypatch.setattr(derivatives, "STALL_SECONDS", 0.3)
    monkeypatch.setattr(derivatives, "_emit_queue_progress", lambda *a, **k: None)
    monkeypatch.setattr(
        derivatives, "_emit_queue_activity", lambda path, **k: warnings.append(k["message"]) if k.get("warning") else None
    )
    from fichero_server.execution import throttle

    monkeypatch.setattr(throttle, "why_wait", lambda **k: None)
    derivatives._progress_add(library, 3)
    yield library, warnings
    derivatives._disarm_stall_watchdog()
    derivatives._progress.pop(library, None)
    derivatives._queue_db_paths.pop(library, None)


def test_a_batch_whose_work_moves_but_does_not_complete_raises_no_stall(watched):
    library, warnings = watched
    end = time.monotonic() + 1.0  # more than three deadlines, with no completion
    while time.monotonic() < end:
        derivatives._progress_touch(library)
        time.sleep(0.05)
    assert warnings == []


def test_a_batch_with_no_movement_still_stalls(watched):
    _library, warnings = watched
    time.sleep(0.8)
    assert warnings and "stalled at 0 of 3" in warnings[0]


def test_touching_an_unwatched_library_arms_nothing(tmp_path):
    before = derivatives._stall_timer
    derivatives._progress_touch(str(tmp_path / "Other.fichero"))
    assert derivatives._stall_timer is before, "a library nobody queued work for gets no watchdog"


def test_a_landed_thumbnail_counts_as_movement(tmp_path: Path, monkeypatch):
    library = str(tmp_path / "Lib.fichero")
    touched: list[str] = []
    monkeypatch.setattr(derivatives, "_progress_touch", touched.append)
    monkeypatch.setattr(derivatives, "_open_stage_db", lambda lib, doc_id: None)
    derivatives._thumbnail_stage("doc-1", library)
    assert touched == [library, library], "a thumbnail stage moves the queue when it starts and when it ends"
    derivatives._embed_stage("doc-1", library)
    assert touched == [library] * 3, "and an embed stage when it starts"


def test_one_long_embed_reports_the_model_loading_not_a_stall(watched, monkeypatch):
    """10-16: one embed took 140 s with nothing else moving, and the queue was called stalled."""
    library, warnings = watched
    shown: list[str | None] = []
    monkeypatch.setattr("fichero_server.db.embeddings.embedder_loaded", lambda: False)
    monkeypatch.setattr(derivatives, "_emit_queue_progress", lambda *a, working=None, **k: shown.append(working))
    with derivatives._embedding(library):
        time.sleep(0.8)  # more than two deadlines inside one embed
    assert warnings == []
    assert shown and shown[-1] == "Loading the search model"
    assert library not in derivatives._busy


def test_an_embed_that_never_returns_still_stalls(watched, monkeypatch):
    library, warnings = watched
    monkeypatch.setattr(derivatives, "BUSY_CEILING_SECONDS", 0.4)
    with derivatives._embedding(library):
        time.sleep(1.0)
    assert warnings and "stalled at 0 of 3" in warnings[0]


def test_a_failed_embed_clears_the_busy_mark(watched):
    library, _ = watched
    with pytest.raises(RuntimeError), derivatives._embedding(library):
        raise RuntimeError("boom")
    assert library not in derivatives._busy


def test_two_overlapping_embeds_the_first_finishing_still_reads_as_work(watched):
    """The pool runs two embeds at once; the first to finish must not clear the mark of the one still running."""
    library, warnings = watched
    first = derivatives._embedding(library)
    second = derivatives._embedding(library)
    first.__enter__()
    second.__enter__()
    first.__exit__(None, None, None)
    assert library in derivatives._busy
    time.sleep(0.8)  # more than two deadlines with only the second in flight
    assert warnings == []
    second.__exit__(None, None, None)
    assert library not in derivatives._busy


def test_the_ceiling_counts_from_the_oldest_embed(watched, monkeypatch):
    library, warnings = watched
    monkeypatch.setattr(derivatives, "BUSY_CEILING_SECONDS", 0.5)
    stuck = derivatives._embedding(library)
    stuck.__enter__()
    time.sleep(0.35)
    newer = derivatives._embedding(library)
    newer.__enter__()  # a fresh start must not hide the one that never returns
    time.sleep(0.9)
    newer.__exit__(None, None, None)
    stuck.__exit__(None, None, None)
    assert warnings and "stalled" in warnings[0]


def test_the_search_model_is_loading_again_after_an_idle_release(monkeypatch):
    from fichero_server.db import embeddings

    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {"m": object()})
    assert embeddings.embedder_loaded() is True
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {})
    assert embeddings.embedder_loaded() is False


def test_a_queue_waiting_behind_another_kind_of_job_is_not_stalled(watched, monkeypatch):
    # A Kraken run holds the model lane for minutes; the embeds queued behind it are waiting their turn (#5807).
    library, warnings = watched
    monkeypatch.setattr(derivatives, "_jobs_say", lambda lib, since=None: "moving")
    time.sleep(0.8)
    assert warnings == []


def test_a_queue_whose_jobs_all_ended_set_aside_is_over_not_stalled(watched, monkeypatch):
    # The pages left in the count were set aside or failed: nothing is queued, so there is nothing to stall on (#5845).
    library, warnings = watched
    monkeypatch.setattr(derivatives, "_jobs_say", lambda lib, since=None: "over")
    time.sleep(0.8)
    assert warnings == [] and library not in derivatives._progress


def _job(db, kind: str, state: str):
    from fichero_server.execution import jobs

    job_id = jobs._insert(db, kind, "p", None, "automatic")
    db.execute("UPDATE jobs SET state = ?, finished_at = now() WHERE id = ?", [state, job_id])
    return job_id


@pytest.fixture
def table(db, monkeypatch):
    from fichero_server.db.manager import db_manager
    from fichero_server.execution import jobs

    jobs._ensure(db)
    jobs.load_kinds()
    monkeypatch.setattr(db_manager, "open_database", lambda key: db)
    return db


def test_page_work_of_ours_on_a_model_lane_running_says_moving(table):
    _job(table, "read-a-page", "running")
    assert derivatives._jobs_say("any") == "moving"


def test_a_workflow_row_a_batch_or_a_far_side_watcher_running_is_not_movement(table):
    for kind in ("workflow", "batch", "workflow-step", "train-a-model", "read-at-scale", derivatives.EMBED_KIND):
        _job(table, kind, "running")
    assert derivatives._jobs_say("any") is None  # a hung embed still alarms during a run


def test_over_needs_a_job_of_this_batch_to_have_failed_not_any_old_one(table):
    from fichero_server.core.timeutil import utc_now

    failed = _job(table, derivatives.THUMBNAIL_KIND, "failed")
    table.execute("UPDATE jobs SET finished_at = ? WHERE id = ?", [utc_now().replace(year=2020), failed])
    assert derivatives._jobs_say("any", since=utc_now()) is None  # an old failure from another batch
    _job(table, derivatives.THUMBNAIL_KIND, "failed")
    assert derivatives._jobs_say("any", since=utc_now().replace(year=2020)) == "over"


def test_a_hung_embed_past_the_ceiling_alarms_even_while_page_work_runs(watched, monkeypatch, table):
    library, warnings = watched
    _job(table, "read-a-page", "running")  # a Kraken run is going...
    monkeypatch.setattr(derivatives, "BUSY_CEILING_SECONDS", 0.1)
    with derivatives._progress_lock:
        derivatives._busy[library] = {1: ("Embedding a page", time.monotonic() - 5)}  # ...and one embed has hung
    try:
        time.sleep(0.8)
    finally:
        derivatives._busy.pop(library, None)
    assert warnings and "stalled at 0 of 3" in warnings[0]


def test_one_library_under_two_spellings_is_one_queue(tmp_path: Path, monkeypatch):
    """The real run 2026-10-27: the import queued under /tmp/…, the stages touched and ticked under /private/tmp/…
    (`str(Path(db.path).parent)`), so the watched queue never heard a thumbnail land: "stalled at 0 of 86" while they
    landed every few seconds. Every spelling of one library is one queue."""
    real = tmp_path / "real"
    (real / "Lib.fichero").mkdir(parents=True)
    (tmp_path / "link").symlink_to(real)
    queued, staged = str(tmp_path / "link" / "Lib.fichero"), str(real / "Lib.fichero")
    warnings: list[str] = []
    monkeypatch.setattr(derivatives, "STALL_SECONDS", 0.3)
    monkeypatch.setattr(derivatives, "_emit_queue_progress", lambda *a, **k: None)
    monkeypatch.setattr(
        derivatives, "_emit_queue_activity", lambda path, **k: warnings.append(k["message"]) if k.get("warning") else None
    )
    from fichero_server.execution import throttle

    monkeypatch.setattr(throttle, "why_wait", lambda **k: None)
    try:
        derivatives._progress_add(queued, 3)
        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            derivatives._progress_touch(staged)
            time.sleep(0.05)
        assert warnings == [], "a thumbnail landing under the other spelling is movement"
        derivatives._progress_tick(staged)
        assert [job["current"] for job in derivatives.background_jobs_snapshot(queued)] == [1]
        assert [job["current"] for job in derivatives.background_jobs_snapshot(staged)] == [1]
    finally:
        derivatives._disarm_stall_watchdog()
        derivatives._progress.clear()
        derivatives._queue_db_paths.clear()
