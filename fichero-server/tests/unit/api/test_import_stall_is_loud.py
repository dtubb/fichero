"""An import that cannot finish must SAY so, not sit at 0% (#4574 follow-up).

Daniel dragged a PDF from another Mac over SMB and the app showed "Processing
imported pages — 0%" indefinitely. The derivative pool has two workers, and a
read against a network volume whose credentials have expired does not fail —
it blocks. Two blocked reads and the queue stops dead: nothing completes, so
nothing ticks the progress counter, so the bar never moves and no error is
ever surfaced. A bar at 0% is indistinguishable from a bar about to move, and
that ambiguity IS the bug.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fichero_server.importers import derivatives
from fichero_server.models import Document, DocType, FileType, Status


def _jpeg_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (32, 24), (10, 90, 160)).save(buf, format="JPEG")
    return buf.getvalue()


class TestTheReadabilityProbe:
    def test_a_readable_file_passes(self, tmp_path: Path):
        path = tmp_path / "ok.jpg"
        path.write_bytes(_jpeg_bytes())
        assert derivatives._probe_source_readable(path) is None

    def test_an_unreadable_file_names_itself(self, tmp_path: Path):
        path = tmp_path / "denied.jpg"
        path.write_bytes(_jpeg_bytes())
        os.chmod(path, 0o000)
        try:
            error = derivatives._probe_source_readable(path)
        finally:
            os.chmod(path, 0o600)
        assert error is not None
        assert "denied.jpg" in error

    def test_a_blocking_read_returns_within_the_deadline(
        self, tmp_path: Path, monkeypatch
    ):
        """A FIFO nobody writes to is a read that never returns.

        This is the SMB shape in miniature: the file exists, stat succeeds,
        and the first byte never arrives. The probe must hand the worker back
        rather than holding it, so the queue keeps draining.
        """
        fifo = tmp_path / "never.fifo"
        os.mkfifo(fifo)
        monkeypatch.setattr(derivatives, "SOURCE_READ_DEADLINE_SECONDS", 0.5)

        error = derivatives._probe_source_readable(fifo)

        assert error is not None
        assert "did not return a byte" in error
        # And it must SAY what to do about it, not just that it failed.
        assert "network volume" in error

    def test_exists_is_not_readability(self, tmp_path: Path, monkeypatch):
        """The distinction the old code missed, stated as a test."""
        fifo = tmp_path / "present.fifo"
        os.mkfifo(fifo)
        monkeypatch.setattr(derivatives, "SOURCE_READ_DEADLINE_SECONDS", 0.5)
        assert fifo.exists()
        assert derivatives._probe_source_readable(fifo) is not None


class TestOnlyDocumentsThatExpectBytesAreJudged:
    def test_a_text_only_document_is_not_called_unreadable(self, db, test_package):
        """A note has no file; that is not a failure."""
        note = Document(
            name="a note", doc_type=DocType.file, page_content="text", status=Status.pending
        )
        db.save(note)
        assert derivatives._source_error(note, db, str(test_package)) is None

    def test_an_image_with_no_file_is_named(self, db, test_package):
        ghost = Document(
            name="gone.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            path="/nowhere/gone.jpg",
            status=Status.pending,
        )
        db.save(ghost)
        error = derivatives._source_error(ghost, db, str(test_package))
        assert error is not None
        assert "gone.jpg" in error


class TestTheQueueKeepsMovingThroughAFailure:
    def test_an_unreadable_source_records_the_reason_and_still_ticks(
        self, db, test_package, monkeypatch
    ):
        """The failure is recorded AND the bar advances — both, or neither helps.

        Recording without ticking leaves the island at 0% with the reason
        buried on a row nobody is looking at; ticking without recording moves
        the bar past a document that silently never got a thumbnail.
        """
        source = Path(test_package).parent / "blocked.jpg"
        source.write_bytes(_jpeg_bytes())
        doc = Document(
            name="blocked.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            path=str(source),
            status=Status.pending,
        )
        db.save(doc)
        os.chmod(source, 0o000)

        frames: list[dict] = []
        monkeypatch.setattr(
            derivatives,
            "_emit_queue_progress",
            lambda library, done, total, **kw: frames.append(
                {"done": done, "total": total, **kw}
            ),
        )
        derivatives._progress_add(str(test_package), 1)
        try:
            derivatives.generate_derivative(doc.id, str(test_package))
        finally:
            os.chmod(source, 0o600)

        after = db.get(Document, doc.id)
        assert (after.metadata or {}).get("derivative_error"), "reason not recorded"
        assert "blocked.jpg" in after.metadata["derivative_error"]
        # The queue reached its total rather than stopping short at 0.
        assert frames[-1]["done"] == frames[-1]["total"] == 1


class TestTheStallWatchdog:
    def test_it_reports_a_queue_that_stops_moving(self, test_package, monkeypatch):
        library = str(test_package)
        monkeypatch.setattr(derivatives, "STALL_SECONDS", 0.2)
        reported = threading.Event()
        frames: list[dict] = []

        def capture(lib, done, total, **kw):
            frames.append({"done": done, "total": total, **kw})
            if kw.get("stalled"):
                reported.set()

        monkeypatch.setattr(derivatives, "_emit_queue_progress", capture)
        derivatives._progress_add(library, 3)
        try:
            assert reported.wait(timeout=5), "a stalled queue said nothing"
        finally:
            derivatives._disarm_stall_watchdog()
            derivatives._progress.pop(library, None)
        stalled = [frame for frame in frames if frame.get("stalled")]
        assert stalled[-1]["done"] == 0 and stalled[-1]["total"] == 3

    def test_progress_stands_the_watchdog_down_when_the_work_finishes(
        self, test_package, monkeypatch
    ):
        """No false alarm after a normal completion."""
        library = str(test_package)
        monkeypatch.setattr(derivatives, "STALL_SECONDS", 0.2)
        monkeypatch.setattr(derivatives, "_emit_queue_progress", lambda *a, **k: None)
        derivatives._progress_add(library, 1)
        derivatives._progress_tick(library)
        assert derivatives._stall_timer is None or not derivatives._stall_timer.is_alive()


class TestTheStalledFrameIsDistinguishable:
    def test_a_stalled_frame_does_not_read_as_running(self, test_package, monkeypatch):
        """The whole point: "stalled" must not look like "still going"."""
        sent: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library, **kw: sent.append(kw),
        )
        derivatives._emit_queue_progress(str(test_package), 0, 12, stalled=True)
        assert sent, "no frame emitted"
        metadata = sent[-1]["metadata"]
        assert metadata["status"] == "stalled"
        assert "Stalled" in metadata["message"]
        assert "network volume" in metadata["message"]

        sent.clear()
        derivatives._emit_queue_progress(str(test_package), 3, 12)
        assert sent[-1]["metadata"]["status"] == "running"


class TestALongBookReportsPagesNotDocuments:
    """The second, independent cause of "0%": the counter counted DOCUMENTS.

    Daniel imported his own 252-page book and watched "Processing imported
    pages — 0%". Nothing was wrong with the embedding: `queue_derivatives`
    seeds one unit per DOCUMENT, so a single-PDF import has a total of 1, and
    every page of the book embeds inside that one unfinished unit. The bar had
    exactly two states — 0% and done — while the label said "pages". A
    truthful count of documents read as a stuck count of pages, and twenty
    minutes of 0% is indistinguishable from a hang.
    """

    def _book(self, db, pages: int) -> Document:
        parent = Document(
            name="book.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            status=Status.pending,
        )
        db.save(parent)
        for number in range(1, pages + 1):
            db.save(
                Document(
                    name=f"book.pdf - Page {number}",
                    doc_type=DocType.page,
                    parent_id=parent.id,
                    sequence=number,
                    page_content=f"page {number} text",
                )
            )
        return parent

    def test_the_bar_moves_through_the_pages(self, db, test_package, monkeypatch):
        library = str(test_package)
        monkeypatch.setattr(type(db), "embed", lambda self, doc: True)
        book = self._book(db, 12)

        frames: list[dict] = []
        monkeypatch.setattr(
            derivatives,
            "_emit_queue_progress",
            lambda lib, done, total, **kw: frames.append({"done": done, "total": total}),
        )
        derivatives._progress_add(library, 1)
        derivatives._embed_stage(book.id, library)

        # The total grew to include the pages, rather than staying at one
        # document that is either unfinished or finished.
        assert frames[-1]["total"] == 13, "pages never joined the total"
        assert frames[-1]["done"] == frames[-1]["total"], "queue never completed"
        # And it actually MOVED: more than the two states the old counter had.
        distinct = {frame["done"] for frame in frames}
        assert len(distinct) > 2, f"bar had only these states: {sorted(distinct)}"

    def test_a_page_that_fails_to_embed_still_advances_the_bar(
        self, db, test_package, monkeypatch
    ):
        """Ticking only on success leaves the total unreachable — the same
        silence, reached from the other side."""
        library = str(test_package)

        def explode(self, doc):
            if "Page 2" in doc.name:
                raise RuntimeError("model said no")
            return True

        monkeypatch.setattr(type(db), "embed", explode)
        book = self._book(db, 4)

        frames: list[dict] = []
        monkeypatch.setattr(
            derivatives,
            "_emit_queue_progress",
            lambda lib, done, total, **kw: frames.append({"done": done, "total": total}),
        )
        derivatives._progress_add(library, 1)
        derivatives._embed_stage(book.id, library)

        assert frames[-1]["done"] == frames[-1]["total"] == 5
        after = db.get(Document, book.id)
        assert (after.metadata or {}).get("embedding_error"), "failure not recorded"
