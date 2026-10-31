"""A metadata field the image marker replaced gets its reading's text back, and a second run changes nothing."""
from fichero_server.maintenance.image_marker_repair import repair_image_marker_fields
from fichero_server.models import Artifact, DocType, Document, FileType


def test_the_field_is_put_back_from_the_readings_text(db):
    page = Document(name="p", path="/p.jpg", doc_type=DocType.page, file_type=FileType.image,
                    metadata={"description": {"image_read": "original"}, "caption": {"image_read": "original"},
                              "keywords": {"a": 1}})
    db.save(page)
    db.save(Artifact(document_id=page.id, artifact_type="description", content="A harbour.", provider="x", model="y"))
    assert repair_image_marker_fields(db) == {"repaired": 1, "left": 1}  # caption has no reading: left, not guessed
    meta = db.get(Document, page.id).metadata
    assert meta["description"] == "A harbour." and meta["caption"] == {"image_read": "original"} and meta["keywords"] == {"a": 1}
    assert repair_image_marker_fields(db)["repaired"] == 0
