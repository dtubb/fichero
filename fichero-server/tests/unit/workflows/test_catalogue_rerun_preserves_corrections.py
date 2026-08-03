"""A Catalogue re-run must not destroy the user's corrections (#4415 wiring).

#4415 built the curation guard and wired it to ``merge_dedup_only``. Catalogue
— the flagship path — never called it. So the guard existed, its tests passed,
and the tool the issue actually named went on destroying corrections:

- every ``catalogue.*`` artifact on the container is **hard-deleted** at the
  top of each save, so a corrected narrative is not overwritten but removed;
- ``container.page_content`` is overwritten directly, bypassing the
  ``page_content_user_edited_at`` guard that ``llm_base`` honours for pages.

That is worse than #4499's duplicate: a duplicate is visible and recoverable,
this leaves nothing behind. It is the #1 bar in #4421 — nothing she does may
destroy her material.

These tests drive the REAL shipped preset through the REAL runner (#4414's
harness), because a test against ``merge_dedup_only`` is exactly what made
this invisible: what a component does is not what the configured thing does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.workflows.test_catalogue_real_preset_run_e2e import (
    _run_through_the_runner,
    two_folder_library,  # noqa: F401 — fixture re-export
)
from tests.unit.workflows.test_default_workflow_e2e_harness import (
    _install_deterministic_workflow_stubs,
)

from fichero_server.db import db_manager
from fichero_server.models import Artifact
from fichero_server.workflows.selection import SelectionKind, WorkflowSelection

import fichero_server.workflows.tools  # noqa: F401


CORRECTION = "Firmado por Ocampo, no por Ospina. — corregido a mano"


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


def _run(library_path: Path, thread_id: str) -> None:
    _run_through_the_runner(
        library_path,
        thread_id,
        WorkflowSelection(kind=SelectionKind.folder, ids=["caja-3"]),
    )


def _catalogue_artifacts(db) -> list[Artifact]:
    return [
        a
        for a in db.all(Artifact)
        if a.document_id == "caja-3"
        and (a.artifact_type == "catalogue" or a.artifact_type.startswith("catalogue."))
    ]


def _correct_artifact(library_path: Path, artifact_id: str) -> None:
    """Edit an artifact the way the app does — through the audited action."""
    from fichero_server.actions.registry import ActionContext, registry

    db = db_manager.get_database(library_path)
    registry.invoke(
        db,
        "artifact.update",
        {"artifact_id": artifact_id, "patch": {"content": CORRECTION}},
        ActionContext(actor="ann", library_path=str(library_path)),
    )


def test_a_rerun_does_not_delete_a_corrected_catalogue_artifact(
    two_folder_library, monkeypatch  # noqa: F811
):
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library

    _run(library_path, "catalogue-correction-first")
    produced = _catalogue_artifacts(db)
    assert produced, (
        "the first run produced no catalogue artifacts, so 'the correction "
        "survived' would be vacuous"
    )
    narrative = next(
        (a for a in produced if a.artifact_type == "catalogue.narrative"), produced[0]
    )
    _correct_artifact(library_path, narrative.id)

    _run(library_path, "catalogue-correction-second")

    db = db_manager.get_database(library_path)
    surviving = db.get(Artifact, narrative.id)
    assert surviving is not None, (
        "the re-run DELETED the artifact the user had corrected. Catalogue "
        "sweeps every catalogue.* row off the container before saving, and "
        "does not ask whether a person had touched one (#4415 unwired)"
    )
    assert surviving.content == CORRECTION, (
        "the artifact survived but her text did not"
    )


def test_a_rerun_does_not_overwrite_corrected_container_page_content(
    two_folder_library, monkeypatch  # noqa: F811
):
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library

    _run(library_path, "catalogue-page-content-first")

    from fichero_server.actions.registry import ActionContext, registry

    db = db_manager.get_database(library_path)
    registry.invoke(
        db,
        "document.update",
        {"doc_id": "caja-3", "update": {"page_content": CORRECTION}},
        ActionContext(actor="ann", library_path=str(library_path)),
    )

    _run(library_path, "catalogue-page-content-second")

    db = db_manager.get_database(library_path)
    from fichero_server.models import Document

    folder = db.get(Document, "caja-3")
    assert folder.page_content == CORRECTION, (
        "the re-run overwrote page_content the user had edited. llm_base "
        "honours metadata['page_content_user_edited_at'] for pages; catalogue "
        "writes container.page_content directly and never checks it"
    )


def test_the_reruns_version_is_recorded_beside_her_correction(
    two_folder_library, monkeypatch  # noqa: F811
):
    """Declining to overwrite is only half of it. A candidate the user never
    sees is a fact destroyed just as surely as one that was deleted."""
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library

    _run(library_path, "catalogue-conflict-first")
    narrative = next(
        a for a in _catalogue_artifacts(db) if a.artifact_type == "catalogue.narrative"
    )
    original_machine_text = narrative.content
    _correct_artifact(library_path, narrative.id)

    _run(library_path, "catalogue-conflict-second")

    db = db_manager.get_database(library_path)
    from fichero_server.workflows.curation_guard import has_conflict

    kept = db.get(Artifact, narrative.id)
    assert has_conflict(kept), (
        "her artifact survived but the re-run's disagreeing version was "
        "dropped without trace — silently resolving in her favour is still "
        "resolving behind her back"
    )
    conflict = kept.data["curation"]["extraction_conflict"]
    assert conflict["proposal"]["artifact_type"] == "catalogue.narrative"
    assert conflict["proposal"]["content"] is not None
    assert original_machine_text is not None


def test_a_workflow_actors_edit_is_not_mistaken_for_a_correction(
    two_folder_library, monkeypatch  # noqa: F811
):
    """The pipeline drives audited routes with actor='workflow'. If that read
    as curation, Catalogue would freeze its own output after one run and
    report the machine's text as the historian's."""
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library

    _run(library_path, "catalogue-machine-actor-first")
    narrative = next(
        a for a in _catalogue_artifacts(db) if a.artifact_type == "catalogue.narrative"
    )

    from fichero_server.actions.registry import ActionContext, registry

    db = db_manager.get_database(library_path)
    registry.invoke(
        db,
        "artifact.update",
        {"artifact_id": narrative.id, "patch": {"content": "machine rewrite"}},
        ActionContext(actor="workflow", library_path=str(library_path)),
    )

    _run(library_path, "catalogue-machine-actor-second")

    db = db_manager.get_database(library_path)
    assert db.get(Artifact, narrative.id) is None, (
        "an edit by the pipeline's own actor was treated as a human "
        "correction, so the tool now protects its own output from itself"
    )


def test_a_corrected_cleanup_artifact_survives_the_same_rerun(
    two_folder_library, monkeypatch  # noqa: F811
):
    """The six folder-cleanup nodes run INSIDE this preset and had the same
    unconditional delete. Fixing only catalogue.* would leave the same run
    destroying `people_clean` on its way past."""
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library

    _run(library_path, "cleanup-correction-first")
    clean = [
        a
        for a in db.all(Artifact)
        if a.document_id == "caja-3" and (a.artifact_type or "").endswith("_clean")
    ]
    assert clean, "no <type>_clean artifact produced, so this proves nothing"
    target = clean[0]
    _correct_artifact(library_path, target.id)

    _run(library_path, "cleanup-correction-second")

    db = db_manager.get_database(library_path)
    surviving = db.get(Artifact, target.id)
    assert surviving is not None, (
        f"the re-run deleted the corrected {target.artifact_type} artifact"
    )
    assert surviving.content == CORRECTION


def test_uncorrected_cleanup_artifacts_still_do_not_accumulate(
    two_folder_library, monkeypatch  # noqa: F811
):
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library

    _run(library_path, "cleanup-no-accumulate-first")
    _run(library_path, "cleanup-no-accumulate-second")

    db = db_manager.get_database(library_path)
    counts: dict[str, int] = {}
    for a in db.all(Artifact):
        if a.document_id == "caja-3" and (a.artifact_type or "").endswith("_clean"):
            counts[a.artifact_type] = counts.get(a.artifact_type, 0) + 1
    duplicated = {t: n for t, n in counts.items() if n > 1}
    assert not duplicated, f"cleanup output accumulated across re-runs: {duplicated}"


def test_uncorrected_catalogue_artifacts_still_do_not_accumulate(
    two_folder_library, monkeypatch  # noqa: F811
):
    """The deletion exists for a real reason. Machine output must still be
    swept, or the fix trades destroyed corrections for duplicate noise."""
    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, db = two_folder_library

    _run(library_path, "catalogue-no-accumulate-first")
    first = {a.artifact_type for a in _catalogue_artifacts(db)}
    assert first, "no catalogue artifacts produced at all"

    _run(library_path, "catalogue-no-accumulate-second")

    db = db_manager.get_database(library_path)
    after = _catalogue_artifacts(db)
    by_type: dict[str, int] = {}
    for a in after:
        by_type[a.artifact_type] = by_type.get(a.artifact_type, 0) + 1
    duplicated = {t: n for t, n in by_type.items() if n > 1}
    assert not duplicated, (
        f"untouched machine output accumulated across re-runs: {duplicated}"
    )
