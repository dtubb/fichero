"""HTML knowledge-surface routes for document reading panes."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.models import DocType, Document

router = APIRouter(prefix="/view", tags=["views"])

_TEMPLATES = None
_GLOBAL_KG_LIMIT = 250


def _templates():
    """Build the Jinja2 environment on first render (#3985).

    Importing jinja2 (via Jinja2Templates) at module scope put it and
    markupsafe on the engine boot path — api.main imports every route module to
    register routers, but templates are only needed when an HTML view actually
    renders.
    """
    global _TEMPLATES
    if _TEMPLATES is None:
        from fastapi.templating import Jinja2Templates

        _TEMPLATES = Jinja2Templates(
            # parents[2]: routes/system/views.py -> routes/system -> routes -> api (#2569)
            directory=str(Path(__file__).resolve().parents[2] / "templates")
        )
    return _TEMPLATES


def _json_for_script(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _page_number(page_label: str | None) -> int | None:
    if not page_label:
        return None
    digits = "".join(ch for ch in page_label if ch.isdigit())
    return int(digits) if digits else None


def _page_children(db: Database, document: Document) -> list[Document]:
    """This document's page children in their real sequence."""
    child_pages = db.query(Document, parent_id=document.id, doc_type=DocType.page)
    child_pages.sort(key=lambda doc: (doc.sequence or 0, doc.name))
    return child_pages


def transcript_pages(document: Document, child_pages: list[Document]) -> list[dict[str, object]]:
    """Every page of the document, in order — including pages with NO content.

    The reader used to be built from the assembled transcript text, which only
    carried pages that had `page_content`. Untranscribed pages vanished, so
    "page 5" in the reader was a different page than "page 5" in the preview and
    every cross-pane action (find match, transcribe this page, jump to page)
    pointed at the wrong sheet (#4356). The page list is now the document's page
    CHILDREN: an empty page is a page with empty content, never a gap.

    Pure over the loaded documents so the ordering + empty-page rule are
    unit-testable without a database.
    """
    from fichero_server.loaders.document_loader import _strip_rtf

    if not child_pages:
        # A leaf document (or a single page) is its own one-page transcript.
        content = _strip_rtf(document.page_content) if document.page_content else ""
        if not content.strip():
            return []
        return [
            {
                "id": document.id,
                "number": document.sequence or 1,
                "label": document.name,
                "content": content,
                "has_content": True,
            }
        ]

    pages: list[dict[str, object]] = []
    for index, page in enumerate(child_pages, start=1):
        content = _strip_rtf(page.page_content) if page.page_content else ""
        pages.append(
            {
                "id": page.id,
                "number": page.sequence or index,
                "label": page.name,
                "content": content,
                "has_content": bool(content.strip()),
            }
        )
    return pages


def transcript_text(pages: list[dict[str, object]]) -> str:
    """The flat "Page N\\n…" transcript, carrying only pages WITH content.

    Deliberately unchanged by #4356: claim `source_char_start`/`source_char_end`
    offsets index into this string, so inserting empty pages here would shift
    every stored offset. The reader renders from the structured page list; this
    text stays the offset-stable reading of the same document.
    """
    return "\n\n".join(
        f"Page {page['number']}\n{page['content']}"
        for page in pages
        if page["has_content"]
    )


def _strip_document_rtf(content: str) -> str:
    from fichero_server.loaders.document_loader import _strip_rtf

    return _strip_rtf(content)


def _claim_payload(
    claims: list[KnowledgeClaim],
    entities_by_id: dict[str, KnowledgeEntity],
) -> list[dict[str, object]]:
    return [
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
            "subject_entity_id": claim.subject_entity_id,
            "subject_canonical": claim.subject_canonical,
            "predicate_verb": claim.predicate_verb,
            "object_phrase": claim.object_phrase,
            "time_start": claim.time_start,
            "time_end": claim.time_end,
            "time_precision": claim.time_precision,
            "confidence_source": claim.confidence_source,
            "claim_location": claim.claim_location,
            "claim_geo": (
                {
                    "lat": claim.claim_geo.lat,
                    "lon": claim.claim_geo.lon,
                    "precision_m": claim.claim_geo.precision_m,
                    "place_name": claim.claim_geo.place_name,
                }
                if claim.claim_geo
                else None
            ),
            "date_values": [
                {
                    "id": value.id,
                    "start": value.start,
                    "end": value.end,
                    "label": value.label,
                    "precision": value.precision,
                    "basis": value.basis.value,
                    "confidence": value.confidence,
                }
                for value in (claim.date_values or [])
            ],
            "place_values": [
                {
                    "id": value.id,
                    "label": value.label,
                    "lat": value.lat,
                    "lon": value.lon,
                    "precision_m": value.precision_m,
                    "geometry_type": value.geometry_type.value,
                    "basis": value.basis.value,
                    "confidence": value.confidence,
                    "places": list(value.places or []),
                }
                for value in (claim.place_values or [])
            ],
            "entity_names": [
                entities_by_id[entity_id].canonical_name
                for entity_id in (claim.entity_ids or [])
                if entity_id in entities_by_id
            ],
        }
        for claim in claims
    ]


