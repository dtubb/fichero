"""A new import's thumbnails are made before heavy local work on its pages (#5585).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md -- `activity.lane.thumbnails-first`.
After linking a 203-page box, many thumbnails were still blank half an hour later while the
recipe's reading had the Mac. Thumbnails are cheap and are what the person sees, so the local ML
lane now takes no job queued at or after a library's waiting thumbnails until they are made.
Through the real `import.folder` action, the real thumbnail stage (slowed, so the order shows)
and the real lanes; the reading's model call is faked.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import fichero_server.api.routes.ingest  # noqa: F401  (registers import.folder)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.importers import derivatives

PAGES = 6


@pytest.fixture
def box(tmp_path) -> Path:
    from PIL import Image

    folder = tmp_path / "Box 7"
    folder.mkdir()
    for i in range(PAGES):
        Image.new("RGB", (40, 60), "white").save(folder / f"f{i:03}.png")
    return folder


@pytest.fixture
def timeline(monkeypatch):
    """When each thumbnail finished and each embed started; the real thumbnail stage, slowed."""
    events: list[tuple[str, str, float]] = []
    lock = threading.Lock()
    real_thumbnail = derivatives._thumbnail_stage

    def thumbnail(doc_id, library):
        result = real_thumbnail(doc_id, library)
        time.sleep(0.15)
        with lock:
            events.append(("thumbnail", doc_id, time.monotonic()))
        return result

    def embed(doc_id, library):
        with lock:
            events.append(("embed", doc_id, time.monotonic()))

    monkeypatch.setattr(derivatives, "_thumbnail_stage", thumbnail)
    monkeypatch.setattr(derivatives, "_embed_stage", embed)
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    return events


def _import(test_package, folder: Path) -> list[str]:
    db = db_manager.get_database(test_package)
    ctx = ActionContext(actor="historian", library_path=str(test_package), is_bootstrap=True)
    return registry.invoke(db, "import.folder", {"path": str(folder)}, ctx).result["document_ids"]


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _read(db, doc_id: str, started: list[float]):
    """A page of a reading handed to the local ML lane, as a local reader's page is."""
    return jobs.submit(db, "read-a-page", doc_id, model="omlx:mlx-community/reader",
                       fn=lambda: started.append(time.monotonic()))


def test_with_a_reading_queued_the_new_pages_thumbnails_finish_first(test_package, box, timeline):
    """WHY: the reading took the Mac and the box stayed blank. The reading of the first page,
    handed in right after the import, waits (saying why) until every thumbnail of the import is
    made."""
    db = db_manager.get_database(test_package)
    doc_ids = _import(test_package, box)
    assert len(doc_ids) == PAGES
    started: list[float] = []
    reading = _read(db, doc_ids[0], started)

    def reason():
        row = db.execute_fetchone("SELECT reason FROM jobs WHERE kind = 'read-a-page'")
        return row[0] if row else None

    assert _wait_for(lambda: reason() == jobs.FIRST_REASON or started), "the held reading never said why"
    assert not started, "the reading started before the thumbnails"
    reading.result(timeout=60)

    thumbnails_done = [t for kind, _, t in timeline if kind == "thumbnail"]
    assert sorted(i for kind, i, _ in timeline if kind == "thumbnail") == sorted(doc_ids)
    assert started[0] >= max(thumbnails_done)


def test_the_imports_own_embeds_wait_for_its_thumbnails(test_package, box, timeline):
    """WHY: the embeds are queued in the same breath as the thumbnails and are the heavier half;
    the first thing on the screen is the pages, then search."""
    _import(test_package, box)
    assert _wait_for(lambda: sum(1 for e in timeline if e[0] == "embed") == PAGES)
    assert min(t for kind, _, t in timeline if kind == "embed") >= max(
        t for kind, _, t in timeline if kind == "thumbnail")


def test_a_reading_already_queued_before_the_import_is_not_held(test_package, box, timeline):
    """WHY: only work queued after the thumbnails waits for them; a page of a run that was already
    waiting keeps its place, so a big import cannot stall a reading someone started earlier."""
    db = db_manager.get_database(test_package)
    release = threading.Event()
    busy = jobs.submit(db, "read-a-page", "page-being-read", model="omlx:mlx-community/reader",
                       fn=lambda: release.wait(30))
    started: list[float] = []
    earlier = _read(db, "an-earlier-page", started)  # waits behind the page being read
    _import(test_package, box)
    release.set()
    busy.result(timeout=30)
    earlier.result(timeout=30)
    assert _wait_for(lambda: sum(1 for e in timeline if e[0] == "thumbnail") == PAGES)
    assert started[0] < max(t for kind, _, t in timeline if kind == "thumbnail")


def test_while_paused_a_persons_reading_does_not_wait_on_paused_thumbnails(test_package, box, timeline):
    """WHY: Pause holds the thumbnails; a page a person waits for still runs while paused. Held
    behind thumbnails that cannot run, it would wait forever."""
    db = db_manager.get_database(test_package)
    jobs.set_paused(True)
    doc_ids = _import(test_package, box)
    started: list[float] = []
    _read(db, doc_ids[0], started).result(timeout=30)
    assert started
    assert [e for e in timeline if e[0] == "thumbnail"] == []
