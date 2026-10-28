"""`delete.never-deletes-the-parent` (#6175): deleting an item removes exactly it and its descendants, never an ancestor or a
sibling. The Opus review proved the engine walks only DOWN; this pins that direction, through the call the sidebar makes
(`document.delete`), so a later change that deletes upward fails here.
WHY: the owner lost a parent folder when deleting inside it; the cause is in the app (the selection after a delete), but the
engine is the last line, and nothing pinned it."""
from __future__ import annotations

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document


def _folder(db, name, parent=None):
    doc = Document(name=name, doc_type=DocType.folder, parent_id=parent)
    db.save(doc)
    return doc


def test_deleting_a_child_leaves_its_ancestors_and_siblings(db):
    grandparent = _folder(db, "Grandparent")
    parent = _folder(db, "Parent", grandparent.id)
    child = _folder(db, "Child", parent.id)
    grandchild = _folder(db, "Grandchild", child.id)
    sibling = _folder(db, "Sibling", parent.id)
    ctx = ActionContext(actor="test", library_path=str(db.path.parent))

    registry.invoke(db, "document.delete", {"doc_id": child.id}, ctx)

    def gone(doc):
        return db.get(Document, doc.id).deleted_at is not None

    assert gone(child) and gone(grandchild), "the item and its descendants go"
    assert not gone(parent) and not gone(grandparent) and not gone(sibling), "never an ancestor or a sibling"
