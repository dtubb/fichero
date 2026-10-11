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

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "scripts"))
from _scan_files import scan_rglob  # noqa: E402


def test_a_failure_after_half_the_writes_leaves_the_target_with_nothing(client, db, tmp_path, monkeypatch):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    source_before, target_before = table_counts(source), table_counts(db)
    target_files = Path(db.path).parent / "files"
    files_before = sorted(scan_rglob(target_files, "*"))

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
    assert sorted(scan_rglob(target_files, "*")) == files_before
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


# --- a move ------------------------------------------------------------------------------------


def test_a_move_whose_source_step_fails_twice_takes_its_copy_back(client, db, tmp_path, monkeypatch):
    """`transfer.action.compensates`: the source step fails half-way (after its deletes, before its cuts)
    twice; its own transaction leaves the source as it was, and the checked copy in the target is
    removed row by row and file by file. A move never ends as a silent copy."""
    from fichero_server.transfer import move

    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    source_before, target_before = table_counts(source), table_counts(db)
    target_files = Path(db.path).parent / "files"
    files_before = sorted(scan_rglob(target_files, "*"))
    attempts = []

    def fails(*args, **kwargs):
        attempts.append(1)
        raise OSError("the source is locked")

    monkeypatch.setattr(move, "cut_in_source", fails)
    response = client.post("/api/documents/transfer",
                           json={"items": [box.folder.id], "source": str(source_package), "mode": "move"})

    assert len(attempts) == 2  # tried, then tried once more
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "was not done" in detail and "taken back" in detail and "the source is locked" in detail
    assert {k: v for k, v in table_counts(source).items() if k != "ActionAudit"} == \
        {k: v for k, v in source_before.items() if k != "ActionAudit"}
    assert source.get(Document, box.folder.id).deleted_at is None
    assert table_counts(db) == target_before and sorted(scan_rglob(target_files, "*")) == files_before
    [record] = db.all(TransferRecord)
    assert record.state.value == "rolled_back" and "the source step failed twice" in record.error
    assert source.get(TransferRecord, record.id).state.value == "rolled_back"


def _move_that_crashes_before_its_source_step(tmp_path, monkeypatch):
    """Two projects, and a move stopped (as by a crash) after the target's copy was checked."""
    from fichero_server.models import DocType
    from fichero_server.transfer import move
    from fichero_server.transfer.plan import build_plan

    source_package, target_package = open_source(tmp_path), open_source(tmp_path, "Istmina.fichero")
    source, target = db_manager.get_database(source_package), db_manager.get_database(target_package)
    box = build_box(source, target, tmp_path)
    landing = Document(name="Landing", doc_type=DocType.folder)
    target.save(landing)
    plan = build_plan(source, target, items=[box.folder.id], target_parent_id=landing.id,
                      transfer_id="crash-move", audit_id="crash-audit", actor="maker")

    class Crash(Exception):
        pass

    def crash(*args, **kwargs):
        raise Crash()

    monkeypatch.setattr(move, "finish_move", crash)
    try:
        move.move_between(source, target, plan, actor="maker", bootstrap=True)
    except Crash:
        pass
    monkeypatch.undo()
    assert target.get(TransferRecord, "crash-move").state.value == "verified"
    assert source.get(TransferRecord, "crash-move").state.value == "verified"
    assert source.get(Document, box.folder.id).deleted_at is None  # the crash came before the source step
    return source_package, target_package, box


def test_a_move_a_crash_left_between_write_and_trash_finishes_when_the_project_opens(tmp_path, monkeypatch):
    """The journal for a move: the copy was written and checked, then the engine stopped. Opening the
    target again (the source open) takes the source step: items to the Trash "moved to", both done."""
    from fichero_server.api.routes.document.trash import moved_reasons

    source_package, target_package, box = _move_that_crashes_before_its_source_step(tmp_path, monkeypatch)
    db_manager.close_database(target_package)
    target = db_manager.get_database(target_package)  # reopened: the pending move is finished

    source = db_manager.get_database(source_package)
    assert target.get(TransferRecord, "crash-move").state.value == "done"
    assert source.get(TransferRecord, "crash-move").state.value == "done"
    assert source.get(Document, box.folder.id).deleted_at is not None
    assert moved_reasons(source, [box.folder.id])[box.folder.id][0].project == "Istmina"


def test_a_pending_move_waits_while_the_other_project_is_closed(tmp_path, monkeypatch):
    """Opened alone, the target cannot take the source step: the move waits, the source untouched,
    and finishes when the source is opened."""
    source_package, target_package, box = _move_that_crashes_before_its_source_step(tmp_path, monkeypatch)
    db_manager.close_database(source_package)
    db_manager.close_database(target_package)

    target = db_manager.get_database(target_package)
    assert target.get(TransferRecord, "crash-move").state.value == "verified"  # waits
    source = db_manager.get_database(source_package)  # the source opens: the move finishes from its side
    assert source.get(TransferRecord, "crash-move").state.value == "done"
    assert target.get(TransferRecord, "crash-move").state.value == "done"
    assert source.get(Document, box.folder.id).deleted_at is not None
