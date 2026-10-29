"""proto.kind.own-and-inherited-by-level (attributes-and-prototypes.md Step 1.2).

A node's effective prototype: its own key, else the first ancestor's effective prototype that
declares a default for the node's level, else none; a node's own kind restarts the chain beneath it.
"""

import pytest

from fichero_server.db import Database
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
from fichero_server.models.node_prototypes import node_level, resolve_node_prototype


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.duckdb")
    for key, attrs, parent in [
        ("eap_box", {"subfolders": "eap_folder"}, None),
        ("eap_folder", {"pages": "eap_page"}, None),
        ("eap_page", {}, None),
        ("bundle", {"pages": "letter_page"}, "eap_folder"),
        ("letter_page", {}, None),
        ("map", {}, None),
    ]:
        d.save(ClassificationValue(dimension=ClassificationDimension.document_prototype,
                                   key=key, label=key, parent_key=parent, attributes=attrs))
    yield d
    d.close()


def _doc(db, id, doc_type, parent=None, proto=None, attributes=None):
    doc = Document(id=id, name=id, path=f"/{id}", doc_type=doc_type, parent_id=parent,
                   prototype_key=proto, attributes=attributes or {})
    db.save(doc)
    return doc


def test_levels_by_doc_type():
    assert node_level(Document(name="a", path="/a", doc_type=DocType.folder)) == "subfolders"
    assert node_level(Document(name="a", path="/a", doc_type=DocType.file)) == "pages"
    assert node_level(Document(name="a", path="/a", doc_type=DocType.page)) == "pages"
    assert node_level(Document(name="a", path="/a", doc_type=DocType.chunk)) == "regions"


def test_own_kind_wins_and_says_set_here(db):
    box = _doc(db, "box", DocType.folder, proto="eap_box")
    res = resolve_node_prototype(db, box)
    assert (res.key, res.rule, res.from_id) == ("eap_box", "own", None)


def test_subfolder_inherits_from_box_at_any_depth(db):
    _doc(db, "box", DocType.folder, proto="eap_box")
    _doc(db, "f1", DocType.folder, parent="box")
    deep = _doc(db, "deep", DocType.folder, parent="f1")
    res = resolve_node_prototype(db, db.get(Document, "f1"))
    assert (res.key, res.rule, res.from_id) == ("eap_folder", "inherited", "box")
    # `f1` has no own kind but now carries an effective one; `deep` walks up past it to the box.
    assert resolve_node_prototype(db, deep).key == "eap_folder"


def test_page_inherits_from_nearest_ancestor_that_declares_pages(db):
    _doc(db, "box", DocType.folder, proto="eap_box")
    _doc(db, "f1", DocType.folder, parent="box")
    page = _doc(db, "p1", DocType.page, parent="f1")
    res = resolve_node_prototype(db, page)
    assert (res.key, res.rule, res.from_id) == ("eap_page", "inherited", "f1")


def test_own_kind_restarts_the_chain_beneath(db):
    _doc(db, "box", DocType.folder, proto="eap_box")
    _doc(db, "f1", DocType.folder, parent="box", proto="bundle")
    page = _doc(db, "p1", DocType.page, parent="f1")
    assert resolve_node_prototype(db, page).key == "letter_page"  # not the box's page kind


def test_a_page_with_its_own_kind_keeps_it(db):
    _doc(db, "box", DocType.folder, proto="eap_box")
    _doc(db, "f1", DocType.folder, parent="box")
    page = _doc(db, "p1", DocType.page, parent="f1", proto="map")
    assert resolve_node_prototype(db, page).key == "map"


def test_clearing_own_kind_inherits_again(db):
    _doc(db, "box", DocType.folder, proto="eap_box")
    f = _doc(db, "f1", DocType.folder, parent="box", proto="bundle")
    assert resolve_node_prototype(db, f).rule == "own"
    f.prototype_key = None
    db.save(f)
    assert resolve_node_prototype(db, db.get(Document, "f1")).key == "eap_folder"


def test_nothing_declared_is_none(db):
    f = _doc(db, "lone", DocType.folder)
    res = resolve_node_prototype(db, f)
    assert (res.key, res.rule) == (None, "none")


def test_parent_cycle_ends_the_walk(db):
    a = _doc(db, "a", DocType.folder, parent="b")
    _doc(db, "b", DocType.folder, parent="a")
    assert resolve_node_prototype(db, a).rule == "none"
