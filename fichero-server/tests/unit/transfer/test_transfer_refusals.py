"""A transfer that cannot be done is refused in words, and changes nothing (#5657).

WHY: `transfer.action.refusals-in-words`. The drop between projects used to do nothing at all
(#2397's "nothing happens"): the source's id went to the target's routes, which did not know it.
Each refusal here names what is wrong in a sentence a person can act on, through the real route,
and neither project changes.
"""

from __future__ import annotations

import pytest
from fichero_server.db.manager import db_manager
from fichero_server.models import DocType, Document

from tests.unit.transfer._two_projects import build_box, open_source, table_counts


@pytest.fixture
def two(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    box = build_box(source, db, tmp_path)
    return client, db, source, source_package, box


def assert_refused(client, db, source, body, status, words):
    before = (table_counts(db), table_counts(source))
    response = client.post("/api/documents/transfer", json=body)
    assert response.status_code == status, response.text
    assert words in response.json()["detail"]
    assert (table_counts(db), table_counts(source)) == before


def test_the_same_project_is_refused(two, test_package):
    client, db, source, _pkg, _box = two
    page = Document(name="here.png", doc_type=DocType.file)
    db.save(page)
    assert_refused(client, db, source, {"items": [page.id], "source": str(test_package)}, 400,
             "is both the source and the target")


def test_an_unknown_item_is_refused(two):
    client, db, source, pkg, _box = two
    assert_refused(client, db, source, {"items": ["no-such-item"], "source": str(pkg)}, 404,
             "There is no item no-such-item in Origen")


def test_a_target_that_is_not_a_folder_is_refused(two):
    client, db, source, pkg, box = two
    page = Document(name="a page", doc_type=DocType.file)
    db.save(page)
    assert_refused(client, db, source, {"items": [box.page1.id], "source": str(pkg), "target_parent_id": page.id}, 400,
             "a page is not a folder")


def test_a_project_that_is_not_open_is_refused(two, tmp_path):
    client, db, source, _pkg, box = two
    closed = tmp_path / "Cerrado.fichero"
    closed.mkdir()
    assert_refused(client, db, source, {"items": [box.page1.id], "source": str(closed)}, 409,
             "Cerrado is not open")


def test_an_alias_between_projects_is_refused(two):
    client, db, source, pkg, box = two
    alias = Document(name="p1 alias", node_kind="alias", alias_target_id=box.page1.id, doc_type=DocType.file)
    source.save(alias)
    assert_refused(client, db, source, {"items": [alias.id], "source": str(pkg)}, 409, "Aliases stay within a project.")


def _pending_move(db, items, target="Istmina"):
    """A move of `items` that a crash left between its checked copy and its source step."""
    from fichero_server.models.transfer import (
        TransferMode,
        TransferRecord,
        TransferRole,
        TransferState,
    )

    db.save(TransferRecord(role=TransferRole.source, state=TransferState.verified, mode=TransferMode.move,
                           source_project=str(db.path.parent), target_project=f"/x/{target}.fichero", items=items))


def test_a_second_drag_of_an_item_a_pending_move_holds_is_refused(two):
    """`transfer.action.second-drag-refused`: the item itself, a page inside it, a folder holding it --
    each read from the source's mirror row alone."""
    client, db, source, pkg, box = two
    _pending_move(source, [box.folder.id])
    for item in (box.folder.id, box.page1.id):
        for mode in ("copy", "move"):
            assert_refused(client, db, source, {"items": [item], "source": str(pkg), "mode": mode}, 409,
                     "These items are already being moved to Istmina.")


def test_a_drop_into_a_folder_a_pending_move_holds_is_refused(two):
    client, db, source, pkg, box = two
    leaving = Document(name="Leaving", doc_type=DocType.folder)
    inside = Document(name="Inside", doc_type=DocType.folder, parent_id=leaving.id)
    db.save(leaving)
    db.save(inside)
    _pending_move(db, [leaving.id], target="Elsewhere")
    assert_refused(client, db, source, {"items": [box.page1.id], "source": str(pkg), "target_parent_id": inside.id}, 409,
             "That folder is already being moved to Elsewhere.")


def test_a_locked_node_is_refused(two):
    client, db, source, pkg, _box = two
    locked = Document(name="Default Workflows", doc_type=DocType.folder, attributes={"read_only": True})
    source.save(locked)
    assert_refused(client, db, source, {"items": [locked.id], "source": str(pkg)}, 403, "read-only")
