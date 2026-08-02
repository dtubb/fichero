"""#4324(e): sub-workflow refs resolve from the library DB before shipped JSON.

A user who edits a seeded sub-workflow component edits the DB row; the shipped
preset JSON is only the install-time template. Resolution order:
injected state["sub_workflows"] → library DB (by id, then by name preferring
the seeded is_system/is_template row) → shipped preset JSON.
"""

from __future__ import annotations

from pathlib import Path

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models import Workflow
from fichero_server.workflows.subworkflow import resolve_sub_workflow_ref
from fichero_server.workflows.types import WorkflowDef

CHILD_NAME = "Spanish Script v2 Child Passes (19th-20th C.)"


def _library(tmp_path: Path) -> Path:
    library_path = tmp_path / "subwf.fichero"
    seed(library_path)
    return library_path


def test_db_edited_child_wins_over_shipped_json(tmp_path: Path):
    library_path = _library(tmp_path)
    db = db_manager.get_database(library_path)
    edited = Workflow(
        id="child-edited",
        name=CHILD_NAME,
        is_system=True,
        nodes=[{"id": "only-node", "tool": "transcribe", "config": {"prompt": "edited"}}],
        edges=[],
    )
    db.save(edited)

    resolved = resolve_sub_workflow_ref(
        CHILD_NAME, {"library_path": str(library_path)}
    )
    assert isinstance(resolved, WorkflowDef)
    assert [n.id for n in resolved.nodes] == ["only-node"]
    assert resolved.nodes[0].config.get("prompt") == "edited"


def test_db_resolution_by_workflow_id(tmp_path: Path):
    library_path = _library(tmp_path)
    db = db_manager.get_database(library_path)
    stored = Workflow(
        id="my-child-id",
        name="Custom Child",
        nodes=[{"id": "n1", "tool": "transcribe", "config": {}}],
        edges=[],
    )
    db.save(stored)

    resolved = resolve_sub_workflow_ref(
        "my-child-id", {"library_path": str(library_path)}
    )
    assert resolved is not None
    assert resolved.name == "Custom Child"


def test_seeded_row_preferred_over_user_duplicate(tmp_path: Path):
    """A user's same-named duplicate must not hijack a preset reference."""
    library_path = _library(tmp_path)
    db = db_manager.get_database(library_path)
    db.save(
        Workflow(
            id="user-copy",
            name=CHILD_NAME,
            is_system=False,
            is_template=False,
            nodes=[{"id": "hijack", "tool": "transcribe", "config": {}}],
            edges=[],
        )
    )
    db.save(
        Workflow(
            id="seeded-copy",
            name=CHILD_NAME,
            is_system=True,
            nodes=[{"id": "seeded-node", "tool": "transcribe", "config": {}}],
            edges=[],
        )
    )

    resolved = resolve_sub_workflow_ref(
        CHILD_NAME, {"library_path": str(library_path)}
    )
    assert resolved is not None
    assert [n.id for n in resolved.nodes] == ["seeded-node"]


def test_falls_back_to_shipped_json_when_absent_from_db(tmp_path: Path):
    library_path = _library(tmp_path)
    db = db_manager.get_database(library_path)
    for wf in db.all(Workflow):
        if wf.name == CHILD_NAME:
            db.delete(wf)

    resolved = resolve_sub_workflow_ref(
        CHILD_NAME, {"library_path": str(library_path)}
    )
    assert resolved is not None, "shipped JSON fallback must still resolve"
    assert {n.tool for n in resolved.nodes} >= {"transcribe", "transcribe_review"}


def test_no_state_still_resolves_shipped_presets():
    resolved = resolve_sub_workflow_ref(CHILD_NAME, None)
    assert resolved is not None


def test_injected_state_wins_over_db(tmp_path: Path):
    library_path = _library(tmp_path)
    injected = WorkflowDef(
        id="inj",
        name=CHILD_NAME,
        nodes=[],
        edges=[],
    )
    resolved = resolve_sub_workflow_ref(
        CHILD_NAME,
        {"library_path": str(library_path), "sub_workflows": {CHILD_NAME: injected}},
    )
    assert resolved is injected


def test_global_default_edit_wins_outside_the_global_library(tmp_path: Path, monkeypatch):
    """#4450 parity for CHILD refs: a user's edit to a default component is a
    GLOBAL-library row. Running the parent in another library must use that
    edited row, not the pristine shipped JSON — otherwise the same workflow
    silently behaves differently per library."""

    library_path = _library(tmp_path)  # no matching row in THIS library

    edited_global = Workflow(
        id="global-child-id",
        name=CHILD_NAME,
        is_system=True,
        nodes=[{"id": "edited-node", "tool": "transcribe", "config": {"prompt": "global-edit"}}],
        edges=[],
    )

    class _GlobalDB:
        def get(self, model, wid):
            return edited_global if wid == "global-child-id" else None

        def workflow_rows_for_list(self, folder_path=None):
            return [edited_global]

    monkeypatch.setattr(
        "fichero_server.workflows.default_workflows.get_global_defaults_database",
        lambda: _GlobalDB(),
    )

    # By id and by name, the global row must beat the shipped JSON.
    for ref in ("global-child-id", CHILD_NAME):
        resolved = resolve_sub_workflow_ref(ref, {"library_path": str(library_path)})
        assert isinstance(resolved, WorkflowDef), ref
        assert [n.id for n in resolved.nodes] == ["edited-node"], ref
        assert resolved.nodes[0].config.get("prompt") == "global-edit", ref

    # And a global USER workflow (is_system=False) must NOT leak.
    edited_global.is_system = False
    resolved = resolve_sub_workflow_ref(
        "global-child-id", {"library_path": str(library_path)}
    )
    assert resolved is None or resolved.nodes[0].id != "edited-node", (
        "a user workflow in the global library is not a default and must not "
        "resolve into other libraries' runs"
    )
