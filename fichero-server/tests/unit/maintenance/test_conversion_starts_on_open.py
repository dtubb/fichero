"""The whole-library conversion starts when a library opens, and says what it did (#5222).

Spec: `segments-and-geometry.md` -- `source.convert.starts-when-a-project-opens`,
`.a-page-is-all-or-nothing`, `.report`.

WHY: `convert_project` was built, proved and pinned, and nothing called it (#5088). So every page
hand-corrected before the page model stayed one rerun away from losing that correction, silently
(#5075), and results never became passes. The ruling (2026-09-20): convert the whole library,
automatically, when it opens, snapshot first. If this regresses, libraries stay half old and half
new; if the start blocks, opening a large library hangs; if a page can half-convert, a crash
leaves a page in a state nobody chose.

Every test builds its own library in a temp dir, and opens it through a PRIVATE
`DatabaseManager`, never the engine's singleton, never a real library.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action and route)
from fichero_server.api.routes.document import segment_conversion
from fichero_server.db import Database
from fichero_server.db.manager import DatabaseManager
from fichero_server.maintenance import conversion_on_open
from fichero_server.maintenance import project_conversion as pc
from fichero_server.models import Artifact, Segment, SegmentPass
from fichero_server.models.conversion import ConversionRun, ConversionVerdict
from tests.unit.maintenance.test_project_conversion_resume import _pages, _snapshot_stub

pytestmark = pytest.mark.source_model


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A library of 4 unconverted pages, closed, ready to be OPENED; conversion switched ON."""
    monkeypatch.delenv("FICHERO_SKIP_PROJECT_CONVERSION", raising=False)
    package = tmp_path / "Old.fichero"
    package.mkdir()
    db = Database(package / "fichero.duckdb")
    docs = _pages(db, 4)
    db.close()
    _snapshot_stub(package, monkeypatch)
    manager = DatabaseManager()
    yield package, manager, [d.id for d in docs]
    conversion_on_open.stop(None)
    manager.close_all()


def _open_and_wait(manager: DatabaseManager, package: Path) -> Database:
    db = manager.get_database(package)
    thread = conversion_on_open._runs.get(manager._cache_key(package), (None,))[0]
    assert thread is not None, "opening started no conversion"
    thread.join(120)
    assert not thread.is_alive()
    return db


def _converted(db: Database, document_id: str) -> bool:
    artifacts = db.query(Artifact, document_id=document_id)
    return all(a.geometry_superseded_by_pass_id for a in artifacts)


def test_opening_converts_every_page_in_the_background(library):
    package, manager, doc_ids = library
    db = _open_and_wait(manager, package)
    assert all(_converted(db, d) for d in doc_ids)
    assert all(db.query(Segment, document_id=d) for d in doc_ids)
    [run] = db.query(ConversionRun)
    assert run.verdict is ConversionVerdict.completed and run.pages_converted == 4


def test_the_open_returns_before_the_conversion_does(library, monkeypatch):
    """A large library must open at once: the runner is held on its first page and the open
    has already returned."""
    package, manager, _ids = library
    release = threading.Event()
    original = pc._convert_one_page

    def held(db, document_id, run_id):
        release.wait(120)
        return original(db, document_id, run_id)

    monkeypatch.setattr(pc, "_convert_one_page", held)
    db = manager.get_database(package)                      # returned while held
    assert not release.is_set()
    assert not any(a.geometry_superseded_by_pass_id for a in db.query(Artifact))
    release.set()
    conversion_on_open._runs[manager._cache_key(package)][0].join(120)


def test_a_second_open_writes_nothing(library):
    package, manager, _ids = library
    _open_and_wait(manager, package)
    manager.close_database(package)
    db = manager.get_database(package)
    thread = conversion_on_open._runs[manager._cache_key(package)][0]
    thread.join(120)
    assert len(db.query(ConversionRun)) == 1                # nothing to do files no report


