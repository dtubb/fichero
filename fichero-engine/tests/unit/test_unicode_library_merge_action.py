from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import pytest

from fichero.actions.registry import ActionContext, registry
from fichero.api.routes import library_registry  # noqa: F401  # register action
from fichero.db import Database
from fichero.knowledge_models import Annotation, AnnotationKind, EntityType, KnowledgeEntity, Note, NoteKind
from fichero.models import ActionAudit, DocType, Document, KnownLibrary


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_file(library: Path, rel_path: str, content: str) -> None:
    target = library / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _save_doc(
    db: Database,
    *,
    doc_id: str,
    name: str,
    rel_path: str | None = None,
    parent_id: str | None = None,
    doc_type: DocType = DocType.file,
    content: str | None = None,
) -> None:
    metadata = {}
    if content is not None:
        metadata["checksum"] = _checksum(content)
    db.save(
        Document(
            id=doc_id,
            name=name,
            parent_id=parent_id,
            doc_type=doc_type,
            path=rel_path,
            metadata=metadata,
            page_content=content or name,
        )
    )


def _save_entity(
    db: Database,
    *,
    entity_id: str,
    canonical_name: str,
    source_document_ids: list[str],
    entity_type: EntityType = EntityType.other,
    parent_id: str | None = None,
    description: str | None = None,
) -> None:
    db.save(
        KnowledgeEntity(
            id=entity_id,
            canonical_name=canonical_name,
            entity_type=entity_type,
            source_document_ids=source_document_ids,
            parent_id=parent_id,
            description=description,
        )
    )


def _save_note(
    db: Database,
    *,
    note_id: str,
    title: str,
    body: str,
    linked_document_ids: list[str] | None = None,
    linked_entity_ids: list[str] | None = None,
    linked_note_ids: list[str] | None = None,
    kind: NoteKind = NoteKind.zettel,
) -> None:
    db.save(
        Note(
            id=note_id,
            title=title,
            body=body,
            kind=kind,
            linked_document_ids=linked_document_ids or [],
            linked_entity_ids=linked_entity_ids or [],
            linked_note_ids=linked_note_ids or [],
        )
    )


def _save_annotation(
    db: Database,
    *,
    annotation_id: str,
    document_id: str,
    kind: AnnotationKind,
    text: str,
    linked_entity_ids: list[str] | None = None,
    linked_note_ids: list[str] | None = None,
    char_start: int | None = None,
    char_end: int | None = None,
) -> None:
    db.save(
        Annotation(
            id=annotation_id,
            document_id=document_id,
            kind=kind,
            text=text,
            linked_entity_ids=linked_entity_ids or [],
            linked_note_ids=linked_note_ids or [],
            char_start=char_start,
            char_end=char_end,
        )
    )


