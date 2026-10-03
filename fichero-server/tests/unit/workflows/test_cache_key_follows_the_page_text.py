"""A text-reading workflow step's cache key follows the page's current text (#5361).

WHY: the node cache keyed on the image file (path, mtime, size), never on the words. After a person
corrected a page, re-running extraction was a cache HIT and returned the entities and claims read
from the misread text, so the knowledge graph never caught up with the correction. The key now
carries a fingerprint of the page text for tools that read text; tools that read the image keep
the file key, so a correction never re-runs OCR. If this regresses, corrected pages keep their old
entities on every re-run.
"""

from __future__ import annotations

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.models import DocType, Document
from fichero_server.workflows.cache import (
    IMAGE_READING_TOOLS,
    TEXT_READING_TOOLS,
    compute_batch_cache_key,
    compute_cache_key,
    text_fingerprint,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "Text.fichero"
    path.mkdir()
    db = db_manager.get_database(path)
    try:
        yield db
    finally:
        db_manager.close_database(path)


def _key(image, fp=""):
    return compute_cache_key(
        workflow_id="wf", node_id="n", tool="extract_all", config={}, provider="p", model="m",
        file_path=str(image), document_id="doc-1", text_fingerprint=fp,
    )


def _correct(db, doc_id, text):
    doc = db.get(Document, doc_id)
    doc.page_content = text
    db.save(doc)


def test_a_correction_changes_the_key_of_a_text_reader(db, tmp_path):
    image = tmp_path / "page.jpg"
    image.write_bytes(b"jpg")
    db.save(Document(id="doc-1", name="page.jpg", doc_type=DocType.file, page_content="Quito 1810"))
    before = _key(image, text_fingerprint(db, ["doc-1"]))
    assert _key(image, text_fingerprint(db, ["doc-1"])) == before, "same text, same key"

    _correct(db, "doc-1", "Quibdó 1810")

    assert _key(image, text_fingerprint(db, ["doc-1"])) != before


def test_a_correction_on_a_page_changes_its_parents_batch_key(db, tmp_path):
    db.save(Document(id="pdf", name="acta.pdf", doc_type=DocType.file))
    db.save(Document(id="p1", name="p1", doc_type=DocType.file, parent_id="pdf", page_content="Quito"))

    def batch():
        return compute_batch_cache_key(
            workflow_id="wf", node_id="n", tool="catalogue", config={}, provider="p", model="m",
            file_paths=[], text_fingerprint=text_fingerprint(db, ["pdf"]),
        )

    before = batch()
    _correct(db, "p1", "Quibdó")
    assert batch() != before


def test_image_readers_keep_the_file_key():
    """No fingerprint means the key is exactly what it was before #5361, so a correction never
    re-runs OCR and existing cached transcriptions stay valid."""
    assert {"transcribe", "describe"} <= IMAGE_READING_TOOLS
    assert {"extract_all", "extract", "summarize", "catalogue"} <= TEXT_READING_TOOLS
    assert not IMAGE_READING_TOOLS & TEXT_READING_TOOLS
    assert text_fingerprint(None, []) == ""
