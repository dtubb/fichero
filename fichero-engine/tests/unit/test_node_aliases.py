"""Tests for alias (reference) nodes — node-model fold P2 (#2591)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from fichero.db import Database
from fichero.models import Document, DocType
from fichero.models.node_aliases import (
    ALIAS_NODE_KIND,
    DanglingAliasError,
    is_alias,
    make_alias,
    resolve_alias,
)


@pytest.fixture
def temp_db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


def test_make_alias_references_target_without_copying():
    target = Document(name="Real Folder", doc_type=DocType.folder, page_content="body")
    alias = make_alias(target, parent_id="container-1")

    assert is_alias(alias)
    assert alias.node_kind == ALIAS_NODE_KIND
    assert alias.alias_target_id == target.id
    assert alias.parent_id == "container-1"
    # Mirrors the target's structural kind, but carries no content of its own.
    assert alias.doc_type == DocType.folder
    assert alias.name == "Real Folder"
    assert alias.page_content is None
    # The alias is its own node — not the target.
    assert alias.id != target.id


def test_alias_resolves_to_live_target(temp_db):
    target = Document(name="Target", doc_type=DocType.file)
    temp_db.save(target)
    alias = make_alias(target, parent_id=None)
    temp_db.save(alias)

    # Reload the alias from the DB to prove alias_target_id round-trips.
    reloaded = temp_db.get(Document, alias.id)
    assert reloaded is not None
    assert reloaded.alias_target_id == target.id

    resolved = resolve_alias(temp_db, reloaded)
    assert resolved.id == target.id
    assert resolved.name == "Target"


def test_alias_to_alias_requires_multiple_hops(temp_db):
    target = Document(name="Leaf", doc_type=DocType.file)
    temp_db.save(target)
    first = make_alias(target, parent_id="container-a")
    temp_db.save(first)
    second = make_alias(first, parent_id="container-b", name="Alias Of Alias")
    temp_db.save(second)

    resolved = resolve_alias(temp_db, temp_db.get(Document, second.id))
    assert resolved.id == first.id
    assert resolved.alias_target_id == target.id
    assert resolved.parent_id == "container-a"

    leaf = resolve_alias(temp_db, resolved)
    assert leaf.id == target.id


def test_deep_alias_chain_can_be_walked_hop_by_hop(temp_db):
    target = Document(name="Leaf", doc_type=DocType.file)
    temp_db.save(target)
    hop1 = make_alias(target, parent_id="c1")
    hop2 = make_alias(hop1, parent_id="c2")
    hop3 = make_alias(hop2, parent_id="c3")
    temp_db.save(hop1)
    temp_db.save(hop2)
    temp_db.save(hop3)

    current = temp_db.get(Document, hop3.id)
    for expected in (hop2.id, hop1.id, target.id):
        current = resolve_alias(temp_db, current)
        assert current.id == expected


def test_alias_resolves_after_target_is_reparented(temp_db):
    root = Document(name="Root", doc_type=DocType.folder)
    new_parent = Document(name="New Parent", doc_type=DocType.folder)
    target = Document(name="Target", doc_type=DocType.file, parent_id=root.id)
    temp_db.save(root)
    temp_db.save(new_parent)
    temp_db.save(target)
    alias = make_alias(target, parent_id="alias-container")
    temp_db.save(alias)

    target.parent_id = new_parent.id
    temp_db.save(target)

    resolved = resolve_alias(temp_db, temp_db.get(Document, alias.id))
    assert resolved.id == target.id
    assert resolved.parent_id == new_parent.id


def test_alias_to_alias_second_hop_raises_when_leaf_target_is_deleted(temp_db):
    target = Document(name="Leaf", doc_type=DocType.file)
    temp_db.save(target)
    first = make_alias(target, parent_id=None)
    second = make_alias(first, parent_id=None)
    temp_db.save(first)
    temp_db.save(second)
    temp_db.delete(target)

    intermediate = resolve_alias(temp_db, temp_db.get(Document, second.id))
    assert intermediate.id == first.id

    with pytest.raises(DanglingAliasError):
        resolve_alias(temp_db, intermediate)


def test_resolving_dangling_alias_raises(temp_db):
    """Deleting the target must surface loudly, not silently substitute."""
    target = Document(name="Doomed", doc_type=DocType.file)
    temp_db.save(target)
    alias = make_alias(target, parent_id=None)
    temp_db.save(alias)

    temp_db.delete(target)

    with pytest.raises(DanglingAliasError):
        resolve_alias(temp_db, temp_db.get(Document, alias.id))


def test_alias_with_no_target_id_raises(temp_db):
    bare = Document(name="bare", node_kind=ALIAS_NODE_KIND)
    with pytest.raises(DanglingAliasError):
        resolve_alias(temp_db, bare)


def test_resolving_non_alias_raises_value_error(temp_db):
    plain = Document(name="plain", doc_type=DocType.file)
    with pytest.raises(ValueError):
        resolve_alias(temp_db, plain)
