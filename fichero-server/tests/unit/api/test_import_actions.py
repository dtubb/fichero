"""Unit tests for the IMPORT-domain audited actions (EPIC #1848 / #2014).

The import sweep registers every mutating import endpoint as an action that
WRAPS the route's proven ``import_*_impl`` (iterate-not-replace) and runs
through ``registry.invoke`` — the single audited write path. These tests drive
each action via the registry (the same path chat tools / App Intents / the
``/api/actions/invoke`` route use) and, per the project test bar
([[would-more-tests-catch-more-issues]]), assert MORE than the happy path:

  (a) the effect lands AND an ActionAudit row is written (actor/target_ids/
      before/after correct);
  (b) undo reverses it (for undoable single-doc imports) and undo-of-undo is
      sane;
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong (missing/non-file
      path, file-as-folder, empty folder no-op, dry-run no-op, unnamed xlsx
      row skipped);
  (e) the emit fires with the right type + ids (emit_change monkeypatched at
      the SOURCE module, mirroring test_action_registry).

The underlying ``fichero_server.importers.ingest.ingest_file`` / ``ingest_folder`` and the xlsx
reader are monkeypatched so these tests exercise the AUDIT/EMIT/UNDO plumbing
without invoking the real loaders/embedding pipeline (RAM economy — the MANAGER
runs the full suite; this worker only writes the tests).

Importing the ingest + documents route modules registers the import.* +
document.* actions at import time.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

# Importing the route modules registers the import.* (+ the document.* used by
# undo) actions at import time.
import fichero_server.api.routes.ingest  # noqa: F401
import fichero_server.api.routes.document.documents  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, Document


def _ctx(db) -> ActionContext:
    # library_path must be the real package dir so the registry emits and the
    # impls resolve package_path; for the test package db.path lives inside it.
    return ActionContext(actor="ui", library_path=str(Path(db.path).parent))


@pytest.fixture
def spy_emit(monkeypatch):
    """Capture emit_change calls at the SOURCE module the registry imports."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


@pytest.fixture
def fake_ingest(monkeypatch):
    """Replace the heavy ingest functions with light ones that just persist
    controlled Documents to the test db and return them.

    Returns a dict the tests can tweak (e.g. how many docs a folder yields).
    """
    cfg = {"folder_count": 2}

    def _fake_ingest_file(
        path, *, mode=None, parent_id=None, db=None, original_filename=None, **kwargs
    ):
        # Mirrors the real contract (#4471): original_filename rides INTO
        # ingest_file (so pages are named before creation), replacing the old
        # post-hoc rename. If the impl stops passing it through, this fake
        # never sees it and the filename assertion below fails — the test
        # pins the pass-through, not a rename that no longer exists.
        doc = Document(name=original_filename or Path(path).name, parent_id=parent_id)
        db.save(doc)
        return doc

    def _fake_ingest_folder(folder, *, db=None, parent_id=None, on_progress=None, **kwargs):
        docs: list[Document] = []
        for i in range(cfg["folder_count"]):
            d = Document(name=f"{Path(folder).name}-{i}", parent_id=parent_id)
            db.save(d)
            docs.append(d)
        if on_progress:
            on_progress(len(docs), max(len(docs), 1))
        return docs

    monkeypatch.setattr("fichero_server.importers.ingest.ingest_file", _fake_ingest_file)
    monkeypatch.setattr("fichero_server.importers.ingest.ingest_folder", _fake_ingest_folder)
    return cfg


def _audit(db, audit_id) -> ActionAudit:
    audit = db.get(ActionAudit, audit_id)
    assert audit is not None
    return audit


def _invoke_inverse(db, audit_id, ctx) -> str:
    """Drive undo the way the generic undo endpoint does."""
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    inv_name, inv_params = inverse
    registry.invoke(db, inv_name, inv_params, ctx)
    return inv_name


# ===========================================================================
# import.file  (POST /api/ingest/file)  — undoable -> document.delete
# ===========================================================================


