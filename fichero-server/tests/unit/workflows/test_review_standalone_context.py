"""Paleographer Review runs STANDALONE on an already-transcribed document.

With no wired draft, the review is given the document's existing text -- page_content first, else
the newest transcription-family artifact (2026-08-26: "do a transcription, then run a paleographer
update on the artifact"). No text anywhere: the review works from the image, and says so. Since
#5026 slice 2 this is the one page-context builder (`tool_context`), not a helper of its own; a
page WITH segments gets its lines (test_every_page_reading_tool_is_given_the_page.py).
"""

from fichero_server.models import Artifact, Document
from fichero_server.tool_context import tool_context


def test_page_content_is_the_first_source(db):
    db.save(Document(id="d1", name="p1.jpg", page_content="texto existente"))
    got = tool_context(db, "d1")
    assert (got.plain, got.text) == (True, "texto existente")


def test_latest_transcription_artifact_is_the_fallback(db):
    db.save(Document(id="d2", name="p2.jpg"))
    db.save(Artifact(document_id="d2", artifact_type="transcription", content="borrador viejo"))
    db.save(Artifact(document_id="d2", artifact_type="transcription_review", content="revisión nueva"))
    got = tool_context(db, "d2")
    assert got.plain and got.text in ("revisión nueva", "borrador viejo")


def test_no_text_anywhere_says_the_review_works_from_the_image(db):
    db.save(Document(id="d3", name="p3.jpg"))
    got = tool_context(db, "d3")
    assert not got.plain and got.text == "" and "works from the picture alone" in got.statement
