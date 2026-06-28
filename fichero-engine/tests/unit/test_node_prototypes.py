"""Tests for prototype/class resolution — node-model fold P1 (#2591)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from fichero.db import Database
from fichero.knowledge.knowledge_models import (
    ClassificationDimension,
    ClassificationValue,
)
from fichero.node_prototypes import (
    PrototypeResolutionError,
    resolve_prototype_attributes,
)


@pytest.fixture
def temp_db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


def _proto(db, key, *, parent_key=None, attributes=None):
    db.save(
        ClassificationValue(
            dimension=ClassificationDimension.document_prototype,
            key=key,
            label=key.title(),
            parent_key=parent_key,
            attributes=attributes or {},
        )
    )


def test_child_inherits_and_overrides_parent_attributes(temp_db):
    _proto(temp_db, "container", attributes={"chat_enabled": True, "icon": "folder"})
    _proto(
        temp_db,
        "workspace",
        parent_key="container",
        attributes={"icon": "rectangle.3.group", "carries_tasks": True},
    )

    effective = resolve_prototype_attributes(temp_db, "workspace")
    assert effective["chat_enabled"] is True  # inherited from container
    assert effective["carries_tasks"] is True  # own
    assert effective["icon"] == "rectangle.3.group"  # child overrides parent


def test_three_level_chain_merges_root_to_leaf(temp_db):
    _proto(temp_db, "node", attributes={"a": 1})
    _proto(temp_db, "container", parent_key="node", attributes={"b": 2})
    _proto(temp_db, "room", parent_key="container", attributes={"a": 99, "c": 3})

    effective = resolve_prototype_attributes(temp_db, "room")
    assert effective == {"a": 99, "b": 2, "c": 3}


def test_unknown_key_raises(temp_db):
    with pytest.raises(PrototypeResolutionError):
        resolve_prototype_attributes(temp_db, "does-not-exist")


def test_unknown_parent_raises(temp_db):
    _proto(temp_db, "child", parent_key="ghost", attributes={"x": 1})
    with pytest.raises(PrototypeResolutionError):
        resolve_prototype_attributes(temp_db, "child")


def test_cyclic_chain_raises(temp_db):
    _proto(temp_db, "a", parent_key="b")
    _proto(temp_db, "b", parent_key="a")
    with pytest.raises(PrototypeResolutionError):
        resolve_prototype_attributes(temp_db, "a")
