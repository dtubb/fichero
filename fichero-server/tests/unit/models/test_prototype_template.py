"""proto.template.columns-are-the-prototype (attributes-and-prototypes.md Step 1.3)."""

import pytest

from fichero_server.db import Database
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
from fichero_server.models.prototype_template import apply_choice, template_for_prototype, template_for_rows


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.duckdb")

    def proto(key, attrs, parent=None, label=None):
        d.save(ClassificationValue(dimension=ClassificationDimension.document_prototype, key=key,
                                   label=label or key, parent_key=parent, attributes=attrs))

    proto("tbase", {
        "name": {"type": "text", "order": 1, "source": "folder.name", "labels": {"es": "Nombre", "en": "Name"}},
        "title": {"type": "text", "order": 2, "labels": {"es": "Título", "en": "Title"}, "help": {"es": "Escriba"}},
        "pages": "page_kind",
    })
    proto("page_kind", {})
    proto("tletter", {"sender": {"type": "text", "order": 3}}, parent="tbase")
    proto("tcourt", {"judge": {"type": "text", "order": 3}}, parent="tbase")
    yield d
    d.close()


def _folder(db, id, proto=None, attrs=None):
    doc = Document(id=id, name=id, path=f"/{id}", doc_type=DocType.folder, prototype_key=proto, attributes=attrs or {})
    db.save(doc)
    return doc


def test_template_is_the_effective_declarations_in_order(db):
    cols = template_for_prototype(db, "tletter")
    assert [c.key for c in cols] == ["name", "title", "sender"]
    assert cols[0].kind == "computed" and cols[0].source == "folder.name"
    assert cols[1].kind == "attribute" and cols[1].labels == {"es": "Título", "en": "Title"}
    assert cols[1].help == {"es": "Escriba"}
    assert "pages" not in [c.key for c in cols]  # a level default is not a column


def test_same_prototype_rows_give_its_columns(db):
    rows = [_folder(db, "a", "tletter"), _folder(db, "b", "tletter")]
    t = template_for_rows(db, rows)
    assert [c.key for c in t.columns] == ["name", "title", "sender"] and not t.mixed


def test_mixed_kinds_show_the_union_with_shared_parent_columns_once(db):
    rows = [_folder(db, "a", "tletter"), _folder(db, "b", "tcourt")]
    t = template_for_rows(db, rows)
    assert [c.key for c in t.columns] == ["name", "title", "sender", "judge"] and t.mixed
    assert t.columns[3].group == "tcourt" and t.columns[2].group == "tletter"


def test_union_follows_first_seen_row_order(db):
    t = template_for_rows(db, [_folder(db, "b", "tcourt"), _folder(db, "a", "tletter")])
    assert [c.key for c in t.columns] == ["name", "title", "judge", "sender"]


def test_rows_with_no_prototype_get_every_catalogue_key_alphabetically(db):
    rows = [_folder(db, "a", None, {"catalogue_title": "x", "catalogue_date": "y", "other": 1}),
            _folder(db, "b", None, {"catalogue_abc": "z"})]
    t = template_for_rows(db, rows)
    assert [c.key for c in t.columns] == ["catalogue_abc", "catalogue_date", "catalogue_title"]


def test_inherited_kind_counts_as_the_rows_prototype(db):
    db.save(ClassificationValue(dimension=ClassificationDimension.document_prototype, key="tbox",
                                label="box", attributes={"subfolders": "tletter"}))
    _folder(db, "tbox", "tbox")
    child = Document(id="c", name="c", path="/c", doc_type=DocType.folder, parent_id="tbox")
    db.save(child)
    assert [c.key for c in template_for_rows(db, [child]).columns] == ["name", "title", "sender"]


def test_choice_hides_columns_or_narrows_to_one_kind(db):
    rows = [_folder(db, "a", "tletter"), _folder(db, "b", "tcourt")]
    t = template_for_rows(db, rows)
    assert [c.key for c in apply_choice(db, t, {"hide": ["title"]}).columns] == ["name", "sender", "judge"]
    assert [c.key for c in apply_choice(db, t, {"only_kind": "tcourt"}).columns] == ["name", "title", "judge"]
    assert apply_choice(db, t, None).columns == t.columns


def test_hidden_declaration_leaves_the_inherited_column_out(db):
    db.save(ClassificationValue(dimension=ClassificationDimension.document_prototype, key="tslim",
                                label="tslim", parent_key="tletter",
                                attributes={"title": {"type": "text", "hidden": True}}))
    assert [c.key for c in template_for_prototype(db, "tslim")] == ["name", "sender"]
