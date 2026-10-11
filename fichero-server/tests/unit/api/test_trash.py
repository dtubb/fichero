"""The Trash, engine half (`docs/contributor_manual/specs/safety/trash.md`, #2077, #5243).

Pins `safety.trash.one-per-project`, `safety.trash.lists-what-and-why`, `safety.trash.put-back`,
`safety.trash.empty-names-moved-items`, `safety.trash.empty-is-one-step` and
`safety.trash.dependants-go-with-their-source`, against a real library database.
"""

from __future__ import annotations

import asyncio

import pytest

import fichero_server.api.routes.claim.claims  # noqa: F401  (registers the actions)
import fichero_server.api.routes.document.documents  # noqa: F401
import fichero_server.api.routes.entity.entities  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.claim.claims import list_claims_impl
from fichero_server.api.routes.document.documents import list_deleted_documents
from fichero_server.api.routes.entity.entities import list_entities_impl
from fichero_server.db.manager import db_manager
from fichero_server.importers.sources_folder import find_sources_folder
from fichero_server.models import ActionAudit, DocType, Document
from fichero_server.models.knowledge import EntityCurationState, KnowledgeClaim, KnowledgeEntity

LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ana", library_path=LIB)


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr("fichero_server.api.change_stream.emit_change", lambda *a, **k: None)


def _doc(db, name, parent=None, kind=DocType.file) -> Document:
    doc = Document(name=name, doc_type=kind, parent_id=parent.id if parent else None)
    db.save(doc)
    return doc


def _delete(db, doc, **extra):
    return registry.invoke(db, "document.delete", {"doc_id": doc.id, **extra}, _ctx())


def _trash(db):
    return asyncio.run(list_deleted_documents(db=db, limit=None, offset=0, readable=lambda rows: (rows, 0)))


def _put_back(db, doc):
    return registry.invoke(db, "document.restore", {"doc_id": doc.id}, _ctx()).result["put_back"]


class TestTheListing:
    def test_each_project_lists_only_its_own_trash(self, db, tmp_path):
        """`safety.trash.one-per-project`: one database per project, so one Trash per project."""
        other_path = tmp_path / "other.fichero"
        other_path.mkdir()
        other = db_manager.get_database(other_path)
        _delete(db, _doc(db, "here.jpg"))
        _delete(other, _doc(other, "there.jpg"))

        assert [item.name for item in _trash(db).items] == ["here.jpg"]
        assert [item.name for item in _trash(other).items] == ["there.jpg"]

    def test_a_trashed_folder_is_listed_once_with_its_count_and_where_it_was(self, db):
        box = _doc(db, "Box 3", kind=DocType.folder)
        folder = _doc(db, "Letters", box, kind=DocType.folder)
        for i in range(3):
            _doc(db, f"page-{i}.jpg", folder)
        _delete(db, folder)

        listing = _trash(db)

        assert listing.total == 1
        item = listing.items[0]
        assert (item.name, item.item_count, item.deleted_by) == ("Letters", 3, "ana")
        assert (item.from_folder_state, item.from_where) == ("live", "Box 3")
        assert (item.reason, item.why) == ("deleted", "Deleted by ana")

    def test_a_page_trashed_on_its_own_before_its_folder_stays_its_own_item(self, db):
        folder = _doc(db, "Letters", kind=DocType.folder)
        early = _doc(db, "early.jpg", folder)
        _doc(db, "later.jpg", folder)
        _delete(db, early)
        _delete(db, folder)

        items = {item.name: item for item in _trash(db).items}

        assert set(items) == {"Letters", "early.jpg"}
        assert items["Letters"].item_count == 1
        assert items["early.jpg"].from_folder_state == "in-trash"

    def test_an_item_a_move_sent_here_says_where_it_went_and_when(self, db):
        """The transfer's soft delete names the target: `moved_to = {project, transfer_id}`."""
        page = _doc(db, "moved.jpg")
        _delete(db, page, moved_to={"project": "Istmina", "transfer_id": "t-1"})

        item = _trash(db).items[0]

        assert (item.reason, item.moved_to_project, item.transfer_id) == ("moved", "Istmina", "t-1")
        assert item.moved_on is not None
        assert item.why == f"Moved to Istmina on {item.moved_on.day} {item.moved_on.strftime('%b %Y')}"

    def test_a_moved_item_put_back_and_deleted_again_is_just_deleted(self, db):
        page = _doc(db, "moved.jpg")
        _delete(db, page, moved_to={"project": "Istmina", "transfer_id": "t-1"})
        _put_back(db, page)
        _delete(db, page)

        assert _trash(db).items[0].reason == "deleted"


