"""A move between projects: the copy, then the source's items in its Trash "moved to", the source's
edges cut and listed, and one undo from either project (#5657, build order 4).

WHY: a move is a copy plus a delete across two files that share no transaction. The source may give
up its items only after the target's copy is checked, and only to its Trash, labelled so a person
finds them ("moved to Istmina"); what cannot follow (a place on a canvas that stays, a workspace
slot, an alias, a synced-folder tie) is cut on purpose and listed, never left pointing at nothing;
and one undo, from either project's window, puts the source back whole and takes the copy away.
Through the real route and the real undo route, between two real open projects.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fichero_server import sync_folder
from fichero_server.api.main import app
from fichero_server.api.routes.document.trash import moved_reasons
from fichero_server.db.manager import db_manager
from fichero_server.models import ActionAudit, DocType, Document
from fichero_server.models.canvas import CanvasItem, CanvasItemKind, CanvasLayout
from fichero_server.models.transfer import TransferRecord

from tests.unit.transfer._two_projects import (
    build_box,
    header_decides,
    open_source,
    table_counts,
)


def _source_edges(source, box) -> dict:
    """Edges from what stays in the source to what moves: each must be cut there, and come back on undo."""
    layout = CanvasLayout(id=f"{box.elsewhere.parent_id}::{box.folder.id}", folder_id=box.elsewhere.parent_id,
                          item_id=box.folder.id, x=5, y=6)
    link = CanvasItem(folder_id=box.elsewhere.parent_id, kind=CanvasItemKind.link,
                      source_item_id=box.elsewhere.id, target_item_id=box.page1.id)
    workspace = Document(name="Desk", doc_type=DocType.folder, is_workspace=True, curated_items=[
        {"id": "slot-1", "target_type": "document", "target_id": box.page1.id},
        {"id": "slot-2", "target_type": "document", "target_id": box.elsewhere.id},
    ])
    alias = Document(name="p2 alias", parent_id=box.elsewhere.parent_id, node_kind="alias",
                     alias_target_id=box.page2.id)
    for row in (layout, link, workspace, alias):
        source.save(row)
    sync_folder._ensure(source)
    sync_folder._record(source, "folder-1", "Box 1/p1.txt", document_id=box.page1.id, fmt="txt", sha="abc",
                        state="written", written=True)
    return {"layout": layout, "link": link, "workspace": workspace, "alias": alias}


def _move(client, source_package, box):
    return client.post("/api/documents/transfer",
                       json={"items": [box.folder.id], "source": str(source_package), "mode": "move"})


def _ties(source, document_id):
    return source.execute_fetchall("SELECT rel_path FROM sync_files WHERE document_id = ?", [document_id])


def test_a_move_lands_whole_and_sends_the_source_to_its_trash_labelled(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    edges = _source_edges(source, box)

    response = _move(client, source_package, box)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "move" and result["state"] == "done"
    [folder_id] = result["copies"]
    assert {d.name for d in db.query(Document, parent_id=folder_id)} == {"p1.png", "p2.png", "p1 alias"}

    # The source's items are in its Trash, not gone, and the Trash says where they went.
    for moved in (box.folder, box.page1, box.page2):
        assert source.get(Document, moved.id).deleted_at is not None
    reasons = moved_reasons(source, [box.folder.id])
    assert reasons[box.folder.id][0].project == "test" and reasons[box.folder.id][0].transfer_id == result["transfer_id"]
    assert source.get(Document, box.elsewhere.id).deleted_at is None  # what did not move stays

    # Cut in the source and listed: the canvas place, the canvas link, the workspace slot, the alias, the tie.
    assert source.get(CanvasLayout, edges["layout"].id) is None
    assert source.get(CanvasItem, edges["link"].id) is None
    assert [s["target_id"] for s in source.get(Document, edges["workspace"].id).curated_items] == [box.elsewhere.id]
    assert source.get(Document, edges["alias"].id).deleted_at is not None
    assert _ties(source, box.page1.id) == []
    listed = {(c["kind"], c["row"]) for c in result["cuts"]}
    assert {("CanvasLayout", edges["layout"].id), ("CanvasItem", edges["link"].id),
            ("Document", edges["workspace"].id), ("Document", edges["alias"].id), ("sync_files", box.page1.id)} <= listed

    # The record in both projects is done; the source's says what it sent to its Trash.
    assert db.get(TransferRecord, result["transfer_id"]).state.value == "done"
    mirror = source.get(TransferRecord, result["transfer_id"])
    assert mirror.state.value == "done" and {box.folder.id, box.page1.id, edges["alias"].id} <= set(mirror.trashed)


def _undo(client, audit_id, headers=None):
    return client.post(f"/api/actions/audit/{audit_id}/undo", headers=headers or {})


def _assert_undone(source, db, box, edges, result, source_before):
    for moved in (box.folder, box.page1, box.page2):
        assert source.get(Document, moved.id).deleted_at is None
    assert source.get(CanvasLayout, edges["layout"].id) is not None
    assert source.get(CanvasItem, edges["link"].id) is not None
    assert len(source.get(Document, edges["workspace"].id).curated_items) == 2
    assert source.get(Document, edges["alias"].id).deleted_at is None
    assert _ties(source, box.page1.id) == [("Box 1/p1.txt",)]
    assert db.get(Document, result["copies"][0]).deleted_at is not None  # the copy is in the target's Trash
    assert db.get(TransferRecord, result["transfer_id"]).state.value == "undone"
    assert source.get(TransferRecord, result["transfer_id"]).state.value == "undone"
    # Every row the source had is back as it was (audit rows and the record aside).
    after = table_counts(source)
    assert {k: v for k, v in after.items() if k != "ActionAudit"} == {k: v for k, v in source_before.items() if k != "ActionAudit"}


def test_undo_of_a_move_from_the_target_puts_both_projects_back(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    edges = _source_edges(source, box)
    source_before = table_counts(source)
    result = _move(client, source_package, box).json()

    undone = _undo(client, result["audit"])
    assert undone.status_code == 200, undone.text
    _assert_undone(source, db, box, edges, result, source_before)
    # And a second undo, from the other window, is refused in words.
    header_decides(app)
    [out] = [a for a in source.all(ActionAudit) if a.action_name == "document.transfer_out"]
    again = _undo(client, out.id, {"X-Fichero-Library-Path": quote(str(source_package), safe="/")})
    assert again.status_code == 409 and "already undone" in again.json()["detail"]


def test_undo_of_a_move_from_the_source_puts_both_projects_back(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    edges = _source_edges(source, box)
    source_before = table_counts(source)
    result = _move(client, source_package, box).json()

    header_decides(app)
    [out] = [a for a in source.all(ActionAudit) if a.action_name == "document.transfer_out"]
    undone = _undo(client, out.id, {"X-Fichero-Library-Path": quote(str(source_package), safe="/")})
    assert undone.status_code == 200, undone.text
    _assert_undone(source, db, box, edges, result, source_before)


def test_undo_of_a_move_is_refused_once_the_source_trash_was_emptied(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    result = _move(client, source_package, box).json()
    source.delete(source.get(Document, box.page1.id))  # emptied from the source's Trash: gone for good

    refused = _undo(client, result["audit"])
    assert refused.status_code == 409 and "the move is permanent" in refused.json()["detail"]
    assert db.get(Document, result["copies"][0]).deleted_at is None  # nothing changed in the target


def test_undo_of_a_move_needs_both_projects_open(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    result = _move(client, source_package, box).json()
    db_manager.close_database(source_package)

    refused = _undo(client, result["audit"])
    assert refused.status_code == 409 and "Open Origen to undo this move" in refused.json()["detail"]
    assert db.get(Document, result["copies"][0]).deleted_at is None
    assert Path(source_package).is_dir()
