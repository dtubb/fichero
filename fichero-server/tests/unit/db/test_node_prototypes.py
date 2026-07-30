"""Tests for prototype/class resolution — node-model fold P1 (#2591)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from fichero_server.db import Database
from fichero_server.models.knowledge import (
    ClassificationDimension,
    ClassificationValue,
)
from fichero_server.models.node_prototypes import (
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
    _proto(temp_db, "test_room", parent_key="container", attributes={"a": 99, "c": 3})

    effective = resolve_prototype_attributes(temp_db, "test_room")
    assert effective == {"a": 99, "b": 2, "c": 3}


def test_builtin_room_and_workspace_inherit_folder_attributes(temp_db):
    room = resolve_prototype_attributes(temp_db, "room")
    workspace = resolve_prototype_attributes(temp_db, "research_workspace")

    assert room["container_kind"] == "folder"
    assert room["supports_children"] is True
    assert room["workspace_kind"] == "room"
    assert workspace["container_kind"] == "folder"
    assert workspace["supports_children"] is True
    assert workspace["workspace_kind"] == "research"


def test_user_defined_child_of_builtin_room_inherits_folder_chain_and_overrides_leaf(temp_db):
    _proto(
        temp_db,
        "custom_room",
        parent_key="room",
        attributes={"workspace_kind": "custom-room", "accent": "gold"},
    )

    effective = resolve_prototype_attributes(temp_db, "custom_room")
    assert effective["container_kind"] == "folder"
    assert effective["supports_children"] is True
    assert effective["spatial_layout"] is True
    assert effective["workspace_kind"] == "custom-room"
    assert effective["accent"] == "gold"


def test_four_level_chain_uses_leaf_override_precedence(temp_db):
    _proto(temp_db, "root", attributes={"icon": "square", "theme": "plain", "locked": False})
    _proto(temp_db, "mid_a", parent_key="root", attributes={"theme": "paper"})
    _proto(temp_db, "mid_b", parent_key="mid_a", attributes={"icon": "tray"})
    _proto(temp_db, "leaf", parent_key="mid_b", attributes={"theme": "canvas", "locked": True})

    effective = resolve_prototype_attributes(temp_db, "leaf")
    assert effective == {"icon": "tray", "theme": "canvas", "locked": True}


def test_unknown_key_raises(temp_db):
    with pytest.raises(PrototypeResolutionError):
        resolve_prototype_attributes(temp_db, "does-not-exist")


def test_unknown_parent_raises(temp_db):
    _proto(temp_db, "child", parent_key="ghost", attributes={"x": 1})
    with pytest.raises(PrototypeResolutionError):
        resolve_prototype_attributes(temp_db, "child")


def test_unknown_parent_mid_chain_raises(temp_db):
    _proto(temp_db, "root", attributes={"a": 1})
    _proto(temp_db, "middle", parent_key="ghost", attributes={"b": 2})
    _proto(temp_db, "leaf", parent_key="middle", attributes={"c": 3})

    with pytest.raises(PrototypeResolutionError, match="Unknown prototype key"):
        resolve_prototype_attributes(temp_db, "leaf")


def test_cyclic_chain_raises(temp_db):
    _proto(temp_db, "a", parent_key="b")
    _proto(temp_db, "b", parent_key="a")
    with pytest.raises(PrototypeResolutionError):
        resolve_prototype_attributes(temp_db, "a")


def test_three_node_cycle_raises_at_resolution_time(temp_db):
    _proto(temp_db, "a", parent_key="b")
    _proto(temp_db, "b", parent_key="c")
    _proto(temp_db, "c", parent_key="a")

    with pytest.raises(PrototypeResolutionError, match="Cyclic prototype parent chain"):
        resolve_prototype_attributes(temp_db, "a")
