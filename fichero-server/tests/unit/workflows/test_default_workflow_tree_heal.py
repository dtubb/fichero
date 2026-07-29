"""Tests for ``heal_default_workflow_tree`` (#4102).

Libraries seeded before the locked "Default Workflows" container existed
hold the preset folders (Transcribe, Convert, …) as ROOT-level folder
documents, with the workflow mirrors parented to them. Seeding is
name-idempotent so it never re-saves those rows — the heal must:

* re-home every preset mirror under the container's per-folder subfolder,
* delete the legacy root folder once the re-homing empties it,
* NEVER touch a root folder that still has content (a user's own "Books"),
* be a cheap no-op when the tree is already healthy.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from fichero_server.db import _DEFAULT_WORKFLOWS_CONTAINER_ID, Database
from fichero_server.models import DocType, Document, Workflow
from fichero_server.workflows.default_workflows import (
    _load_preset_files,
    heal_default_workflow_tree,
)


@pytest.fixture
def temp_db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


def _first_foldered_preset() -> dict:
    preset = next(
        p for p in _load_preset_files() if (p.get("folder_path") or "/") not in ("", "/")
    )
    return preset


def _make_legacy_layout(db: Database, preset: dict) -> tuple[Workflow, Document]:
    """Simulate the pre-container tree: a root-level preset folder holding
    the workflow's mirror document."""
    folder_name = preset["folder_path"].strip("/")
    legacy_folder = Document(name=folder_name)
    legacy_folder.doc_type = DocType.folder
    db.save(legacy_folder)

    workflow = Workflow(
        name=preset["name"],
        is_template=True,
        is_system=True,
        folder_path=preset["folder_path"],
    )
    db.save(workflow)

    # Force the mirror back to the legacy shape: parented to the root folder.
    mirror = db.get(Document, workflow.id)
    mirror.parent_id = legacy_folder.id
    db.save(mirror)
    return workflow, legacy_folder


def test_heal_rehomes_mirror_and_sweeps_empty_legacy_folder(temp_db):
    preset = _first_foldered_preset()
    workflow, legacy_folder = _make_legacy_layout(temp_db, preset)

    healed = heal_default_workflow_tree(temp_db)
    assert healed == 1

    mirror = temp_db.get(Document, workflow.id)
    assert mirror.parent_id is not None
    assert mirror.parent_id.startswith(_DEFAULT_WORKFLOWS_CONTAINER_ID)
    assert "/" not in mirror.parent_id.removeprefix("system-default-workflows")

    # The emptied legacy root folder is gone.
    assert temp_db.get(Document, legacy_folder.id) is None


def test_heal_recognizes_legacy_seed_without_system_flags(temp_db):
    preset = _first_foldered_preset()
    workflow, _ = _make_legacy_layout(temp_db, preset)
    workflow.is_template = False
    workflow.is_system = False
    temp_db.save(workflow)

    assert heal_default_workflow_tree(temp_db) == 1
    assert temp_db.get(Document, workflow.id).parent_id.startswith(
        _DEFAULT_WORKFLOWS_CONTAINER_ID
    )


def test_heal_leaves_user_folder_with_content_alone(temp_db):
    preset = _first_foldered_preset()
    _, legacy_folder = _make_legacy_layout(temp_db, preset)

    # A user document inside the same-named root folder.
    user_doc = Document(name="my-notes.pdf", parent_id=legacy_folder.id)
    temp_db.save(user_doc)

    heal_default_workflow_tree(temp_db)

    # Folder survives because it still has the user's content.
    assert temp_db.get(Document, legacy_folder.id) is not None
    assert temp_db.get(Document, user_doc.id).parent_id == legacy_folder.id


def test_heal_skips_user_authored_workflows(temp_db):
    preset = _first_foldered_preset()
    # Same name as a preset but NOT template/system — a user's own copy.
    workflow = Workflow(name=preset["name"], is_template=False, is_system=False)
    temp_db.save(workflow)
    before = temp_db.get(Document, workflow.id).parent_id

    healed = heal_default_workflow_tree(temp_db)

    assert healed == 0
    assert temp_db.get(Document, workflow.id).parent_id == before


def test_heal_is_noop_on_healthy_tree(temp_db):
    preset = _first_foldered_preset()
    workflow = Workflow(
        name=preset["name"],
        is_template=True,
        is_system=True,
        folder_path=preset["folder_path"],
    )
    temp_db.save(workflow)  # already homed by the mirror save

    assert heal_default_workflow_tree(temp_db) == 0
    mirror = temp_db.get(Document, workflow.id)
    assert mirror.parent_id.startswith(_DEFAULT_WORKFLOWS_CONTAINER_ID)
