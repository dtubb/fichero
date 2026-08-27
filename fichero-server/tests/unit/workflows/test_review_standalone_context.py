"""Paleographer Review runs STANDALONE on an already-transcribed document.

With no wired draft, transcribe_review pulls the document's existing text —
page_content first, else the newest transcription-family artifact
(2026-08-26: "do a transcription, then run a paleographer update on the
artifact"). No text anywhere → None, and the review works from the image.
"""

from fichero_server.models import Artifact, Document
from fichero_server.workflows.tools.transcribe_review import (
    _existing_transcription_context,
)


def test_page_content_is_the_first_source(db, test_package):
    doc = Document(id="d1", name="p1.jpg", page_content="texto existente")
    db.save(doc)
    texts = _existing_transcription_context(str(test_package), [doc])
    assert texts == ["texto existente"]


def test_latest_transcription_artifact_is_the_fallback(db, test_package):
    doc = Document(id="d2", name="p2.jpg")
    db.save(doc)
    db.save(Artifact(document_id="d2", artifact_type="transcription",
                     content="borrador viejo"))
    db.save(Artifact(document_id="d2", artifact_type="transcription_review",
                     content="revisión nueva"))
    texts = _existing_transcription_context(str(test_package), [doc])
    assert texts is not None
    assert texts[0] in ("revisión nueva", "borrador viejo")


def test_no_text_anywhere_returns_none(db, test_package):
    doc = Document(id="d3", name="p3.jpg")
    db.save(doc)
    assert _existing_transcription_context(str(test_package), [doc]) is None
