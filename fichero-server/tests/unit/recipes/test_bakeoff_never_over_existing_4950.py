"""`source.try.never-over-existing` (#4950): a bake-off changes nothing that exists.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: "Try Another Option" must be safe to press
on a project that already holds corrected pages: an alternative runs as a job and its scores are kept beside the model,
and "nothing existing changes". Driven through the real bake-off routes and the job as the scheduler runs it (the harness of
`test_bakeoff_readers.py`; Kraken faked at its seam): the pages, their segments, readings, passes and text are the same
before and after.
"""
from __future__ import annotations

from fichero_server.models import Artifact, ContentRepresentation, Document
from fichero_server.models.segments import SegmentPass
from tests.unit.recipes.test_bakeoff_readers import (  # noqa: F401  (fixtures and helpers)
    _corrected, _run, _set_up, folder, readers,
)


def _snapshot(db) -> dict:
    """Every row a person could have: documents (with their text), artifacts, readings, passes."""
    return {
        "documents": sorted((d.id, d.name, d.page_content, str(d.metadata)) for d in db.query(Document)),
        "artifacts": sorted((a.id, a.artifact_type, a.content) for a in db.query(Artifact)),
        "readings": sorted((r.id, str(r.model_dump())) for r in db.query(ContentRepresentation)),
        "passes": sorted((p.id, str(p.model_dump())) for p in db.query(SegmentPass)),
    }


def test_a_bakeoff_changes_nothing_that_exists(client, db, tmp_path, folder, readers, with_material):
    """source.try.never-over-existing: "nothing existing changes"."""
    _set_up(client)
    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    before = _snapshot(db)
    assert before["readings"], "the corrected pages carry readings"

    _run(client, db)

    assert _snapshot(db) == before
