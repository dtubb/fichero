"""#4414 Stage 4: the real Catalogue preset touches its folder and NOTHING else.

The existing harness already runs the unmodified preset through the real graph
with only the model stubbed, so the tools, the DB writes and the wiring are
genuine. What it does not assert is the property #4396 was actually about:

    a run scoped to one folder must leave everything outside it untouched.

#4396 was found by noticing catalogue output on the wrong documents — after
the fact, in real archival data. Nothing in the system objected at the time,
and no test could have caught it, because every existing assertion checks that
the RIGHT things happened and none check that the wrong things did not.

So this seeds a second folder that is never selected, runs the preset on the
first, and asserts the outsider is untouched on every axis the run can write:
entities, claims, artifacts, and page_content. Plus the recorded scope
(#4384) matches the selected folder's descendants exactly — the row that makes
an over-scoped run visible on sight rather than by its effects.

Nothing here skips: the model is stubbed deterministically, everything else is
real.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed
from tests.unit.workflows.test_default_workflow_e2e_harness import (
    FIXTURE_TEXT,
    _install_deterministic_workflow_stubs,
    _load_catalogue_workflow,
)

from fichero_server.db import db_manager
from fichero_server.models import Artifact, DocType, Document, FileType
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.run_scope import resolve_run_scope
from fichero_server.workflows.runtime import build_initial_state


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


@pytest.fixture
def two_folder_library(tmp_path: Path):
    """Two sibling folders. Only the first is ever selected."""
    library_path = tmp_path / "scope-isolation.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    def _folder(folder_id: str, name: str, doc_id: str, filename: str):
        db.save(Document(id=folder_id, name=name, doc_type=DocType.folder))
        source = tmp_path / filename
        source.write_text(FIXTURE_TEXT, encoding="utf-8")
        db.save(
            Document(
                id=doc_id,
                parent_id=folder_id,
                name=filename,
                path=str(source),
                doc_type=DocType.file,
                file_type=FileType.text,
                page_content=FIXTURE_TEXT,
                metadata={"transcription": FIXTURE_TEXT},
            )
        )

    _folder("caja-3", "Caja 3", "caja-3-doc", "caja3.txt")
    _folder("caja-4", "Caja 4", "caja-4-doc", "caja4.txt")
    return library_path, db


def _run_catalogue_on(library_path: Path, selected_doc_id: str, task_id: str):
    workflow = _load_catalogue_workflow()
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]}, library_path=str(library_path)
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = task_id
    return asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))


def _touching(rows, doc_ids: set[str]) -> list:
    """Rows whose source document is in `doc_ids`."""
    out = []
    for row in rows:
        single = getattr(row, "source_document_id", None)
        many = getattr(row, "source_document_ids", None) or []
        if (single and single in doc_ids) or (set(many) & doc_ids):
            out.append(row)
    return out


class TestTheRunProducesItsOwnOutput:
    """Preconditions. If these fail the isolation assertions below are
    vacuous — a run that did nothing touches nothing."""

    def test_the_selected_folder_carries_the_catalogue_artifact(
        self, two_folder_library, monkeypatch
    ):
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, db = two_folder_library
        _run_catalogue_on(library_path, "caja-3", "iso-run-1")

        artifacts = [
            a for a in db.all(Artifact)
            if a.document_id == "caja-3"
            and (a.artifact_type == "catalogue" or a.artifact_type.startswith("catalogue."))
        ]
        assert artifacts, (
            "the folder-level catalogue did not land on the folder document — "
            "folder-level output has nowhere to live (#4397/#4414)"
        )

    def test_entities_and_claims_land_for_the_selected_folder(
        self, two_folder_library, monkeypatch
    ):
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, db = two_folder_library
        _run_catalogue_on(library_path, "caja-3", "iso-run-2")

        inside = {"caja-3", "caja-3-doc"}
        assert _touching(db.all(KnowledgeEntity), inside), "no entities for the run"
        assert _touching(db.all(KnowledgeClaim), inside), "no claims for the run"


class TestNothingOutsideTheSelectionIsTouched:
    """The #4396 property, asserted directly for the first time."""

    def test_the_unselected_folder_gets_no_entities_or_claims(
        self, two_folder_library, monkeypatch
    ):
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, db = two_folder_library
        _run_catalogue_on(library_path, "caja-3", "iso-run-3")

        outside = {"caja-4", "caja-4-doc"}
        stray_entities = _touching(db.all(KnowledgeEntity), outside)
        stray_claims = _touching(db.all(KnowledgeClaim), outside)

        assert stray_entities == [], (
            "a run scoped to Caja 3 wrote entities against Caja 4 — this is "
            f"#4396: {[e.canonical_name for e in stray_entities]}"
        )
        assert stray_claims == [], (
            f"a run scoped to Caja 3 wrote {len(stray_claims)} claim(s) "
            "against Caja 4 (#4396)"
        )

    def test_the_unselected_folder_gets_no_artifacts(
        self, two_folder_library, monkeypatch
    ):
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, db = two_folder_library
        _run_catalogue_on(library_path, "caja-3", "iso-run-4")

        stray = [
            a for a in db.all(Artifact)
            if a.document_id in {"caja-4", "caja-4-doc"}
        ]
        assert stray == [], (
            "artifacts landed on the unselected folder: "
            f"{sorted({a.artifact_type for a in stray})}"
        )

    def test_the_unselected_folder_keeps_its_page_content(
        self, two_folder_library, monkeypatch
    ):
        """Catalogue OVERWRITES the container's page_content with the
        narrative. On the wrong container that silently destroys content."""
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, db = two_folder_library
        before = db.get(Document, "caja-4").page_content

        _run_catalogue_on(library_path, "caja-3", "iso-run-5")

        assert db.get(Document, "caja-4").page_content == before, (
            "the unselected folder's page_content was overwritten by a run "
            "scoped elsewhere (#4396)"
        )
        assert db.get(Document, "caja-4-doc").page_content == FIXTURE_TEXT


class TestTheRecordedScopeMatchesTheSelection:
    """#4384: the row that makes an over-scoped run visible on sight."""

    def test_scope_resolves_to_exactly_the_folder_descendants(
        self, two_folder_library
    ):
        _library_path, db = two_folder_library
        scope = resolve_run_scope(db, ["caja-3"])

        assert scope["requested_ids"] == ["caja-3"]
        assert scope["resolved_ids"] == ["caja-3-doc"]
        assert scope["resolved_count"] == 1
        assert scope["kinds"] == {"caja-3": "folder"}

    def test_scope_never_reaches_the_sibling_folder(self, two_folder_library):
        _library_path, db = two_folder_library
        scope = resolve_run_scope(db, ["caja-3"])

        assert "caja-4" not in scope["resolved_ids"]
        assert "caja-4-doc" not in scope["resolved_ids"], (
            "the recorded scope claims documents the run must never touch — "
            "the record would corroborate an over-scoped run instead of "
            "exposing it (#4384/#4396)"
        )