class TestImportFileAction:
    def test_file_effect_audit_and_emit(self, db, tmp_path, fake_ingest, spy_emit):
        src = tmp_path / "letter.pdf"
        src.write_bytes(b"%PDF-1.4")

        result = registry.invoke(
            db, "import.file", {"path": str(src), "copy_mode": True}, _ctx(db)
        )

        # (a) effect: a document was created + persisted
        new_id = result.result["id"]
        assert db.get(Document, new_id) is not None

        # (a) audit row with the right shape
        audit = _audit(db, result.audit_id)
        assert audit.action_name == "import.file"
        assert audit.actor == "ui"
        assert audit.target_ids == [new_id]
        assert audit.after == {"document_id": new_id}
        assert audit.before is None  # nothing existed before an import

        # (e) emit fired with document.created + the new id
        assert len(spy_emit) == 1
        _args, kwargs = spy_emit[0]
        assert kwargs["type"] == "document.created"
        assert kwargs["document_ids"] == [new_id]

    def test_file_undo_deletes_then_undo_of_undo_restores(self, db, tmp_path, fake_ingest):
        src = tmp_path / "ephemeral.txt"
        src.write_text("hi")
        ctx = _ctx(db)

        result = registry.invoke(db, "import.file", {"path": str(src)}, ctx)
        new_id = result.result["id"]
        assert db.get(Document, new_id) is not None

        # (b) undo import -> document.delete soft-deletes it
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.delete"
        assert db.get(Document, new_id) is not None
        assert db.get(Document, new_id).deleted_at is not None

        # (b) undo-of-undo: the delete audit inverts to document.restore -> back
        del_audit = next(
            a for a in db.all(ActionAudit)
            if a.action_name == "document.delete" and new_id in a.target_ids
        )
        reg = registry.get("document.delete")
        inverse = reg.invert(del_audit.before, del_audit.after, ctx)
        registry.invoke(db, inverse[0], inverse[1], ctx)
        assert db.get(Document, new_id) is not None

    def test_file_is_undoable(self, db):
        assert registry.get("import.file").undoable is True

    def test_file_missing_path_400(self, db, tmp_path, fake_ingest):
        # (d) a naive impl would hand a non-existent path to the loader
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "import.file", {"path": str(tmp_path / "missing.pdf")}, _ctx(db))
        assert exc.value.status_code == 400

    def test_file_disallowed_path_403(self, db, fake_ingest):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "import.file", {"path": "/no/such/file.pdf"}, _ctx(db))
        assert exc.value.status_code == 403

    def test_file_directory_as_file_400(self, db, tmp_path, fake_ingest):
        # (d) a directory is not a file
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "import.file", {"path": str(tmp_path)}, _ctx(db))
        assert exc.value.status_code == 400

    def test_file_validation_requires_path(self, db):
        # (c) path is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "import.file", {"copy_mode": True}, _ctx(db))


# ===========================================================================
# import.folder  (POST /api/ingest/folder)  — undoable=False (many docs)
# ===========================================================================


class TestImportFolderAction:
    def test_folder_effect_audit_and_emit(self, db, tmp_path, fake_ingest, spy_emit):
        folder = tmp_path / "box"
        folder.mkdir()
        fake_ingest["folder_count"] = 3

        result = registry.invoke(db, "import.folder", {"path": str(folder)}, _ctx(db))

        # (a) effect: three documents created
        ids = result.result["document_ids"]
        assert result.result["count"] == 3
        assert all(db.get(Document, i) is not None for i in ids)

        audit = _audit(db, result.audit_id)
        assert audit.action_name == "import.folder"
        assert set(audit.target_ids) == set(ids)
        assert audit.after == {"document_ids": ids}

        # (e) one document.created emit carrying every new id
        _args, kwargs = spy_emit[-1]
        assert kwargs["type"] == "document.created"
        assert set(kwargs["document_ids"]) == set(ids)

    def test_folder_is_not_undoable(self, db):
        # imports of many docs have no single existing inverse action
        assert registry.get("import.folder").undoable is False

    def test_folder_empty_skips_emit(self, db, tmp_path, fake_ingest, spy_emit):
        # (d) a folder that yields no docs must NOT emit a change event
        folder = tmp_path / "empty"
        folder.mkdir()
        fake_ingest["folder_count"] = 0

        result = registry.invoke(db, "import.folder", {"path": str(folder)}, _ctx(db))
        assert result.result["count"] == 0
        assert spy_emit == []
        # the audit still records the (empty) request for forensics
        assert _audit(db, result.audit_id).action_name == "import.folder"

    def test_folder_missing_path_400(self, db, tmp_path, fake_ingest):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "import.folder", {"path": str(tmp_path / "missing")}, _ctx(db))
        assert exc.value.status_code == 400

    def test_folder_disallowed_path_403(self, db, fake_ingest):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "import.folder", {"path": "/no/such/dir"}, _ctx(db))
        assert exc.value.status_code == 403

    def test_folder_file_as_folder_400(self, db, tmp_path, fake_ingest):
        # (d) a file path is not a directory
        f = tmp_path / "a.txt"
        f.write_text("x")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "import.folder", {"path": str(f)}, _ctx(db))
        assert exc.value.status_code == 400

    def test_folder_validation_requires_path(self, db):
        # (c) path is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "import.folder", {"recursive": True}, _ctx(db))


# ===========================================================================
# import.xlsx  (POST /api/ingest/xlsx)  — undoable=False; dry_run is a no-op
# ===========================================================================


@pytest.fixture
def fake_xlsx(monkeypatch):
    """Stub the xlsx reader so import.xlsx tests don't need a real workbook."""
    rows = {"records": [{"name": "Row A"}, {"name": "Row B"}]}

    def _read(path, *, column_map=None, sheet_index=0):
        return rows["records"]

    monkeypatch.setattr("fichero_server.loaders.xlsx_reader.read_xlsx_records", _read)
    return rows