def _make_library(path: Path, spec: list[dict]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    db = Database(path / "fichero.duckdb")
    try:
        for item in spec:
            if item["kind"] == "folder":
                _save_doc(
                    db,
                    doc_id=item["id"],
                    name=item["name"],
                    parent_id=item.get("parent_id"),
                    doc_type=DocType.folder,
                )
                continue
            _write_file(path, item["rel_path"], item["content"])
            _save_doc(
                db,
                doc_id=item["id"],
                name=item["name"],
                rel_path=item["rel_path"],
                parent_id=item.get("parent_id"),
                content=item["content"],
            )
    finally:
        db.close()


def _register(global_db: Database, path: Path) -> None:
    global_db.save(
        KnownLibrary(
            path=unicodedata.normalize("NFC", str(path.resolve())),
            name=path.name,
        )
    )


def _ctx(library_path: str | None = None) -> ActionContext:
    return ActionContext(actor="ui", library_path=library_path)


@pytest.fixture
def global_db(tmp_path, monkeypatch) -> Database:
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    db = Database(tmp_path / "global.fichero" / "fichero.duckdb")
    try:
        yield db
    finally:
        db.close()


def test_unicode_merge_action_merges_synthetic_pair_and_writes_audit(tmp_path, global_db) -> None:
    left = tmp_path / "left" / unicodedata.normalize("NFD", "Chocó.fichero")
    right = tmp_path / "right" / unicodedata.normalize("NFC", "Chocó.fichero")
    _make_library(
        right,
        [
            {"kind": "file", "id": "win-same", "name": "same.txt", "rel_path": "files/same.txt", "content": "same"},
            {"kind": "file", "id": "win-shared", "name": "shared.txt", "rel_path": "files/shared.txt", "content": "winner"},
        ],
    )
    _make_library(
        left,
        [
            {"kind": "folder", "id": "loser-folder", "name": "Loser Folder"},
            {"kind": "file", "id": "lose-same", "name": "same.txt", "rel_path": "files/same.txt", "content": "same"},
            {"kind": "file", "id": "lose-shared", "name": "shared.txt", "rel_path": "files/shared.txt", "content": "loser"},
            {
                "kind": "file",
                "id": "lose-only",
                "name": "only.txt",
                "rel_path": "files/only.txt",
                "parent_id": "loser-folder",
                "content": "only-left",
            },
        ],
    )
    winner_db = Database(right / "fichero.duckdb")
    try:
        _save_entity(
            winner_db,
            entity_id="win-entity-same",
            canonical_name="Exact Person",
            entity_type=EntityType.person,
            source_document_ids=["win-same"],
        )
        _save_entity(
            winner_db,
            entity_id="win-entity-shared",
            canonical_name="Shared Place",
            entity_type=EntityType.location,
            source_document_ids=["win-shared"],
            description="winner",
        )
        _save_note(
            winner_db,
            note_id="win-note-same",
            title="Exact note",
            body="same body",
            linked_document_ids=["win-same"],
            kind=NoteKind.reference,
        )
        _save_note(
            winner_db,
            note_id="win-note-shared",
            title="Shared note",
            body="winner note",
            linked_document_ids=["win-shared"],
        )
        _save_annotation(
            winner_db,
            annotation_id="win-ann-same",
            document_id="win-same",
            kind=AnnotationKind.highlight,
            text="same highlight",
            char_start=1,
            char_end=4,
        )
        _save_annotation(
            winner_db,
            annotation_id="win-ann-shared",
            document_id="win-shared",
            kind=AnnotationKind.note,
            text="winner annotation",
        )
    finally:
        winner_db.close()
    loser_db = Database(left / "fichero.duckdb")
    try:
        _save_entity(
            loser_db,
            entity_id="lose-entity-same",
            canonical_name="Exact Person",
            entity_type=EntityType.person,
            source_document_ids=["lose-same"],
        )
        _save_entity(
            loser_db,
            entity_id="lose-entity-shared",
            canonical_name="Shared Place",
            entity_type=EntityType.location,
            source_document_ids=["lose-shared"],
            description="loser",
        )
        _save_entity(
            loser_db,
            entity_id="lose-entity-only-parent",
            canonical_name="Folder Person",
            entity_type=EntityType.person,
            source_document_ids=["lose-only"],
            parent_id="loser-folder",
        )
        _save_entity(
            loser_db,
            entity_id="lose-entity-only-child",
            canonical_name="Folder Person Child",
            entity_type=EntityType.person,
            source_document_ids=["lose-only"],
            parent_id="loser-folder",
        )
        _save_note(
            loser_db,
            note_id="lose-note-same",
            title="Exact note",
            body="same body",
            linked_document_ids=["lose-same"],
            kind=NoteKind.reference,
        )
        _save_note(
            loser_db,
            note_id="lose-note-shared",
            title="Shared note",
            body="loser note",
            linked_document_ids=["lose-shared"],
        )
        _save_note(
            loser_db,
            note_id="lose-note-only",
            title="Only note",
            body="loser only note",
            linked_document_ids=["lose-only"],
            linked_entity_ids=["lose-entity-only-child"],
        )
        _save_annotation(
            loser_db,
            annotation_id="lose-ann-same",
            document_id="lose-same",
            kind=AnnotationKind.highlight,
            text="same highlight",
            char_start=1,
            char_end=4,
        )
        _save_annotation(
            loser_db,
            annotation_id="lose-ann-shared",
            document_id="lose-shared",
            kind=AnnotationKind.note,
            text="loser annotation",
        )
        _save_annotation(
            loser_db,
            annotation_id="lose-ann-only",
            document_id="lose-only",
            kind=AnnotationKind.note,
            text="loser only annotation",
            linked_entity_ids=["lose-entity-only-child"],
            linked_note_ids=["lose-note-only"],
        )
    finally:
        loser_db.close()
    _register(global_db, left)
    _register(global_db, right)

    result = registry.invoke(
        global_db,
        "library.unicode_merge",
        {"left_path": str(left), "right_path": str(right)},
        _ctx(str(right)),
    )

    assert result.result["status"] == "merged"
    assert result.result["winner_path"] == str(right)
    assert Path(result.result["journal_path"]).exists()
    assert not left.exists()
    assert Path(result.result["loser_renamed_path"]).exists()
    assert [row.path for row in global_db.all(KnownLibrary)] == [
        unicodedata.normalize("NFC", str(right.resolve()))
    ]

    winner_db = Database(right / "fichero.duckdb")
    try:
        docs = winner_db.all(Document)
        file_docs = [doc for doc in docs if doc.doc_type == DocType.file]
        paths = sorted(doc.path for doc in file_docs if doc.path)
        assert paths.count("files/same.txt") == 1
        assert "files/shared.txt" in paths
        assert any(path.startswith("files/shared.from-") for path in paths)
        loser_folder = next(doc for doc in docs if doc.name == "Loser Folder")
        copied_only = next(doc for doc in docs if doc.name == "only.txt")
        assert copied_only.parent_id == loser_folder.id
        assert copied_only.path == "files/only.txt"

        entities = winner_db.all(KnowledgeEntity)
        exact_entities = [entity for entity in entities if entity.canonical_name == "Exact Person"]
        assert len(exact_entities) == 1
        shared_entities = [entity for entity in entities if entity.canonical_name == "Shared Place"]
        assert len(shared_entities) == 2
        child_entity = next(entity for entity in entities if entity.canonical_name == "Folder Person Child")
        parent_entity = next(entity for entity in entities if entity.canonical_name == "Folder Person")
        assert child_entity.parent_id == loser_folder.id
        assert parent_entity.parent_id == loser_folder.id
        assert child_entity.source_document_ids == [copied_only.id]

        notes = winner_db.all(Note)
        exact_notes = [note for note in notes if note.title == "Exact note"]
        assert len(exact_notes) == 1
        shared_notes = [note for note in notes if note.title == "Shared note"]
        assert len(shared_notes) == 2
        copied_note = next(note for note in notes if note.title == "Only note")
        assert copied_note.linked_document_ids == [copied_only.id]
        assert copied_note.linked_entity_ids == [child_entity.id]

        annotations = winner_db.all(Annotation)
        exact_annotations = [ann for ann in annotations if ann.text == "same highlight"]
        assert len(exact_annotations) == 1
        shared_annotations = [ann for ann in annotations if ann.text in {"winner annotation", "loser annotation"}]
        assert len(shared_annotations) == 2
        copied_annotation = next(ann for ann in annotations if ann.text == "loser only annotation")
        assert copied_annotation.document_id == copied_only.id
        assert copied_annotation.linked_entity_ids == [child_entity.id]
        assert copied_annotation.linked_note_ids == [copied_note.id]
    finally:
        winner_db.close()

    audit = global_db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.action_name == "library.unicode_merge"
    assert audit.after["deferred_follow_up_issue"] == 3094
    journal = json.loads(Path(result.result["journal_path"]).read_text(encoding="utf-8"))
    doc_dispositions = {row["source_document_id"]: row["disposition"] for row in journal["dispositions"] if row.get("source_document_id")}
    entity_dispositions = {row["source_entity_id"]: row["disposition"] for row in journal["dispositions"] if row.get("source_entity_id")}
    note_dispositions = {row["source_note_id"]: row["disposition"] for row in journal["dispositions"] if row.get("source_note_id")}
    annotation_dispositions = {row["source_annotation_id"]: row["disposition"] for row in journal["dispositions"] if row.get("source_annotation_id")}
    assert doc_dispositions["lose-same"] == "dedupe_identical"
    assert doc_dispositions["lose-shared"] == "keep_both_conflicting_path"
    assert doc_dispositions["lose-only"] == "copy_with_file"
    assert entity_dispositions["lose-entity-same"] == "dedupe_identical"
    assert entity_dispositions["lose-entity-shared"] == "copy_entity"
    assert entity_dispositions["lose-entity-only-child"] == "copy_entity"
    assert note_dispositions["lose-note-same"] == "dedupe_identical"
    assert note_dispositions["lose-note-shared"] == "copy_note"
    assert note_dispositions["lose-note-only"] == "copy_note"
    assert annotation_dispositions["lose-ann-same"] == "dedupe_identical"
    assert annotation_dispositions["lose-ann-shared"] == "copy_annotation"
    assert annotation_dispositions["lose-ann-only"] == "copy_annotation"


def test_unicode_merge_action_is_idempotent_on_rerun(tmp_path, global_db) -> None:
    left = tmp_path / "left" / unicodedata.normalize("NFD", "Chocó.fichero")
    right = tmp_path / "right" / unicodedata.normalize("NFC", "Chocó.fichero")
    _make_library(right, [])
    _make_library(left, [])
    _register(global_db, left)
    _register(global_db, right)

    first = registry.invoke(
        global_db,
        "library.unicode_merge",
        {"left_path": str(left), "right_path": str(right)},
        _ctx(str(right)),
    )
    second = registry.invoke(
        global_db,
        "library.unicode_merge",
        {"left_path": str(left), "right_path": str(right)},
        _ctx(str(right)),
    )

    assert first.result["status"] == "merged"
    assert second.result["status"] == "noop"


def test_unicode_merge_action_aborts_on_snapshot_failure(tmp_path, global_db, monkeypatch) -> None:
    from fichero.api.routes import library_registry as registry_routes

    left = tmp_path / "left" / unicodedata.normalize("NFD", "Chocó.fichero")
    right = tmp_path / "right" / unicodedata.normalize("NFC", "Chocó.fichero")
    _make_library(right, [])
    _make_library(left, [])
    _register(global_db, left)
    _register(global_db, right)
    calls: list[str] = []

    real_snapshot = registry_routes.snapshot_library

    def snapshot_spy(path: str, **kwargs):
        calls.append(path)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real_snapshot(path, **kwargs)

    monkeypatch.setattr(registry_routes, "snapshot_library", snapshot_spy)

    with pytest.raises(RuntimeError, match="boom"):
        registry.invoke(
            global_db,
            "library.unicode_merge",
            {"left_path": str(left), "right_path": str(right)},
            _ctx(str(right)),
        )

    assert left.exists()
    assert right.exists()
    assert len(global_db.all(KnownLibrary)) == 2
