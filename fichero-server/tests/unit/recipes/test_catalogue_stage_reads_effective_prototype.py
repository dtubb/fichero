"""proto.runs.read-the-effective-prototype (#6087, #5636): the Catalogue stage's fields and the table step's units come from
the node's EFFECTIVE prototype, not its own key alone."""
from __future__ import annotations

from fichero_server.models import Artifact, DocType, Document
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
from fichero_server.recipes import catalogue_step as step
from fichero_server.recipes import table

TEXT = ("Title: Cartas del alcalde.\nDates: 1900\nExtent: 12 folios\nAccess points: Villa Sur\n"
        "Scope and content: Cartas.")


def _proto(db, key, attrs):
    db.save(ClassificationValue(dimension=ClassificationDimension.document_prototype, key=key, label=key,
                                attributes=attrs))


def _folder(db, name, parent=None, proto=None):
    doc = Document(name=name, path=f"/{name}", doc_type=DocType.folder, parent_id=parent, prototype_key=proto)
    db.save(doc)
    return doc


def _describe(db, folder):
    art = Artifact(document_id=folder.id, artifact_type=step.ARTIFACT_TYPE, content=TEXT, provider="p", model="m")
    db.save(art)
    step.put_in_attributes(db, folder.id, TEXT, art.id, run_id="r", provider="p", model="m")
    return db.get(Document, folder.id).attributes


def test_a_folder_with_no_prototype_keeps_the_fixed_set(db):
    attrs = _describe(db, _folder(db, "Sin"))
    assert {"catalogue_title", "catalogue_extent", "catalogue_scope_content"} <= set(attrs)


def test_a_folder_beneath_a_box_is_asked_the_boxs_folder_fields_with_no_assignment_of_its_own(db):
    _proto(db, "tfolder", {"catalogue_title": {"type": "text"}, "catalogue_date_normalised": {"type": "date"},
                           "name": {"type": "text", "source": "folder.name"}})
    _proto(db, "tbox", {"subfolders": "tfolder"})
    box = _folder(db, "Caja", proto="tbox")
    row = _folder(db, "Doc", box.id)
    assert row.prototype_key is None and step.asked_fields(db, row) >= {"catalogue_title", "catalogue_date_normalised"}
    attrs = _describe(db, row)
    assert attrs["catalogue_title"] == "Cartas del alcalde." and attrs["catalogue_date_normalised"] == "1900"
    assert "catalogue_extent" not in attrs and "catalogue_scope_content" not in attrs  # not declared: not asked
    assert "name" not in step.asked_fields(db, row)  # a computed column is never a field to fill


def test_the_table_step_asks_a_page_whose_kind_comes_from_the_folder_above(db):
    _proto(db, "tpage", {"folio": {"type": "text"}})
    _proto(db, "tfolder", {"pages": "tpage"})
    folder = _folder(db, "Doc", proto="tfolder")
    page = Document(name="p1", path="/p1", doc_type=DocType.page, parent_id=folder.id)
    db.save(page)
    assert page.prototype_key is None
    assert [u.id for u in table.units(db, [page.id], "tpage")] == [page.id]
    assert table.units(db, [page.id], "tother") == []