class TestPutBack:
    def test_into_its_folder_when_the_folder_is_live(self, db):
        folder = _doc(db, "Letters", kind=DocType.folder)
        page = _doc(db, "p.jpg", folder)
        _delete(db, page)

        answer = _put_back(db, page)

        assert (answer["folder_id"], answer["into_sources"]) == (folder.id, False)
        assert answer["message"] == "Put back in Letters."
        assert db.get(Document, page.id).deleted_at is None

    def test_into_sources_when_its_folder_is_in_the_trash(self, db):
        folder = _doc(db, "Letters", kind=DocType.folder)
        page = _doc(db, "p.jpg", folder)
        _delete(db, page)
        _delete(db, folder)

        answer = _put_back(db, page)

        sources = find_sources_folder(db)
        assert answer["into_sources"] is True
        assert answer["folder_id"] == sources.id
        assert answer["folder_in_trash_id"] == folder.id
        assert answer["message"] == "Put back in Sources: its folder is in the Trash."
        restored = db.get(Document, page.id)
        assert (restored.deleted_at, restored.parent_id) == (None, sources.id)
        assert db.get(Document, folder.id).deleted_at is not None

    def test_into_sources_when_its_folder_is_gone(self, db):
        folder = _doc(db, "Letters", kind=DocType.folder)
        page = _doc(db, "p.jpg", folder)
        _delete(db, page)
        db.delete(db.get(Document, folder.id))

        answer = _put_back(db, page)

        assert answer["message"] == "Put back in Sources: its folder is gone."
        assert db.get(Document, page.id).parent_id == find_sources_folder(db).id

    def test_a_folder_brings_back_what_went_with_it_only(self, db):
        folder = _doc(db, "Letters", kind=DocType.folder)
        early = _doc(db, "early.jpg", folder)
        later = _doc(db, "later.jpg", folder)
        _delete(db, early)
        _delete(db, folder)

        _put_back(db, folder)

        assert db.get(Document, later.id).deleted_at is None
        assert db.get(Document, early.id).deleted_at is not None

    def test_put_back_is_a_step_that_can_be_taken_back(self, db):
        from fichero_server.actions.undo import undo_set

        page = _doc(db, "p.jpg")
        _delete(db, page)
        result = registry.invoke(db, "document.restore", {"doc_id": page.id}, _ctx())

        undo_set(db, [result.audit_id], _ctx())

        assert db.get(Document, page.id).deleted_at is not None


