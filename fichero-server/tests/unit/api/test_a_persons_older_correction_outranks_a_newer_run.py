"""A person's correction in the OLDER format outranks a newer machine run (#5222, the SACRED rule).

WHY: before the page model a person's work lived on the result itself -- a transcription they
corrected through `artifact.update`, one marked reviewed, or one a person made (provider "user" or,
in libraries written by earlier versions, "human"). The working pass is the newest MACHINE pass
unless a person chose or touched one. Without these signals, converting an old library (a
collaborator has years of hand-fixed pages) would put the newest machine run in front of every
page a person corrected. If this regresses, the corrected reading silently stops being the page.

Checked on the seam the app reads, before conversion (provisional passes) and after it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from tests.unit.api.test_segment_conversion_action import _artifact, _make_doc, _seam

T0 = datetime(2024, 3, 1, tzinfo=timezone.utc)


def _older_and_newer(db):
    doc = _make_doc(db)
    older = _artifact(db, doc)
    older.created_at = T0
    db.save(older)
    newer = _artifact(db, doc)
    newer.created_at = T0 + timedelta(days=400)
    db.save(newer)
    return doc, older, newer


def _working_source(client, doc_id: str) -> str | None:
    [working] = [p for p in _seam(client, doc_id)["passes"] if p["working"]]
    return working["source_artifact_id"]


def _mark(db, older, how: str) -> None:
    if how == "corrected":
        registry.invoke(db, "artifact.update", {"artifact_id": older.id, "patch": {"content": "fixed by hand"}},
                        ActionContext(actor="historian", library_path=None, is_bootstrap=True))
    elif how == "reviewed":
        older.reviewed = True
        db.save(older)
    else:
        older.provider = how  # "user", or "human" as earlier versions wrote it
        db.save(older)


def test_uncorrected_the_newest_machine_run_is_working(db, client):
    doc, _older, newer = _older_and_newer(db)
    assert _working_source(client, doc.id) == newer.id


@pytest.mark.parametrize("how", ["corrected", "reviewed", "user", "human"])
def test_an_older_result_a_person_worked_on_stays_working_before_and_after_conversion(db, client, how):
    doc, older, _newer = _older_and_newer(db)
    _mark(db, older, how)
    assert _working_source(client, doc.id) == older.id, "before conversion"

    registry.invoke(db, "segment.convert_and_edit", {"document_id": doc.id},
                    ActionContext(actor="system", library_path=None, is_bootstrap=True))
    assert _working_source(client, doc.id) == older.id, "after conversion"


def test_a_correction_the_agent_or_a_run_made_is_not_a_persons(db, client):
    doc, older, newer = _older_and_newer(db)
    registry.invoke(db, "artifact.update", {"artifact_id": older.id, "patch": {"content": "machine rewrite"}},
                    ActionContext(actor="workflow", library_path=None, is_bootstrap=True))
    assert _working_source(client, doc.id) == newer.id
