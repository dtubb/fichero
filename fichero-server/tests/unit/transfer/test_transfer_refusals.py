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


def _refused(client, db, source, body, status, words):
    before = (table_counts(db), table_counts(source))
    response = client.post("/api/documents/transfer", json=body)
    assert response.status_code == status, response.text
    assert words in response.json()["detail"]
    assert (table_counts(db), table_counts(source)) == before


def test_the_same_project_is_refused(two, test_package):
    client, db, source, _pkg, _box = two
    page = Document(name="here.png", doc_type=DocType.file)
    db.save(page)
    _refused(client, db, source, {"items": [page.id], "source": str(test_package)}, 400,
             "is both the source and the target")


def test_an_unknown_item_is_refused(two):
    client, db, source, pkg, _box = two
    _refused(client, db, source, {"items": ["no-such-item"], "source": str(pkg)}, 404,
             "There is no item no-such-item in Origen")


def test_a_target_that_is_not_a_folder_is_refused(two):
    client, db, source, pkg, box = two
    page = Document(name="a page", doc_type=DocType.file)
    db.save(page)
    _refused(client, db, source, {"items": [box.page1.id], "source": str(pkg), "target_parent_id": page.id}, 400,
             "a page is not a folder")


def test_a_project_that_is_not_open_is_refused(two, tmp_path):
    client, db, source, _pkg, box = two
    closed = tmp_path / "Cerrado.fichero"
    closed.mkdir()
    _refused(client, db, source, {"items": [box.page1.id], "source": str(closed)}, 409,
             "Cerrado is not open")


def test_an_alias_between_projects_is_refused(two):
    client, db, source, pkg, box = two
    alias = Document(name="p1 alias", node_kind="alias", alias_target_id=box.page1.id, doc_type=DocType.file)
    source.save(alias)
    _refused(client, db, source, {"items": [alias.id], "source": str(pkg)}, 409, "Aliases stay within a project.")


def test_a_move_is_refused_until_it_is_built(two):
    client, db, source, pkg, box = two
    _refused(client, db, source, {"items": [box.page1.id], "source": str(pkg), "mode": "move"}, 409,
             "Moving between projects is not built yet")


def test_a_locked_node_is_refused(two):
    client, db, source, pkg, _box = two
    locked = Document(name="Default Workflows", doc_type=DocType.folder, attributes={"read_only": True})
    source.save(locked)
    _refused(client, db, source, {"items": [locked.id], "source": str(pkg)}, 403, "read-only")
