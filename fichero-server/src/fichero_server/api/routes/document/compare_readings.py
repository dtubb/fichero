"""Scoring one reading of a page against another (#5389).

`transcription_accuracy.character_error_rate` (#3905) is the one CER in Fichero, with its definition
and normalisation policies. This route lets any surface reach it: a pass against a pass, a pass
against a run's transcription, either way round. Read-only.

Agreement is not accuracy: with no checked reference, the number says how far two readings differ,
not which is right. So the answer is labelled `agreement` unless the caller names who checked the
reference (`reference_checked_by`), and only then `cer`. A gold text with no attribution is an
anonymous opinion (the same rule `ReferenceTranscription` keeps).
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.models import Artifact, Document
from fichero_server.workflows.run_comparison import RunComparisonError
from fichero_server.workflows.transcription_accuracy import (
    DEFAULT_POLICY_NAME,
    POLICIES,
    character_error_rate,
)

router = APIRouter(prefix="/documents")


class ReadingRef(BaseModel):
    """One reading of the page: a pass, or a saved result (artifact)."""

    pass_id: Optional[str] = None
    artifact_id: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "ReadingRef":
        if bool(self.pass_id) == bool(self.artifact_id):
            raise ValueError("name exactly one of pass_id or artifact_id")
        return self


class CompareReadingsRequest(BaseModel):
    reference: ReadingRef
    hypothesis: ReadingRef
    policies: list[str] = Field(default_factory=lambda: [DEFAULT_POLICY_NAME],
                                description=f"normalisation policies: {', '.join(sorted(POLICIES))}")
    reference_checked_by: Optional[str] = Field(
        default=None, description="who checked the reference; without it the score is agreement, not CER")


class ReadingScore(BaseModel):
    policy: str
    policy_description: str
    distance: int
    reference_chars: int
    hypothesis_chars: int
    rate: float


class CompareReadingsResponse(BaseModel):
    measure: Literal["agreement", "cer"]
    reference_label: str
    hypothesis_label: str
    definition: str
    scores: list[ReadingScore]


def _reading(db: Database, document_id: str, ref: ReadingRef) -> tuple[str, str]:
    """(text, label) of one reading; 404 when it is not this page's."""
    if ref.pass_id:
        from fichero_server.api.routes.document.segment_readings import document_text
        from fichero_server.models import SegmentPass

        p = db.get(SegmentPass, ref.pass_id)
        if p is None or p.document_id != document_id:
            raise HTTPException(status_code=404, detail=f"pass {ref.pass_id} is not on this page")
        label = " / ".join(x for x in (p.name, p.provider, p.model) if x)
        return document_text(db, document_id, pass_id=p.id).text, f"pass: {label}"
    a = db.get(Artifact, ref.artifact_id)
    if a is None or a.document_id != document_id:
        raise HTTPException(status_code=404, detail=f"result {ref.artifact_id} is not on this page")
    return a.content or "", f"result: {' / '.join(x for x in (a.artifact_type, a.provider, a.model) if x)}"


@router.post("/{document_id}/readings/compare", response_model=CompareReadingsResponse)
async def compare_readings(
    document_id: str,
    request: CompareReadingsRequest,
    db: Database = Depends(get_library_database),
) -> CompareReadingsResponse:
    """How far one reading of this page is from another, by Fichero's CER definition, under each
    normalisation policy asked for. Labelled `agreement` unless `reference_checked_by` names who
    checked the reference. Refuses (422) rather than returning a number it cannot stand behind:
    an empty reference, an unknown policy, a text too long for an exact score."""
    if db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    ref_text, ref_label = _reading(db, document_id, request.reference)
    hyp_text, hyp_label = _reading(db, document_id, request.hypothesis)
    try:
        scores = [character_error_rate(ref_text, hyp_text, policy=p) for p in request.policies]
    except RunComparisonError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    checked = bool(request.reference_checked_by and request.reference_checked_by.strip())
    return CompareReadingsResponse(
        measure="cer" if checked else "agreement",
        reference_label=ref_label + (f" (checked by {request.reference_checked_by.strip()})" if checked else ""),
        hypothesis_label=hyp_label,
        definition=scores[0].definition,
        scores=[ReadingScore(policy=s.policy, policy_description=s.policy_description, distance=s.distance,
                             reference_chars=s.reference_chars, hypothesis_chars=s.hypothesis_chars, rate=s.cer)
                for s in scores],
    )
