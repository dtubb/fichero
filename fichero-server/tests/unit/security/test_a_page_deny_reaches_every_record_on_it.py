"""A deny on a page reaches every record that belongs to it, named by its own id (#5177).

WHY: an editor denied a page could still change records on it by naming them -- a reading, a
reading order or one of its entries, an agent note, a citation, an annotation, an interpretation, a
note, a typed link, a library link -- because only the document itself (and the segment family)
resolved to the page. Each of these goes through the REAL action by name (the app's
`/api/actions/invoke`) with ONLY the record's own id in the params, so the 403 can come from nothing
but the resolver; the same editor on an allowed page gets 200, so the 403 is the deny and not a
broken call. If this regresses, a denied page's record can be withdrawn by id again.
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import AgentNote, AgentNoteActor, AgentNoteSourceAnchor, ContentRepresentation, DocType, Document
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.hermeneutics import Interpretation
from fichero_server.models.knowledge import Annotation, DocumentCitation, LibraryItemLink, Note, ProvenanceKind
from fichero_server.models.reading_orders import ReadingOrder, ReadingOrderEntry
from fichero_server.models.typed_links import TypedLink
from tests.unit.api.test_segments_multiuser_access import (  # noqa: F401  (fixtures)
    _grant_role,
    _make_doc,
    _make_pass,
    _make_segment,
    _override,
    multiuser_client,
    users,
)


def _segment(db, doc):
    return _make_segment(db, document_id=doc.id, pass_id=_make_pass(db, doc.id).id, rect=[0.1, 0.1, 0.2, 0.05])


def _reading(db, doc):
    row = ContentRepresentation(document_id=doc.id, kind="transcription", content="x",
                                source_anchor=SourceAnchor(document_id=doc.id))
    db.save(row)
    return "representation.retract", {"representation_id": row.id}


def _order(db, doc):
    seg = _segment(db, doc)
    row = ReadingOrder(document_id=doc.id, pass_id=seg.pass_id, provenance_kind=ProvenanceKind.human, name="mine")
    db.save(row)
    return "reading_order.delete", {"order_id": row.id}


def _entry(db, doc):
    seg = _segment(db, doc)
    order = ReadingOrder(document_id=doc.id, pass_id=seg.pass_id, provenance_kind=ProvenanceKind.human, name="mine")
    db.save(order)
    row = ReadingOrderEntry(order_id=order.id, segment_id=seg.id, position=1.0)
    db.save(row)
    return "reading_order.remove", {"entry_id": row.id}


def _agent_note(db, doc):
    row = AgentNote(body="remember this", source_anchor=AgentNoteSourceAnchor(document_id=doc.id),
                    actor=AgentNoteActor(actor_id="agent"))
    db.save(row)
    return "agent_memory.delete", {"note_id": row.id}


def _citation(db, doc):
    row = DocumentCitation(source_document_id=doc.id, target_citation_text="Smith 1901")
    db.save(row)
    return "citation.delete", {"citation_id": row.id}


def _annotation(db, doc):
    row = Annotation(kind="highlight", document_id=doc.id)
    db.save(row)
    return "annotation.delete", {"annotation_id": row.id}


def _note(db, doc):
    page = Document(name="page 1", doc_type=DocType.page, parent_id=doc.id)   # a note hangs on a page
    db.save(page)
    row = Note(page_id=page.id, body="a note")
    db.save(row)
    return "note.delete", {"note_id": row.id}


def _typed_link(db, doc):
    a, b = _segment(db, doc), _segment(db, doc)
    row = TypedLink(from_id=a.id, to_id=b.id, link_type="glosses", provenance_kind=ProvenanceKind.human)
    db.save(row)
    return "typed_link.delete", {"link_id": row.id}


def _library_link(db, doc):
    row = LibraryItemLink(source_id="entity-1", source_type="entity", target_id=doc.id,
                          target_type="document", relation_type="cites")
    db.save(row)
    return "library-link.delete", {"link_id": row.id}


def _interpretation(db, doc):
    from fichero_server.models.hermeneutics import InterpretiveFramework

    framework = InterpretiveFramework(name="a lens", framework_type="thematic", description="a lens")
    db.save(framework)
    row = Interpretation(framework_id=framework.id, interpretation_text="read so", act="reading", document_id=doc.id)
    db.save(row)
    return "interpretation.update", {"interpretation_id": row.id, "interpretation_text": "read otherwise"}


def _rights_on_page(db, doc):
    from fichero_server.models.rights import RightsRecord

    row = RightsRecord(target_kind="document", target_id=doc.id)
    db.save(row)
    return "rights.withdraw", {"record_id": row.id}


def _rights_on_segment(db, doc):
    from fichero_server.models.rights import RightsRecord

    row = RightsRecord(target_kind="segment", target_id=_segment(db, doc).id)
    db.save(row)
    return "rights.withdraw", {"record_id": row.id}


KINDS = {
    "reading": _reading, "reading order": _order, "reading-order entry": _entry, "agent note": _agent_note,
    "citation": _citation, "annotation": _annotation, "note": _note, "typed link": _typed_link,
    "library link": _library_link, "interpretation": _interpretation,
    "rights record on the page": _rights_on_page, "rights record on a segment": _rights_on_segment,
}


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_an_editor_denied_the_page_cannot_change_its_record(kind, multiuser_client, app_db, users, db):
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")
    denied, allowed = _make_doc(db, "denied.jpg"), _make_doc(db, "allowed.jpg")
    _override(app_db, users.editor, library_path, denied.id, "deny")
    for doc, expected in ((denied, 403), (allowed, 200)):
        name, params = KINDS[kind](db, doc)
        response = client.post("/api/actions/invoke", headers=login("editor"), json={"name": name, "params": params})
        assert response.status_code == expected, (kind, doc.name, response.text[:300])


def test_a_rights_record_on_the_library_is_not_the_pages_to_deny(multiuser_client, app_db, users, db):
    """Archive's semantics (#5177): a record on the LIBRARY belongs to no document, so a deny on
    some page does not reach it -- and it must not fail closed either (the editor may withdraw it)."""
    from fichero_server.models.rights import RightsRecord

    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")
    denied = _make_doc(db, "denied.jpg")
    _override(app_db, users.editor, library_path, denied.id, "deny")
    row = RightsRecord(target_kind="library", target_id="library")
    db.save(row)
    response = client.post("/api/actions/invoke", headers=login("editor"),
                           json={"name": "rights.withdraw", "params": {"record_id": row.id}})
    assert response.status_code == 200, response.text[:300]
