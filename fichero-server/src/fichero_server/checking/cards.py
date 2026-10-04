"""The check job's cards: what a checker of each layer is shown, and how its answer is read.

`source.check.readings-card` (the palaeographer reviewer), `.claims-card`, `.entities-card`. One proposal
per call; every card asks for the same answer, one JSON object:

    {"verdict": "confirm" | "correct" | "reject", "why": "...", "correction": {...} | null}

A recipe may give its own prompt for a card (`source.recipe.is-a-file`): the same `{...}` fields are
filled in.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fichero_server.models.checking import VERDICTS
from fichero_server.training.reasons import REVIEW
from fichero_server.training.reasons import USE_CASE as REASONS_USE_CASE

REVIEW_USE_CASE = REASONS_USE_CASE[REVIEW]

READINGS_PROMPT = (
    "The image is one line cut from a photographed handwritten page{language}. Here is a reading of it:\n"
    "{reading}\n"
    "Check the reading against the image as a palaeographer. Reply with only a JSON object: "
    '{{"verdict": "confirm" if the reading stands, "correct" if the line reads otherwise, or "reject" if the '
    'image holds no writing or the reading is not of this line; "why": what in the writing shows it; '
    '"correction": {{"text": "the line exactly as written, nothing corrected or modernised"}} when you correct '
    "it, else null}}."
)
CLAIMS_PROMPT = (
    "Here is a statement found in a historical document, and the passage it was found in.\n"
    "Statement: {text}\nSubject: {subject}\nRelation: {relation}\nObject: {object}\nPassage: {excerpt}\n"
    "Check whether the passage says this. Reply with only a JSON object: "
    '{{"verdict": "confirm" if it does, "correct" if it says something close that should be stated '
    'otherwise, or "reject" if it does not; "why": what in the passage shows it; "correction": '
    '{{"text": "...", "subject": "...", "relation": "...", "object": "..."}} when you correct it, else null}}.'
)
ENTITIES_PROMPT = (
    "Here is an entity found in historical documents{language}.\n"
    "Name: {name}\nType: {type}\nOther names: {aliases}\nPassages that mention it:\n{excerpts}\n"
    "Check whether the passages show such an entity under this name and type. Reply with only a JSON object: "
    '{{"verdict": "confirm", "correct" or "reject"; "why": what in the passages shows it; '
    '"correction": {{"name": "...", "type": "..."}} when you correct it, else null}}.'
)
PROMPTS = {"readings": READINGS_PROMPT, "claims": CLAIMS_PROMPT, "entities": ENTITIES_PROMPT}
#: The palaeographer reviewer's episodes are the vision card's `review` lessons (`training.reasons.REVIEW`).
USE_CASE = {"readings": REVIEW_USE_CASE, "claims": "check-claims", "entities": "check-entities"}
#: Passages shown for an entity: enough to judge, few enough to read.
EXCERPTS_PER_ENTITY = 5


@dataclass
class Proposal:
    layer: str
    target_id: str
    document_id: str | None
    fields: dict[str, Any]
    image: str | None = None  # a data URI: the line's picture
    segment_id: str | None = None
    line_id: str | None = None  # the line's PAGE id, for the `review` arm
    shown: str = ""  # the reading checked
    extra: dict[str, Any] = field(default_factory=dict)


def prompt_for(proposal: Proposal, *, template: str | None = None, language: str | None = None) -> str:
    hint = f" (in {language})" if language and language not in ("und", "unknown") else ""
    return (template or PROMPTS[proposal.layer]).format(language=hint, **proposal.fields)


def parse_verdict(raw: str, layer: str) -> dict[str, Any] | None:
    """The checker's answer, or None when it is not the object asked for (the proposal is unanswered)."""
    from fichero_server.training.reasons import split_thinking

    answer, _thinking = split_thinking(raw)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip())
    try:
        item = json.loads(text)
    except ValueError:
        return None
    if not isinstance(item, dict) or item.get("verdict") not in VERDICTS or not isinstance(item.get("why"), str):
        return None
    correction = item.get("correction")
    if item["verdict"] == "correct":
        if not isinstance(correction, dict):
            return None
        if layer == "readings" and not str(correction.get("text") or "").strip():
            return None
    return {"verdict": item["verdict"], "why": item["why"].strip(),
            "correction": correction if item["verdict"] == "correct" else None}


def _descendants(db: Any, scope_ids: list[str]) -> list[Any]:
    from fichero_server.models import Document

    seen: set[str] = set()
    out: list[Any] = []

    def visit(doc: Any) -> None:
        if doc is None or doc.id in seen or getattr(doc, "deleted_at", None):
            return
        seen.add(doc.id)
        out.append(doc)
        for child in sorted(db.query(Document, parent_id=doc.id),
                            key=lambda d: (d.sequence if d.sequence is not None else 1 << 30, d.name or "", d.id)):
            visit(child)

    for doc_id in scope_ids:
        visit(db.get(Document, doc_id))
    return out


