"""A thumbnail or an embed that fails ends its job FAILED with a plain sentence and its fix, never silently (#6584).

Spec: docs/contributor_manual/specs/ui/activity-pane.md `activity.run.failed-is-never-requeued-by-itself`,
`activity.pane.failure-with-its-fix-in-the-row`. WHY (owner 2026-11-13): a page whose thumbnail failed kept `Status.pending`
with the error in its metadata, the job read done, nothing in Activity said so, and the next open ran it again.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document, FileType


def _page(db, tmp_path) -> Document:
    path = tmp_path / "page.png"
    Image.new("RGB", (16, 16), (255, 255, 255)).save(str(path), format="PNG")
    doc = Document(name="page.png", doc_type=DocType.file, file_type=FileType.image, path=str(path), page_content="x")
    db.save(doc)
    return doc


def test_a_thumbnail_that_cannot_be_made_fails_the_job_in_plain_words(db, tmp_path, monkeypatch):
    doc = _page(db, tmp_path)

    def broken(doc, package_path, db):
        raise ValueError("PIL cannot identify image file")

    monkeypatch.setattr("fichero_server.db.storage.ensure_thumbnail", broken)

    with pytest.raises(derivatives.DerivativeFailed) as failed:
        derivatives._thumbnail_job(db, doc.id)

    words = jobs.failed_reason(derivatives.THUMBNAIL_KIND, failed.value)
    assert words == "The thumbnail for page.png could not be made. Try again, or open the file to check it is a readable image."
    assert "PIL" not in words, "the raw error is for Copy Details, not the row"
    kept = db.get(Document, doc.id)
    assert "PIL cannot identify" in kept.metadata["derivative_error"], "the raw error is kept on the document"
    assert kept.status.value == "pending"


def test_an_embed_that_fails_ends_its_job_failed_not_done(db, tmp_path, monkeypatch):
    doc = _page(db, tmp_path)
    monkeypatch.setattr(derivatives, "_embed_document_tree", lambda doc, db, library: "the embedder choked")

    with pytest.raises(derivatives.DerivativeFailed, match="Search could not index page.png"):
        derivatives._embed_job(db, doc.id)  # as the embed JOB runs it
    derivatives._embed_stage(doc.id, str(Path(db.path).parent))  # an import's inline pass records and goes on

    assert db.get(Document, doc.id).metadata["embedding_error"] == "the embedder choked"
