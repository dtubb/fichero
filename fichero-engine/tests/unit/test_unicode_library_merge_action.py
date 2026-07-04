from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import pytest

from fichero.actions.registry import ActionContext, registry
from fichero.api.routes import library_registry  # noqa: F401  # register action
from fichero.db import Database
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
    finally:
        winner_db.close()

    audit = global_db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.action_name == "library.unicode_merge"
    assert audit.after["deferred_follow_up_issue"] == 3094
    journal = json.loads(Path(result.result["journal_path"]).read_text(encoding="utf-8"))
    dispositions = {row["source_document_id"]: row["disposition"] for row in journal["dispositions"]}
    assert dispositions["lose-same"] == "dedupe_identical"
    assert dispositions["lose-shared"] == "keep_both_conflicting_path"
    assert dispositions["lose-only"] == "copy_with_file"


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
