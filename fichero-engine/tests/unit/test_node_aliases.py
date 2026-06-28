"""Tests for alias (reference) nodes — node-model fold P2 (#2591)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from fichero.db import Database
from fichero.models import Document, DocType
from fichero.node_aliases import (
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
