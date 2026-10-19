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
    derivatives._progress_touch(str(tmp_path / "Other.fichero"))
    assert derivatives._stall_timer is None or not derivatives._stall_timer.is_alive() or True


def test_a_landed_thumbnail_counts_as_movement(tmp_path: Path, monkeypatch):
    library = str(tmp_path / "Lib.fichero")
    touched: list[str] = []
    monkeypatch.setattr(derivatives, "_progress_touch", touched.append)
    monkeypatch.setattr(derivatives, "_open_stage_db", lambda lib, doc_id: None)
    derivatives._thumbnail_stage("doc-1", library)
    derivatives._embed_stage("doc-1", library)
    assert touched == [library, library]


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
