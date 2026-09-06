"""#4450: default workflows resolve from the GLOBAL library in every library.

Defaults are seeded once into ``global.fichero`` (#4102) and must be OFFERED
and RUNNABLE in every library — resolved from the app, never copied
per-library (copies drift). User workflows are the opposite: they belong to
the library that created them and must not leak across libraries.

The ``client`` fixture speaks for a NON-global library (``test.fichero``);
``global_db`` is the engine's global library database. Every test here fails
without the cross-library resolution added for #4450 (routes previously
looked up workflow ids in the request library's db only).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from fichero_server.models import Workflow


@pytest.fixture
def global_db():
    from fichero_server.db.manager import db_manager
    from fichero_server.db.storage import settings

    db = db_manager.get_database(str(settings.global_library_path))
    # The global library db is SHARED across the whole test session (one
    # FICHERO_BASE_PATH per process). Rows this test saves there would merge
    # into every later library workflow list (#4450 resolution) and turn
    # "empty library" assertions order-dependent — so delete what we create.
    from fichero_server.models import Workflow

    before = {w.id for w in db.all(Workflow)}
    yield db
    for workflow in list(db.all(Workflow)):
        if workflow.id not in before:
            db.delete(workflow)


def _make_default(global_db, name: str | None = None) -> Workflow:
    """Save a shipped-default-shaped workflow (is_system) into the global db."""
    workflow = Workflow(
        name=name or f"Default {uuid4().hex[:8]}",
        description="shipped preset",
        format="nodes",
        is_system=True,
        is_template=True,
        # A minimal VALID graph: the execute route runs preflight validation
        # before accepting, and an empty node list (or an unmapped required
        # port) is a 400. A lone `files` source node has no required inputs.
        nodes=[{"id": "files-source", "tool": "files", "inputs": {}, "config": {}}],
        edges=[],
    )
    global_db.save(workflow)
    return workflow


def _make_global_user_workflow(global_db) -> Workflow:
    """Save a USER workflow into the global library (is_system=False)."""
    workflow = Workflow(
        name=f"My Global Pipeline {uuid4().hex[:8]}",
        format="nodes",
        is_system=False,
        is_template=False,
        nodes=[],
        edges=[],
    )
    global_db.save(workflow)
    return workflow


class TestListMergesGlobalDefaults:
    def test_non_global_library_lists_global_defaults(self, client, global_db):
        default = _make_default(global_db)
        response = client.get("/api/workflows")
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        assert default.id in ids

    def test_global_user_workflows_do_not_leak_into_other_libraries(
        self, client, global_db
    ):
        user_workflow = _make_global_user_workflow(global_db)
        response = client.get("/api/workflows")
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        assert user_workflow.id not in ids

    def test_global_preset_appears_even_when_is_system_flag_dropped(
        self, client, global_db
    ):
        # Regression (#4450): the merge filtered on the mutable is_system flag,
        # which legacy / re-homed global preset rows can lose — then a
        # non-global library offered ZERO defaults (Daniel, live). A row that
        # matches a shipped preset's IDENTITY must still surface even with the
        # flag cleared, and must not be duplicated.
        from fichero_server.workflows.default_workflows import (
            _load_preset_files,
            preset_workflow_id,
        )

        preset = _load_preset_files()[0]
        name = preset["name"]
        flag_dropped = Workflow(
            id=preset_workflow_id(name),
            name=name,
            format="nodes",
            is_system=False,  # the flag the old filter required — gone
            is_template=False,
            folder_path=preset.get("folder_path", "/"),
            nodes=[{"id": "files-source", "tool": "files", "inputs": {}, "config": {}}],
            edges=[],
        )
        global_db.save(flag_dropped)

        response = client.get("/api/workflows")
        assert response.status_code == 200
        matches = [
            i for i in response.json()["items"] if i["id"] == flag_dropped.id
        ]
        assert len(matches) == 1  # present despite the dropped flag, and once

    def test_global_user_workflow_named_like_preset_does_not_leak(
        self, client, global_db
    ):
        # CRITICAL (code review): the (name, folder_path) fallback must be gated
        # on a seeder flag. A workflow a USER authored in the global library,
        # named exactly like a preset and in its folder but carrying NO flags,
        # must NOT leak into other libraries — while a real preset that kept
        # is_template (lost only is_system) still resolves.
        from fichero_server.workflows.default_workflows import _load_preset_files

        presets = _load_preset_files()
        user_row = Workflow(
            name=presets[0]["name"],
            format="nodes",
            is_system=False,
            is_template=False,  # no seeder flag → a user workflow, not a default
            folder_path=presets[0].get("folder_path", "/"),
            nodes=[],
            edges=[],
        )
        global_db.save(user_row)
        # A real preset that lost is_system but kept is_template must still show.
        flagged_preset = Workflow(
            name=presets[1]["name"],
            format="nodes",
            is_system=False,
            is_template=True,
            folder_path=presets[1].get("folder_path", "/"),
            nodes=[{"id": "files-source", "tool": "files", "inputs": {}, "config": {}}],
            edges=[],
        )
        global_db.save(flagged_preset)

        response = client.get("/api/workflows")
        assert response.status_code == 200
        ids = {i["id"] for i in response.json()["items"]}
        assert user_row.id not in ids  # gated out — no seeder flag
        assert flagged_preset.id in ids  # name+folder + is_template → resolves

    def test_library_workflow_of_same_id_wins_over_global_default(
        self, client, db, global_db
    ):
        # A library row and a global default sharing an id must not produce a
        # duplicate entry, and the library's own row is the one returned.
        default = _make_default(global_db)
        local = Workflow(
            id=default.id,
            name="Library-local copy",
            format="nodes",
            nodes=[],
            edges=[],
        )
        db.save(local)
        response = client.get("/api/workflows")
        assert response.status_code == 200
        matches = [i for i in response.json()["items"] if i["id"] == default.id]
        assert len(matches) == 1
        assert matches[0]["name"] == "Library-local copy"


class TestReadFallback:
    def test_get_resolves_default_from_global(self, client, global_db):
        default = _make_default(global_db)
        response = client.get(f"/api/workflows/{default.id}")
        assert response.status_code == 200
        assert response.json()["name"] == default.name

    def test_get_global_user_workflow_stays_404(self, client, global_db):
        user_workflow = _make_global_user_workflow(global_db)
        response = client.get(f"/api/workflows/{user_workflow.id}")
        assert response.status_code == 404

    def test_export_resolves_default_from_global(self, client, global_db):
        default = _make_default(global_db)
        response = client.get(f"/api/workflows/{default.id}/export")
        assert response.status_code == 200
        assert response.json()["name"] == default.name


class TestExecuteFallback:
    def test_execute_resolves_default_from_global(self, client, global_db):
        """The run is accepted: recipe from the app, run pinned to library."""
        default = _make_default(global_db)
        response = client.post(
            "/api/workflow-execution/execute",
            json={"workflow_id": default.id},
        )
        assert response.status_code == 202
        body = response.json()
        assert body["workflow_id"] == default.id
        assert body["workflow_name"] == default.name

    def test_execute_global_user_workflow_stays_404(self, client, global_db):
        user_workflow = _make_global_user_workflow(global_db)
        response = client.post(
            "/api/workflow-execution/execute",
            json={"workflow_id": user_workflow.id},
        )
        assert response.status_code == 404


class TestDuplicateIntoCurrentLibrary:
    def test_duplicate_default_lands_in_current_library_as_editable(
        self, client, db, global_db
    ):
        default = _make_default(global_db)
        response = client.post(f"/api/workflows/{default.id}/duplicate")
        assert response.status_code == 200
        copy_id = response.json()["id"]

        copy = db.get(Workflow, copy_id)
        assert copy is not None, "duplicate must be saved into the CURRENT library"
        assert copy.is_system is False
        # And it never landed in the global library.
        assert global_db.get(Workflow, copy_id) is None


class TestMutationsDoNotFallBack:
    def test_delete_of_global_default_is_404_from_another_library(
        self, client, global_db
    ):
        """A default is not deletable through another library's scope."""
        default = _make_default(global_db)
        response = client.delete(f"/api/workflows/{default.id}")
        assert response.status_code == 404
        assert global_db.get(Workflow, default.id) is not None
