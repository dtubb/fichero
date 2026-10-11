"""A copy that fails half-way leaves nothing it wrote, and the source as it was (#5657).

WHY: two projects are two DuckDB files with no shared transaction. A copy that stopped after half
its rows would leave pages without their lines, readings without their pages, files nobody points
at -- and a person would not know which half arrived. `transfer.action.verify-then-delete` and the
journal (`transfer.action.journal-recovers`) promise all or nothing: the record is written
`writing` before any row, the rows go in one target transaction, and a failure rolls it back, removes
the copied files and records why. The failure is injected after half the rows, through the real route.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.db.manager import db_manager
from fichero_server.models import Document
from fichero_server.models.transfer import TransferRecord
from fichero_server.transfer import copy as transfer_copy
from tests.unit.transfer._two_projects import build_box, open_source, table_counts


def test_a_failure_after_half_the_writes_leaves_the_target_with_nothing(client, db, tmp_path, monkeypatch):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    source_before, target_before = table_counts(source), table_counts(db)
    target_files = Path(db.path).parent / "files"
    files_before = sorted(target_files.rglob("*"))

    planned = client.post("/api/documents/transfer",
                          json={"items": [box.folder.id], "source": str(source_package), "dry_run": True}).json()
    half = sum(c["planned"] for c in planned["counts"]) // 2
    real_save, saved = transfer_copy._save_row, []

    def fail_half_way(target_db, row):
        if len(saved) == half:
            raise OSError("disk went away")
        real_save(target_db, row)
        saved.append(row.id)

    monkeypatch.setattr(transfer_copy, "_save_row", fail_half_way)
    response = client.post("/api/documents/transfer", json={"items": [box.folder.id], "source": str(source_package)})

    assert len(saved) == half > 0  # the failure really came after half the rows were written
    assert response.status_code == 500
    assert "rolled back" in response.json()["detail"] and "disk went away" in response.json()["detail"]
    # Nothing the transfer wrote is left in the target: rows, files.
    assert table_counts(db) == target_before
    assert not [d for d in db.all(Document) if (d.metadata or {}).get("transferred_from")]
    assert sorted(target_files.rglob("*")) == files_before
    # The record says what failed, and that it was rolled back; nothing became undoable.
    [record] = db.all(TransferRecord)
    assert record.state.value == "rolled_back" and "disk went away" in record.error
    assert record.result["state"] == "rolled_back"
    # The source is exactly as it was, with no record of a transfer that did not happen.
    assert table_counts(source) == source_before
    assert source.all(TransferRecord) == []


def test_a_rolled_back_transfer_cannot_be_undone(client, db, tmp_path, monkeypatch):
    """The journal's `rolled_back` is final: the undo action refuses it in words, changing nothing."""
    from fichero_server.actions.registry import ActionContext, ActionRefused, registry

    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)

    def fail(target_db, row):
        raise OSError("no room")

    monkeypatch.setattr(transfer_copy, "_save_row", fail)
    client.post("/api/documents/transfer", json={"items": [box.page1.id], "source": str(source_package)})
    [record] = db.all(TransferRecord)
    ctx = ActionContext(actor="maker", library_path=str(Path(db.path).parent), is_bootstrap=True)
    try:
        registry.invoke(db, "document.untransfer", {"transfer_id": record.id}, ctx)
    except ActionRefused as refused:
        assert "rolled_back" in str(refused)
    else:
        raise AssertionError("undo of a rolled-back transfer was not refused")


def test_a_transfer_a_crash_left_writing_is_rolled_back_when_the_project_opens(tmp_path):
    """The journal: a crash between `writing` and the commit leaves no rows (DuckDB rolled them back)
    but may leave copied files; opening the project removes them and says why. A copy a crash left
    `verified` was committed and checked, so it is closed as done."""
    from fichero_server.models.transfer import TransferMode, TransferRole, TransferState

    package = open_source(tmp_path, "Istmina.fichero")
    db = db_manager.get_database(package)
    stray = package / "files" / "transfer-1234" / "p1.png"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"half a copy")
    common = dict(role=TransferRole.target, mode=TransferMode.copy, source_project="Origen", target_project=str(package))
    db.save(TransferRecord(id="crashed", state=TransferState.writing, files_written=[str(stray)], **common))
    db.save(TransferRecord(id="finished", state=TransferState.verified, **common))
    db_manager.close_database(package)

    reopened = db_manager.get_database(package)
    crashed = reopened.get(TransferRecord, "crashed")
    assert crashed.state.value == "rolled_back" and "rolled back on open" in crashed.error
    assert not stray.exists()
    assert reopened.get(TransferRecord, "finished").state.value == "done"