class TestEmptyTrash:
    @pytest.fixture
    def snapshots(self, monkeypatch):
        taken: list[str] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.document.documents.auto_snapshot_before_risky_operation",
            lambda path, **_k: taken.append(path),
        )
        return taken

    def _fill(self, db):
        folder = _doc(db, "Letters", kind=DocType.folder)
        pages = [_doc(db, f"p{i}.jpg", folder) for i in range(2)]
        moved = [_doc(db, f"m{i}.jpg") for i in range(3)]
        keep = _doc(db, "keep.jpg")
        db.save(KnowledgeClaim(text="on a trashed page", source_document_id=pages[0].id))
        db.save(KnowledgeClaim(text="on a live page", source_document_id=keep.id))
        _delete(db, folder)
        for page in moved:
            _delete(db, page, moved_to={"project": "Istmina", "transfer_id": "t-9"})
        return folder, pages, moved, keep

    def test_the_preview_counts_and_names_the_moved_items_and_changes_nothing(self, db, client):
        self._fill(db)

        preview = client.get("/api/documents/trash/empty").json()

        assert (preview["items"], preview["documents"], preview["statements"]) == (4, 6, 1)
        assert preview["sentence"] == "Delete 4 items for good? This cannot be undone."
        [group] = preview["moved"]
        assert (group["project"], group["count"]) == ("Istmina", 3)
        assert group["sentence"].startswith("3 of these were moved to Istmina on ")
        assert group["sentence"].endswith("; emptying makes those moves permanent.")
        assert _trash(db).total == 4

    def test_empty_is_one_recorded_step_after_one_snapshot(self, db, snapshots):
        folder, pages, moved, keep = self._fill(db)

        result = registry.invoke(db, "document.empty_trash", {}, _ctx())

        assert snapshots == [LIB]
        assert len(db.query(ActionAudit, action_name="document.empty_trash")) == 1
        assert result.result["documents"] == 6
        assert result.result["moved"][0]["count"] == 3
        for doc in [folder, *pages, *moved]:
            assert db.get(Document, doc.id) is None
        assert db.get(Document, keep.id) is not None
        assert [c.text for c in db.all(KnowledgeClaim)] == ["on a live page"]
        assert _trash(db).total == 0

    def test_no_snapshot_no_empty(self, db, monkeypatch):
        from fichero_server.db.storage_snapshots import SnapshotRefused
        from fastapi import HTTPException

        def refuse(*_a, **_k):
            raise SnapshotRefused("No room for a snapshot.")

        monkeypatch.setattr(
            "fichero_server.api.routes.document.documents.auto_snapshot_before_risky_operation", refuse
        )
        page = _doc(db, "p.jpg")
        _delete(db, page)

        with pytest.raises(HTTPException) as refused:
            registry.invoke(db, "document.empty_trash", {}, _ctx())

        assert refused.value.status_code == 503
        assert db.get(Document, page.id) is not None


class TestKnowledgeGoesWithItsSource:
    """`safety.trash.dependants-go-with-their-source`: hidden while trashed, back on Put Back,
    pruned on Empty Trash."""

    def _knowledge(self, db):
        page = _doc(db, "trashed.jpg")
        other = _doc(db, "live.jpg")
        only_here = KnowledgeEntity(canonical_name="Only Here", source_document_ids=[page.id])
        verified = KnowledgeEntity(
            canonical_name="Verified Here", source_document_ids=[page.id],
            curation_state=EntityCurationState.verified,
        )
        both = KnowledgeEntity(canonical_name="Both Places", source_document_ids=[page.id])
        for entity in (only_here, verified, both):
            db.save(entity)
        db.save(KnowledgeClaim(text="zebra rests here", source_document_id=page.id, entity_ids=[only_here.id]))
        db.save(KnowledgeClaim(
            text="zebra rests on two", source_document_id=page.id, source_ids=[other.id], entity_ids=[both.id]
        ))
        return page

    def _seen(self, db, client):
        claims = {c.text for c in list_claims_impl(db)}
        entities = {e.canonical_name for e in list_entities_impl(db, limit=100)}
        hits = client.get("/api/kg/search", params={"q": "zebra"}).json()["hits"]
        return claims, entities, {h["title"] for h in hits}

    def test_hidden_then_back_then_pruned(self, db, client, monkeypatch):
        monkeypatch.setattr(
            "fichero_server.api.routes.document.documents.auto_snapshot_before_risky_operation",
            lambda *_a, **_k: None,
        )
        page = self._knowledge(db)
        before = self._seen(db, client)
        assert before[0] == {"zebra rests here", "zebra rests on two"}

        _delete(db, page)
        claims, entities, hits = self._seen(db, client)
        assert claims == {"zebra rests on two"}
        assert entities == {"Verified Here", "Both Places"}
        assert hits == {"zebra rests on two"}
        assert len(db.all(KnowledgeClaim)) == 2  # hidden, not deleted

        _put_back(db, page)
        assert self._seen(db, client) == before

        _delete(db, page)
        registry.invoke(db, "document.empty_trash", {}, _ctx())
        assert db.all(KnowledgeClaim) == []