def test_closing_mid_run_stops_at_a_page_boundary_and_the_next_open_finishes(library, monkeypatch):
    package, manager, doc_ids = library
    first_page_done = threading.Event()
    go_on = threading.Event()
    original = pc._convert_one_page

    def slow(db, document_id, run_id):
        outcome = original(db, document_id, run_id)
        first_page_done.set()
        go_on.wait(120)
        return outcome

    monkeypatch.setattr(pc, "_convert_one_page", slow)
    manager.get_database(package)
    assert first_page_done.wait(120)
    closer = threading.Thread(target=manager.close_database, args=(package,))
    closer.start()
    go_on.set()
    closer.join(120)
    monkeypatch.setattr(pc, "_convert_one_page", original)

    db = _open_and_wait(manager, package)
    assert all(_converted(db, d) for d in doc_ids)
    runs = sorted(db.query(ConversionRun), key=lambda r: r.started_at)
    assert runs[0].pages_converted == 1 and runs[-1].pages_converted == 3


def test_a_fault_inside_a_pages_transaction_leaves_that_page_untouched(library, monkeypatch):
    """The fault is raised INSIDE the page's transaction, after its pass and segments are
    written and before its marker: the page must come out with none of them."""
    package, manager, doc_ids = library
    doomed = doc_ids[1]
    original = segment_conversion._readings_from_conversion

    def fault(db, artifact, rows, reads):
        if artifact.document_id == doomed:
            raise RuntimeError("disk vanished mid-page")
        return original(db, artifact, rows, reads)

    monkeypatch.setattr(segment_conversion, "_readings_from_conversion", fault)
    db = _open_and_wait(manager, package)

    assert not db.query(Segment, document_id=doomed)
    assert not db.query(SegmentPass, document_id=doomed)
    assert not _converted(db, doomed)
    assert all(_converted(db, d) for d in doc_ids if d != doomed)
    [run] = db.query(ConversionRun)
    assert [(f.document_id, "disk vanished" in f.reason) for f in run.failures] == [(doomed, True)]


def test_when_the_snapshot_cannot_be_made_nothing_converts_and_it_says_why(library, monkeypatch):
    package, manager, doc_ids = library
    import fichero_server.db.storage_snapshots as snaps

    def no_room(*_a, **_k):
        raise RuntimeError("the snapshot volume is full")

    monkeypatch.setattr(snaps, "snapshot_library", no_room)
    db = _open_and_wait(manager, package)
    assert not db.query(Segment)
    [run] = db.query(ConversionRun)
    assert run.verdict is ConversionVerdict.refused_snapshot


def test_the_status_route_reports_the_run_what_is_left_and_what_was_not_converted(db, client):
    """What the app's pill reads. A page that failed is named with its reason; a `segmentation`
    artifact is named as left as it was; `seen` is recorded once the run is final."""
    from fichero_server.models.conversion import ConversionFailure
    from fichero_server.models import DocType, Document, FileType

    empty = client.get("/api/conversion/status").json()
    assert empty["running"] is False and empty["run_id"] is None

    doc = Document(name="old.jpg", doc_type=DocType.file, file_type=FileType.image, path="/o.jpg")
    db.save(doc)
    db.save(Artifact(document_id=doc.id, artifact_type="segmentation", data={"segments": [{"bbox": [1, 2, 3, 4]}]}))
    run = ConversionRun(verdict=ConversionVerdict.completed, pages_converted=3, snapshot_path="/snap",
                        failures=[ConversionFailure(document_id="d9", reason="a box lies outside the page")])
    run.finished_at = run.started_at
    db.save(run)

    status = client.get("/api/conversion/status").json()
    assert status["verdict"] == "completed" and status["pages_converted"] == 3
    assert status["pages_not_converted"] == [{"document_id": "d9", "reason": "a box lies outside the page"}]
    assert [row["artifact_type"] for row in status["left_as_they_were"]] == ["segmentation"]
    assert status["seen"] is False
    assert client.post(f"/api/conversion/{run.run_id}/seen").json()["seen"] is True