def _document_scoped_entities(
    db: Database, doc_ids: set[str], claims: list[KnowledgeClaim]
) -> list[KnowledgeEntity]:
    entity_ids = {
        entity_id
        for claim in claims
        for entity_id in (claim.entity_ids or [])
    }
    entity_ids.update(db.knowledge_entity_ids_scoped_to_documents(doc_ids))
    scoped = db.query_in(KnowledgeEntity, "id", sorted(entity_ids))
    scoped.sort(key=lambda entity: entity.canonical_name.lower())
    return scoped


@router.get("/document/{doc_id}", response_class=HTMLResponse)
async def document_view(
    request: Request,
    doc_id: str,
    db: Database = Depends(get_library_database),
) -> HTMLResponse:
    document = db.get(Document, doc_id)
    if document is None:
        raise HTTPException(404, f"Document not found: {doc_id}")

    from fichero_server.api.routes.claim.claims import _descendant_doc_ids

    # Per-page PDFs store claims on children, so scope the graph to the full
    # document subtree and let query_in filter before hydration (#3224).
    doc_scope = _descendant_doc_ids(db, doc_id)
    claims = db.query_in(KnowledgeClaim, "source_document_id", doc_scope)

    entities = _document_scoped_entities(db, doc_scope, claims)
    entities_by_id = {entity.id: entity for entity in entities}

    pages = transcript_pages(document, _page_children(db, document))
    transcript = (
        _strip_document_rtf(document.page_content)
        if document.page_content
        else transcript_text(pages)
    )

    document_payload = {
        "id": document.id,
        "name": document.name,
        "doc_type": document.doc_type.value,
        "file_type": document.file_type.value if document.file_type else None,
        "page_content": transcript,
        # Every page in sequence, empty ones included (#4356) — the reader
        # renders this list, so reader page N is preview page N.
        "pages": pages,
    }
    entity_payload = [
        {
            "id": entity.id,
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type.value,
            "aliases": list(entity.aliases or []),
            "date_values": [
                {
                    "id": value.id,
                    "start": value.start,
                    "end": value.end,
                    "label": value.label,
                    "precision": value.precision,
                    "basis": value.basis.value,
                    "confidence": value.confidence,
                }
                for value in (entity.date_values or [])
            ],
            "place_values": [
                {
                    "id": value.id,
                    "label": value.label,
                    "lat": value.lat,
                    "lon": value.lon,
                    "precision_m": value.precision_m,
                    "geometry_type": value.geometry_type.value,
                    "basis": value.basis.value,
                    "confidence": value.confidence,
                    "places": list(value.places or []),
                }
                for value in (entity.place_values or [])
            ],
            "source_document_ids": list(entity.source_document_ids or []),
            "metadata": dict(entity.metadata or {}),
        }
        for entity in entities
    ]
    claim_payload = _claim_payload(claims, entities_by_id)

    return _templates().TemplateResponse(
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


@router.get("/kg/global", response_class=HTMLResponse)
async def global_kg_view(
    request: Request,
    db: Database = Depends(get_library_database),
) -> HTMLResponse:
    """Render the shared KG web pane without document scoping.

    Used by OntologyBrowser graph mode so sidebar + inspector run through the
    same WebKit renderer path.
    """
    entity_count = db.count(KnowledgeEntity)
    claim_count = db.count(KnowledgeClaim)
    entities = db.query_page(KnowledgeEntity, limit=_GLOBAL_KG_LIMIT)
    entities_by_id = {entity.id: entity for entity in entities}
    claims = db.query_page(KnowledgeClaim, limit=_GLOBAL_KG_LIMIT)

    document_payload = {
        "id": "__kg_global__",
        "name": "Knowledge Graph",
        "doc_type": "kg",
        "file_type": None,
        "page_content": "",
        "pages": [],
        "graph_summary": {
            "shown_entities": len(entities),
            "total_entities": entity_count,
            "shown_claims": len(claims),
            "total_claims": claim_count,
        },
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
    claim_payload = _claim_payload(claims, entities_by_id)

    return _templates().TemplateResponse(
        request=request,
        name="document_view.html",
        context={
            "document": SimpleNamespace(name="Knowledge Graph"),
            "transcript": "",
            "document_json": _json_for_script(document_payload),
            "entities_json": _json_for_script(entity_payload),
            "claims_json": _json_for_script(claim_payload),
        },
    )
