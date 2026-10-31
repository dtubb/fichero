"""proto.value.set-inherited-default-empty: the value walk, with the origin of every value."""

import pytest

from fichero_server.db import Database
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
from fichero_server.models.node_prototypes import effective_node_attributes


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.duckdb")
    d.save(ClassificationValue(
        dimension=ClassificationDimension.document_prototype, key="tbox", label="box",
        attributes={"subfolders": "tfolder"}))
    d.save(ClassificationValue(
        dimension=ClassificationDimension.document_prototype, key="tfolder", label="folder",
        attributes={
            "ref": {"type": "text", "inherits": True},
            "title": {"type": "text"},
            "rights": {"type": "text", "inherits": True, "default": "CC BY"},
        }))
    yield d
    d.close()


def _doc(db, id, doc_type, parent=None, proto=None, attributes=None):
    doc = Document(id=id, name=id, path=f"/{id}", doc_type=doc_type, parent_id=parent,
                   prototype_key=proto, attributes=attributes or {})
    db.save(doc)
    return doc


def test_set_here_inherited_default_empty(db):
    _doc(db, "box", DocType.folder, proto="tbox", attributes={"ref": "EAP1", "title": "box title"})
    f = _doc(db, "f1", DocType.folder, parent="box", attributes={"title": "mine"})
    out = effective_node_attributes(db, f)
    assert out["title"]["value"] == "mine" and out["title"]["origin"] == "here"
    assert out["ref"]["value"] == "EAP1"
    assert (out["ref"]["origin"], out["ref"]["from"]) == ("inherited", "box")
    assert (out["rights"]["value"], out["rights"]["origin"]) == ("CC BY", "default")


def test_non_inheriting_key_never_walks_up(db):
    _doc(db, "box", DocType.folder, proto="tbox", attributes={"title": "box title"})
    f = _doc(db, "f1", DocType.folder, parent="box")
    out = effective_node_attributes(db, f)
    assert out["title"]["origin"] == "empty" and out["title"]["value"] in (None, "")


def test_own_value_overrides_and_nothing_inherited_is_stored(db):
    _doc(db, "box", DocType.folder, proto="tbox", attributes={"ref": "EAP1"})
    f = _doc(db, "f1", DocType.folder, parent="box", attributes={"ref": "EAP2"})
    assert effective_node_attributes(db, f)["ref"]["origin"] == "here"
    g = _doc(db, "f2", DocType.folder, parent="box")
    effective_node_attributes(db, g)
    assert db.get(Document, "f2").attributes == {}


def test_nearest_ancestor_wins(db):
    _doc(db, "box", DocType.folder, proto="tbox", attributes={"ref": "far"})
    _doc(db, "mid", DocType.folder, parent="box", attributes={"ref": "near"})
    f = _doc(db, "f1", DocType.folder, parent="mid")
    out = effective_node_attributes(db, f)
    assert (out["ref"]["value"], out["ref"]["from"]) == ("near", "mid")


def test_source_of_a_value_is_reported(db):
    f = _doc(db, "f1", DocType.folder, proto="tfolder", attributes={"title": "x"})
    f.metadata = {"attribute_sources": {"title": {"by": "person", "name": "Ann"}}}
    db.save(f)
    out = effective_node_attributes(db, db.get(Document, "f1"))
    assert out["title"]["source"] == {"by": "person", "name": "Ann"}
