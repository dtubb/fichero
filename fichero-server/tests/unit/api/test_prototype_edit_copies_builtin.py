"""proto.template.edit-copies-a-builtin: a column change on a built-in lands on a project-owned child (attributes-and-prototypes.md §3)."""
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, DocType, Document
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
from fichero_server.models.prototype_template import template_for_rows

CTX = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
DIM = ClassificationDimension.document_prototype
TITLE = {"type": "text", "order": 1, "labels": {"es": "Título"}}


def _proto(db, key, attrs, parent=None, builtin=True):
    v = ClassificationValue(dimension=DIM, key=key, label=key, parent_key=parent, attributes=attrs, is_builtin=builtin)
    db.save(v)
    return v


def _get(db, key):
    return next(v for v in db.query(ClassificationValue, dimension=DIM) if v.key == key)


def _patch(db, value, attrs):
    return registry.invoke(db, "classification.patch", {"value_id": value.id, "attributes": attrs}, CTX)


def _undo(db, audit_id):
    audit = db.get(ActionAudit, audit_id)
    name, params = registry.get(audit.action_name).invert(audit.before, audit.after, CTX)
    registry.invoke(db, name, params, CTX)


def _world(db):
    """A built-in folder kind, a built-in box naming it for the folders beneath, a box carrying the box kind."""
    kind = _proto(db, "tkind", {"title": TITLE})
    _proto(db, "tbox", {"subfolders": "tkind"})
    box = Document(id="box", name="Box", path="/box", doc_type=DocType.folder, prototype_key="tbox")
    row = Document(id="row", name="Row", path="/row", doc_type=DocType.folder, parent_id="box")
    own = Document(id="own", name="Own", path="/own", doc_type=DocType.folder, prototype_key="tkind")
    for d in (box, row, own):
        db.save(d)
    return kind


def test_a_change_on_a_builtin_makes_a_child_assigns_it_and_leaves_the_builtin(db):
    kind = _world(db)
    new = {**kind.attributes, "extra": {"type": "text", "order": 2, "labels": {"es": "Extra"}}}
    result = _patch(db, kind, new)
    assert _get(db, "tkind").attributes == {"title": TITLE}  # the built-in is never edited
    child = db.get(Document, "own").prototype_key
    assert child.startswith("tkind-copy") and _get(db, child).parent_key == "tkind" and not _get(db, child).is_builtin
    assert set(_get(db, child).attributes) == {"title", "extra"}
    # the node that carried the kind, and the box that names it for the rows beneath: the rows follow, no assignment per folder
    box_kind = db.get(Document, "box").prototype_key
    assert box_kind.startswith("tbox-copy")
    cols = [c.key for c in template_for_rows(db, [db.get(Document, "row")]).columns]
    assert "extra" in cols and "title" in cols
    assert db.get(Document, "own").prototype_key == child and result.audit_id


def test_a_later_change_patches_the_child_and_makes_no_second_copy(db):
    kind = _world(db)
    _patch(db, kind, {"title": TITLE, "extra": {"type": "text", "order": 2}})
    child = _get(db, db.get(Document, "own").prototype_key)
    before = len(db.query(ClassificationValue, dimension=DIM))
    _patch(db, child, {**child.attributes, "more": {"type": "text", "order": 3}})
    assert len(db.query(ClassificationValue, dimension=DIM)) == before
    assert "more" in _get(db, child.key).attributes


def test_undo_takes_back_the_copy_the_assignment_and_the_change_together(db):
    kind = _world(db)
    result = _patch(db, kind, {"title": TITLE, "extra": {"type": "text", "order": 2}})
    keys = lambda: {v.key for v in db.query(ClassificationValue, dimension=DIM)}  # noqa: E731 -- the seeded built-ins are there too
    before = keys() - {k for k in keys() if "-copy" in k}
    assert len(keys() - before) == 2  # a copy of the kind and of the box
    _undo(db, result.audit_id)
    assert keys() == before
    assert db.get(Document, "own").prototype_key == "tkind" and db.get(Document, "box").prototype_key == "tbox"


def test_a_change_to_a_non_builtin_is_the_plain_patch(db):
    own = _proto(db, "tmine", {"title": TITLE}, builtin=False)
    before = len(db.query(ClassificationValue, dimension=DIM))
    _patch(db, own, {"title": TITLE, "x": {"type": "text"}})
    assert len(db.query(ClassificationValue, dimension=DIM)) == before and "x" in _get(db, "tmine").attributes
