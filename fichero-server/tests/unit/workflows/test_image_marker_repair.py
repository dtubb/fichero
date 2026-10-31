"""A metadata field the image marker replaced gets its reading's text back, and a second run changes nothing."""
from fichero_server.maintenance.image_marker_repair import repair_image_marker_fields
from fichero_server.models import Artifact, DocType, Document, FileType


def test_the_field_is_put_back_from_the_readings_text(db):
    page = Document(name="p", path="/p.jpg", doc_type=DocType.page, file_type=FileType.image,
                    metadata={"description": {"image_read": "original"}, "caption": {"image_read": "original"},
                              "keywords": {"a": 1}})
    db.save(page)
    db.save(Artifact(document_id=page.id, artifact_type="description", content="A harbour.", provider="x", model="y"))
    assert repair_image_marker_fields(db) == {"repaired": 1, "left": 1, "document_ids": [page.id]}  # caption has no reading: left, not guessed
    meta = db.get(Document, page.id).metadata
    assert meta["description"] == "A harbour." and meta["caption"] == {"image_read": "original"} and meta["keywords"] == {"a": 1}
    assert repair_image_marker_fields(db)["repaired"] == 0


def test_a_library_opened_on_new_code_is_repaired_through_the_real_open_and_it_is_visible(tmp_path):
    from fichero_server.db import db_manager

    package = tmp_path / "Dev Project.fichero"
    db = db_manager.get_database(package, create=True)
    page = Document(name="p", path="/p.jpg", doc_type=DocType.page, file_type=FileType.image,
                    metadata={"description": {"image_read": "original"}})
    db.save(page)
    db.save(Artifact(document_id=page.id, artifact_type="description", content="A harbour.", provider="x", model="y"))
    db_manager.close_database(package)
    db = db_manager.get_database(package)
    try:
        assert db.get(Document, page.id).metadata["description"] == "A harbour."
        rows = db.execute_fetchall("SELECT state, reason FROM jobs WHERE id LIKE 'repair-image-marker-%'")
        assert len(rows) == 1 and rows[0][0] == "done" and "1 description or caption field" in rows[0][1]
    finally:
        db_manager.close_database(package)
    db = db_manager.get_database(package)
    try:
        assert len(db.execute_fetchall("SELECT id FROM jobs WHERE id LIKE 'repair-image-marker-%'")) == 1, "a second open adds nothing"
    finally:
        db_manager.close_database(package)
