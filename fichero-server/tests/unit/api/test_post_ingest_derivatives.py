"""Imported images get a thumbnail and leave Pending (#4225).

Before this stage existed, an imported image sat at ``Status: Pending`` with
no thumbnail forever: nothing in the ingest path produced a derivative, and
nothing moved the document off ``pending``. Thumbnails existed only where some
other process happened to have made one.

The shape (Daniel, 2026-07-28): "we want import fast, and then thumbnails
loading on a separate process". So the assertions below are about the SPLIT as
much as the outcome — the derivative work must not be on the import path, must
be bounded, and must announce itself per document so a row updates in place.
"""

from __future__ import annotations

from concurrent.futures import wait
from pathlib import Path

import pytest

from fichero_server.importers.derivatives import (
    DERIVATIVE_FILE_TYPES,
    MAX_CONCURRENT_DERIVATIVES,
    generate_derivative,
    needs_derivative,
    queue_derivatives,
)
from fichero_server.models import Document, DocType, FileType, Status


def _jpeg_bytes(size: tuple[int, int] = (64, 48)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, (120, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def ingested_image(db, test_package):
    """A LINK-mode image document, exactly as ingest records one."""
    from fichero_server.importers.ingest import IngestMode, ingest_file

    source = Path(test_package).parent / "IMG_075.jpg"
    source.write_bytes(_jpeg_bytes())
    doc = ingest_file(
        source,
        mode=IngestMode.LINK,
        db=db,
        package_path=Path(test_package),
        extract_text=False,
        auto_embed=False,
    )
    return doc


class TestTheStageProducesADerivative:
    def test_ingest_leaves_the_document_pending_without_a_thumbnail(
        self, ingested_image
    ):
        """The precondition — import itself still does the minimum (#4203)."""
        from fichero_server.db.storage import has_thumbnail

        assert ingested_image.status == Status.pending
        assert not has_thumbnail(ingested_image.id)

    def test_the_derivative_stage_produces_a_thumbnail(
        self, ingested_image, test_package
    ):
        thumb = generate_derivative(ingested_image.id, test_package)

        assert thumb is not None
        assert thumb.exists()
        assert thumb.stat().st_size > 0

    def test_the_document_leaves_pending(self, ingested_image, test_package, db):
        generate_derivative(ingested_image.id, test_package)

        after = db.get(Document, ingested_image.id)
        assert after.status == Status.completed
        assert "derivative_error" not in (after.metadata or {})

    def test_queueing_drains_and_produces_the_thumbnail(
        self, ingested_image, test_package, db
    ):
        futures = queue_derivatives([ingested_image], library_path=test_package)
        wait(futures, timeout=60)

        assert [f.result() for f in futures] != [None]
        assert db.get(Document, ingested_image.id).status == Status.completed


class TestFailureIsVisibleNotSilent:
    def test_a_missing_source_records_an_error_and_stays_pending(
        self, ingested_image, test_package, db
    ):
        """A document that CANNOT be rendered must not read as completed.

        "No thumbnail" alone is indistinguishable from "not yet"; the recorded
        error is what makes a failure selectable for retry (#4203's model).
        """
        Path(ingested_image.path).unlink()

        assert generate_derivative(ingested_image.id, test_package) is None

        after = db.get(Document, ingested_image.id)
        assert after.status == Status.pending
        assert (after.metadata or {}).get("derivative_error")

    def test_a_vanished_document_does_not_raise(self, test_package):
        assert generate_derivative("no-such-document", test_package) is None

    def test_a_later_success_clears_the_recorded_error(
        self, ingested_image, test_package, db
    ):
        source = Path(ingested_image.path)
        original = source.read_bytes()
        source.unlink()
        generate_derivative(ingested_image.id, test_package)
        source.write_bytes(original)

        generate_derivative(ingested_image.id, test_package)

        after = db.get(Document, ingested_image.id)
        assert "derivative_error" not in (after.metadata or {})
        assert after.status == Status.completed


class TestTheSplitAndItsBounds:
    def test_concurrency_is_bounded(self):
        """#1400: unbounded concurrent decode destabilised the window server."""
        assert 1 <= MAX_CONCURRENT_DERIVATIVES <= 4

    def test_only_renderable_types_are_queued(self):
        assert DERIVATIVE_FILE_TYPES == frozenset({FileType.image, FileType.pdf})
        assert needs_derivative(
            Document(name="a.jpg", doc_type=DocType.file, file_type=FileType.image)
        )
        assert not needs_derivative(
            Document(name="a.zip", doc_type=DocType.file, file_type=FileType.other)
        )

    def test_queueing_a_non_renderable_document_is_a_no_op(self, test_package):
        doc = Document(name="a.zip", doc_type=DocType.file, file_type=FileType.other)

        assert queue_derivatives([doc], library_path=test_package) == []

    def test_queueing_without_a_library_path_is_refused_loudly(self, caplog):
        doc = Document(name="a.jpg", doc_type=DocType.file, file_type=FileType.image)

        with caplog.at_level("WARNING"):
            assert queue_derivatives([doc], library_path="") == []

        assert "derivatives" in caplog.text.lower()

    def test_queueing_inside_a_transaction_waits_for_the_commit(
        self, ingested_image, test_package, db
    ):
        """The audited import.file action is ATOMIC.

        Submitting inside the open transaction lets a worker look up a
        document id that has not been committed yet, find nothing, and drop
        the thumbnail — a silent loss. The submission must ride the
        after-commit hook.
        """
        with db.transaction():
            # A real write, because the DB starts its transaction lazily and
            # only runs after-commit hooks when one actually started — a
            # read-only `with db.transaction()` discards them.
            db.save(ingested_image)
            futures = queue_derivatives(
                [ingested_image], library_path=test_package, db=db
            )
            assert futures == [], "must not submit before the commit"

        wait(futures, timeout=60)
        assert futures, "the commit must release the queued work"
        assert db.get(Document, ingested_image.id).status == Status.completed

    def test_the_route_passes_its_db_so_the_hook_is_used(self):
        import inspect

        from fichero_server.api.routes.ingest import core

        assert "db=db" in inspect.getsource(core.import_file_impl)

    def test_the_ingest_route_queues_the_work(self):
        """The stage must be WIRED — a queue nobody fills is not a pipeline."""
        import inspect

        from fichero_server.api.routes.ingest import core

        assert "queue_derivatives" in inspect.getsource(core.import_file_impl)
        assert "queue_derivatives" in inspect.getsource(core.import_folder_impl)


class TestTheDocumentUpdatedEventLands:
    def test_each_completed_derivative_emits_document_updated(
        self, ingested_image, test_package, monkeypatch
    ):
        """Rows update in place off the change stream — no manual refresh."""
        seen: list[tuple[str, tuple[str, ...]]] = []

        import fichero_server.api.change_stream as change_stream

        def record(library_path, *, type, document_ids=(), **kwargs):
            seen.append((type, tuple(document_ids)))

        monkeypatch.setattr(change_stream, "emit_change", record)

        generate_derivative(ingested_image.id, test_package)

        assert ("document.updated", (ingested_image.id,)) in seen


class TestDeferredEmbedding:
    """Embedding moved off the import path (2026-08-09).

    The old inline default made a first import pay the ~19s embedding-model
    load plus per-page compute before the request finished — Daniel:
    "shouldn't embeddings happen after it's imported?". Rows now land
    instantly; this stage embeds and only then clears ``pending``.
    """

    def test_ingest_request_defaults_defer_embedding(self):
        from fichero_server.api.routes.ingest.core import (
            IngestFileRequest,
            IngestFolderRequest,
        )

        assert IngestFileRequest(path="/x").auto_embed is False
        assert IngestFolderRequest(path="/x").auto_embed is False

    def test_text_bearing_documents_are_queued(self, test_package):
        from fichero_server.importers.derivatives import needs_embedding

        text_doc = Document(
            name="a.md", doc_type=DocType.file,
            file_type=FileType.text, page_content="hello",
        )
        assert needs_embedding(text_doc)
        assert queue_derivatives([text_doc], library_path=test_package)
        assert not needs_embedding(
            Document(name="a.zip", doc_type=DocType.file, file_type=FileType.other)
        )

    def test_the_stage_embeds_the_document_and_its_pdf_pages(
        self, db, test_package, monkeypatch
    ):
        parent = Document(
            name="a.pdf", doc_type=DocType.file, file_type=FileType.pdf,
            status=Status.pending, page_content="doc text",
        )
        db.save(parent)
        page = Document(
            name="page 1", doc_type=DocType.file, parent_id=parent.id,
            status=Status.completed, page_content="page text",
        )
        db.save(page)
        embedded: list[str] = []
        monkeypatch.setattr(
            type(db), "embed",
            lambda self, doc: (embedded.append(doc.id), True)[1],
        )

        generate_derivative(parent.id, test_package)

        assert parent.id in embedded
        assert page.id in embedded

    def test_pending_clears_after_deferred_embedding(
        self, db, test_package, monkeypatch
    ):
        doc = Document(
            name="a.md", doc_type=DocType.file, file_type=FileType.text,
            status=Status.pending, page_content="hello",
        )
        db.save(doc)
        monkeypatch.setattr(type(db), "embed", lambda self, d: True)

        generate_derivative(doc.id, test_package)

        refreshed = db.get(Document, doc.id)
        assert refreshed.status == Status.completed
        assert "embedding_error" not in (refreshed.metadata or {})

    def test_an_embed_failure_is_recorded_and_does_not_strand_pending(
        self, db, test_package, monkeypatch
    ):
        doc = Document(
            name="a.md", doc_type=DocType.file, file_type=FileType.text,
            status=Status.pending, page_content="hello",
        )
        db.save(doc)

        def exploding_embed(self, _doc):
            raise RuntimeError("model blew up")

        monkeypatch.setattr(type(db), "embed", exploding_embed)

        generate_derivative(doc.id, test_package)

        refreshed = db.get(Document, doc.id)
        assert refreshed.status == Status.completed
        assert "embeds failed" in refreshed.metadata["embedding_error"]
