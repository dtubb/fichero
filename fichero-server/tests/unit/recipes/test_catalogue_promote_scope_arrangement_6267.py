"""The catalogue is a folder's own record, all of it, once (#6267, `catalogue.scope-and-arrangement-are-attributes`,
`catalogue.promote-is-undoable-and-idempotent`): Scope and content and Arrangement are attributes too, and
`folder.promote_catalogue` brings a folder described earlier up to date with no model call."""
from __future__ import annotations

import fichero_server.api.routes.document.documents  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.actions.undo import undo_set
from fichero_server.models import Artifact, DocType, Document
from fichero_server.recipes import catalogue_step

OLD = "Title: Wheat letters.\nDates: 1776.\nDescription: A short paragraph."
NEW = OLD + "\nScope and content: Letters about wheat.\nArrangement: By date, then by sender."
CTX = ActionContext(actor="ui", library_path="")


def test_scope_and_arrangement_are_parsed_as_attributes():
    got = catalogue_step.parse_fields(NEW)
    assert got["catalogue_scope_content"] == "Letters about wheat."
    assert got["catalogue_arrangement"] == "By date, then by sender."
    assert "Short paragraph" not in str(got)  # Description is still prose only


def _described_folder(db, text=OLD):
    box = Document(name="Box 1", doc_type=DocType.folder)
    db.save(box)
    art = Artifact(document_id=box.id, artifact_type=catalogue_step.ARTIFACT_TYPE, content=text, provider="p", model="m")
    db.save(art)
    catalogue_step.put_in_content(db, box.id, text, art.id)
    catalogue_step.put_in_attributes(db, box.id, text, art.id, run_id="r1", provider="p", model="m")
    return box.id, art


def _promote(db, **params):
    return registry.invoke(db, "folder.promote_catalogue", params, CTX)


def test_promote_gives_an_earlier_folder_the_new_keys_and_is_idempotent(db):
    box, art = _described_folder(db)
    art.content = NEW  # the saved description now carries the two fields; the folder's attributes do not
    db.save(art)
    assert "catalogue_scope_content" not in (db.get(Document, box).attributes or {})
    assert _promote(db).result["promoted"] == [box]
    folder = db.get(Document, box)
    assert folder.attributes["catalogue_scope_content"] == "Letters about wheat."
    assert folder.attributes["catalogue_title"] == "Wheat letters." and folder.page_content == NEW
    assert _promote(db, folder_id=box).result["promoted"] == []  # nothing left to change


def test_promote_is_undone_to_what_the_folder_held(db):
    box, art = _described_folder(db)
    art.content = NEW
    db.save(art)
    was = db.get(Document, box)
    before = (was.page_content, dict(was.attributes))
    audit_id = _promote(db, folder_id=box).audit_id
    undo_set(db, [audit_id], CTX)
    folder = db.get(Document, box)
    assert (folder.page_content, dict(folder.attributes)) == before
