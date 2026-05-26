"""HTML knowledge-surface routes for document reading panes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
from fichero.models import DocType, Document

router = APIRouter(prefix="/view", tags=["views"])

_TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


def _json_for_script(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _page_number(page_label: str | None) -> int | None:
    if not page_label:
        return None
    digits = "".join(ch for ch in page_label if ch.isdigit())
    return int(digits) if digits else None


def _transcript_for_document(db: Database, document: Document) -> str:
    if document.page_content:
        return document.page_content

    child_pages = [
        doc
        for doc in db.all(Document)
        if doc.parent_id == document.id and doc.doc_type == DocType.page
    ]
    child_pages.sort(key=lambda doc: (doc.sequence or 0, doc.name))

    chunks: list[str] = []
    for page in child_pages:
        if page.page_content:
            label = page.sequence or "?"
            chunks.append(f"Page {label}\n{page.page_content}")
    return "\n\n".join(chunks)


@router.get("/document/{doc_id}", response_class=HTMLResponse)
async def document_view(
    request: Request,
    doc_id: str,
    db: Database = Depends(get_library_database),
) -> HTMLResponse:
    document = db.get(Document, doc_id)
    if document is None:
        raise HTTPException(404, f"Document not found: {doc_id}")

    claims = [
        claim for claim in db.query(KnowledgeClaim)
        if claim.source_document_id == doc_id
    ]

    entity_ids = sorted({entity_id for claim in claims for entity_id in (claim.entity_ids or [])})
    entities = [db.get(KnowledgeEntity, entity_id) for entity_id in entity_ids]
    entities = [entity for entity in entities if entity is not None]
    entities_by_id = {entity.id: entity for entity in entities}

    transcript = _transcript_for_document(db, document)

    document_payload = {
        "id": document.id,
        "name": document.name,
        "doc_type": document.doc_type.value,
        "file_type": document.file_type.value if document.file_type else None,
        "page_content": transcript,
    }
    entity_payload = [
        {
            "id": entity.id,
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type.value,
            "aliases": list(entity.aliases or []),
        }
        for entity in entities
    ]
    claim_payload = [
        {
            "id": claim.id,
            "text": claim.text,
            "source_document_id": claim.source_document_id,
            "source_page_label": claim.source_page_label,
            "page_number": _page_number(claim.source_page_label),
            "source_excerpt": claim.source_excerpt,
            "source_char_start": claim.source_char_start,
            "source_char_end": claim.source_char_end,
            "entity_ids": list(claim.entity_ids or []),
            "subject_canonical": claim.subject_canonical,
            "predicate_verb": claim.predicate_verb,
            "object_phrase": claim.object_phrase,
            "entity_names": [
                entities_by_id[entity_id].canonical_name
                for entity_id in (claim.entity_ids or [])
                if entity_id in entities_by_id
            ],
        }
        for claim in claims
    ]

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="document_view.html",
        context={
            "document": document,
            "transcript": transcript,
            "document_json": _json_for_script(document_payload),
            "entities_json": _json_for_script(entity_payload),
            "claims_json": _json_for_script(claim_payload),
        },
    )