class TestImportXlsxAction:
    def _xlsx_file(self, tmp_path) -> Path:
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK\x03\x04")  # zip magic; reader is stubbed anyway
        return f

    def test_xlsx_creates_docs_audit_and_emit(self, db, tmp_path, fake_xlsx, spy_emit):
        f = self._xlsx_file(tmp_path)

        result = registry.invoke(
            db, "import.xlsx", {"path": str(f), "dry_run": False}, _ctx(db)
        )

        # (a) effect: one document per row
        ids = result.result["document_ids"]
        assert result.result["count"] == 2
        assert {db.get(Document, i).name for i in ids} == {"Row A", "Row B"}

        audit = _audit(db, result.audit_id)
        assert audit.action_name == "import.xlsx"
        assert set(audit.target_ids) == set(ids)

        # (e) emit document.created with the created ids
        _args, kwargs = spy_emit[-1]
        assert kwargs["type"] == "document.created"
        assert set(kwargs["document_ids"]) == set(ids)

    def test_xlsx_dry_run_is_a_noop(self, db, tmp_path, fake_xlsx, spy_emit):
        # (d) dry_run mutates NOTHING and emits NO change event, even though it
        # still writes an audit recording the (preview) request
        f = self._xlsx_file(tmp_path)
        before = len(db.all(Document))

        result = registry.invoke(
            db, "import.xlsx", {"path": str(f), "dry_run": True}, _ctx(db)
        )
        assert result.result["dry_run"] is True
        assert result.result["document_ids"] == []
        assert len(db.all(Document)) == before
        assert spy_emit == []
        assert _audit(db, result.audit_id).after is None

    def test_xlsx_unnamed_row_skipped(self, db, tmp_path, fake_xlsx, spy_emit):
        # (d) a row with no derivable name is skipped + reported, not crashed
        fake_xlsx["records"] = [{"name": "Keep"}, {"_internal": "drop"}]
        f = self._xlsx_file(tmp_path)

        result = registry.invoke(
            db, "import.xlsx", {"path": str(f), "dry_run": False}, _ctx(db)
        )
        assert result.result["count"] == 1
        assert len(result.result["errors"]) == 1

    def test_xlsx_non_spreadsheet_400(self, db, tmp_path, fake_xlsx):
        # (d) a .txt path is rejected before any parse attempt
        bad = tmp_path / "notes.txt"
        bad.write_text("hi")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "import.xlsx", {"path": str(bad), "dry_run": False}, _ctx(db)
            )
        assert exc.value.status_code == 400

    def test_xlsx_is_not_undoable(self, db):
        assert registry.get("import.xlsx").undoable is False

    def test_xlsx_validation_requires_path(self, db):
        # (c) path is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "import.xlsx", {"dry_run": False}, _ctx(db))


# ===========================================================================
# import.upload_file  (POST /api/documents/import)  — undoable -> document.delete
# ===========================================================================


class TestImportUploadFileAction:
    def test_upload_effect_filename_audit_and_emit(self, db, fake_ingest, spy_emit):
        # the on-disk file has a hashed/temp name; the action preserves the
        # caller's original display name (#1104)
        src = Path(db.path).parent / "files" / "fichero_upload_abc123.pdf"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"%PDF-1.4")

        result = registry.invoke(
            db,
            "import.upload_file",
            {"path": str(src), "original_filename": "Marshall Diary.pdf"},
            _ctx(db),
        )

        new_id = result.result["id"]
        persisted = db.get(Document, new_id)
        assert persisted is not None
        # (d) the display name is the ORIGINAL, not the temp/hashed on-disk name
        assert persisted.name == "Marshall Diary.pdf"

        audit = _audit(db, result.audit_id)
        assert audit.action_name == "import.upload_file"
        assert audit.target_ids == [new_id]
        assert audit.after == {"document_id": new_id}

        _args, kwargs = spy_emit[-1]
        assert kwargs["type"] == "document.created"
        assert kwargs["document_ids"] == [new_id]

    def test_upload_undo_deletes(self, db, fake_ingest):
        src = Path(db.path).parent / "files" / "fichero_upload_x.txt"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("hi")
        ctx = _ctx(db)

        result = registry.invoke(db, "import.upload_file", {"path": str(src)}, ctx)
        new_id = result.result["id"]
        assert db.get(Document, new_id) is not None

        # (b) undo -> document.delete soft-deletes it
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "document.delete"
        assert db.get(Document, new_id) is not None
        assert db.get(Document, new_id).deleted_at is not None

    def test_upload_rejects_absolute_path_outside_library(self, db, fake_ingest):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "import.upload_file", {"path": "/etc/passwd"}, _ctx(db))
        assert exc.value.status_code == 400

    def test_upload_missing_path_400(self, db, fake_ingest):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "import.upload_file", {"path": "/no/such/upload.pdf"}, _ctx(db)
            )
        assert exc.value.status_code == 400

    def test_upload_validation_requires_path(self, db):
        # (c) path is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "import.upload_file", {"parent_id": None}, _ctx(db))

    def test_upload_is_undoable(self, db):
        assert registry.get("import.upload_file").undoable is True


# ===========================================================================
# Registration sanity — every import.* verb is in the registry
# ===========================================================================


def test_all_import_actions_registered():
    names = set(registry.names())
    assert {
        "import.file",
        "import.folder",
        "import.xlsx",
        "import.upload_file",
    } <= names