def reading_proposals(db: Any, scope_ids: list[str], *, kind: str = "transcription",
                      pass_model: str | None = None) -> tuple[list[Proposal], list[dict[str, str]]]:
    """Each line's counting reading on every page in scope, with the line's picture. The lines are those
    of the page's newest live pass with lines (or of `pass_model`'s newest)."""
    from PIL import Image

    from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
    from fichero_server.formats.harness import xml_id
    from fichero_server.llm.line_reader import _crop_data_uri
    from fichero_server.models import Segment
    from fichero_server.models.segments import SegmentPass
    from fichero_server.page_export import ExportRefused, export_page
    from fichero_server.training.line_pairs import lines_with_ids

    proposals: list[Proposal] = []
    missing: list[dict[str, str]] = []
    for doc in _descendants(db, scope_ids):
        if getattr(doc.doc_type, "value", doc.doc_type) not in ("file", "page"):
            continue
        passes = [p for p in db.query(SegmentPass, document_id=doc.id) if not p.deleted_at
                  and (pass_model is None or p.model == pass_model)]
        lines_by_pass = {p.id: [s for s in db.query(Segment, pass_id=p.id) if s.kind == "line" and not s.deleted_at]
                         for p in passes}
        passes = [p for p in passes if lines_by_pass[p.id]]
        if not passes:
            continue
        chosen = max(passes, key=lambda p: p.created_at)
        photo = Path(doc.path) if doc.path else None
        if photo is None or not photo.is_file():
            missing.append({"document_id": doc.id, "why": "its photograph is not on this Mac"})
            continue
        try:
            outlines = {line_id: polygon for line_id, polygon, _text in lines_with_ids(
                export_page(db, doc.id, "pagexml", pass_id=chosen.id).data.decode("utf-8"))}
        except ExportRefused as exc:
            missing.append({"document_id": doc.id, "why": str(exc)})
            continue
        image = Image.open(photo)
        image.load()
        for segment in lines_by_pass[chosen.id]:
            items = readings_of_segment(db, segment.id)
            counted = counting_by_kind(db, segment.id, items).get(kind)
            reading = next((i for i in items if counted and i.id == counted.representation_id), None)
            polygon = outlines.get(xml_id(segment.id))
            if reading is None or not polygon:
                continue
            proposals.append(Proposal(
                layer="readings", target_id=reading.id, document_id=doc.id,
                fields={"reading": json.dumps(reading.content, ensure_ascii=False)},
                image=_crop_data_uri(image, polygon), segment_id=segment.id, line_id=xml_id(segment.id),
                shown=reading.content,
                extra={"kind": kind, "provisional": reading.provisional,
                       "derived_from_artifact_id": reading.derived_from_artifact_id}))
    return proposals, missing


def claim_proposals(db: Any, scope_ids: list[str]) -> list[Proposal]:
    """The statements found in the documents in scope, live and not merged away."""
    from fichero_server.models.knowledge import KnowledgeClaim

    proposals = []
    for doc in _descendants(db, scope_ids):
        for claim in sorted(db.query(KnowledgeClaim, source_document_id=doc.id), key=lambda c: (c.created_at, c.id)):
            if claim.merged_into_id or getattr(claim, "deleted_at", None):
                continue
            proposals.append(Proposal(layer="claims", target_id=claim.id, document_id=doc.id, fields={
                "text": claim.text, "subject": claim.svo_subject or claim.subject_canonical or "",
                "relation": claim.svo_verb or claim.predicate_verb or "",
                "object": claim.svo_object or claim.object_phrase or "", "excerpt": claim.source_excerpt or ""}))
    return proposals


def entity_proposals(db: Any, scope_ids: list[str], *, language: str | None = None) -> list[Proposal]:
    """The entities named in the documents in scope, or by their statements, with the passages that
    mention them."""
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

    docs = {d.id for d in _descendants(db, scope_ids)}
    claims = [c for doc_id in docs for c in db.query(KnowledgeClaim, source_document_id=doc_id)]
    ids = {e for c in claims for e in c.entity_ids}
    entities = [e for e in db.query(KnowledgeEntity)
                if not e.merged_into_id and (e.id in ids or docs.intersection(e.source_document_ids or []))]
    proposals = []
    for entity in sorted(entities, key=lambda e: (e.canonical_name, e.id)):
        excerpts = [c.source_excerpt for c in claims if entity.id in c.entity_ids and c.source_excerpt]
        proposals.append(Proposal(layer="entities", target_id=entity.id, document_id=None, fields={
            "name": entity.canonical_name, "type": getattr(entity.entity_type, "value", entity.entity_type),
            "aliases": ", ".join(entity.aliases) or "none",
            "excerpts": "\n".join(f"- {e}" for e in excerpts[:EXCERPTS_PER_ENTITY]) or "- none recorded"}))
    return proposals
