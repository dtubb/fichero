"""Mixed-type KG search — claims + entities + notes + annotations.

Single endpoint returns hits across every KG row type so the
SwiftUI search bar can show a unified result list. Each hit
carries its type so the UI renders the right preview cell.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    Annotation,
    KnowledgeClaim,
    KnowledgeEntity,
    Note,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg/search")


HitType = Literal["entity", "claim", "note", "annotation"]


class KGSearchHit(BaseModel):
    """One mixed-type hit."""
    hit_type: HitType
    id: str
    title: str
    snippet: str
    score: float  # 0-1 substring match strength
    document_id: str | None = None
    entity_id: str | None = None


class KGSearchResponse(BaseModel):
    query: str
    hits: list[KGSearchHit]
    counts: dict[str, int]  # per-type result counts


@router.get(
    "",
    response_model=KGSearchResponse,
    summary="Mixed-type KG search — one call, hits across entities + claims + notes + annotations",
)
async def search_kg(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    types: list[HitType] | None = Query(
        default=None,
        description=(
            "Filter to specific row types — pass repeated 'types' "
            "params. Defaults to all four when omitted."
        ),
    ),
    db: Database = Depends(get_library_database),
) -> KGSearchResponse:
    needle = q.lower()
    requested = set(types) if types else {"entity", "claim", "note", "annotation"}
    hits: list[KGSearchHit] = []
    counts: dict[str, int] = {"entity": 0, "claim": 0, "note": 0, "annotation": 0}

    if "entity" in requested:
        for e in db.query(KnowledgeEntity):
            name = (e.canonical_name or "").lower()
            aliases = " ".join(e.aliases or []).lower()
            description = (e.description or "").lower()
            if needle in name or needle in aliases or needle in description:
                hits.append(KGSearchHit(
                    hit_type="entity",
                    id=e.id,
                    title=e.canonical_name,
                    snippet=e.description or ", ".join(e.aliases or []),
                    score=_score(needle, name + " " + aliases + " " + description),
                    entity_id=e.id,
                ))
                counts["entity"] += 1

    if "claim" in requested:
        for c in db.query(KnowledgeClaim):
            text = (c.text or "").lower()
            excerpt = (c.source_excerpt or "").lower()
            if needle in text or needle in excerpt:
                hits.append(KGSearchHit(
                    hit_type="claim",
                    id=c.id,
                    title=c.text[:120],
                    snippet=c.source_excerpt or c.text[:200],
                    score=_score(needle, text + " " + excerpt),
                    document_id=c.source_document_id,
                ))
                counts["claim"] += 1

    if "note" in requested:
        for n in db.query(Note):
            title = (n.title or "").lower()
            body = (n.body or "").lower()
            tags = " ".join(n.tags or []).lower()
            if needle in title or needle in body or needle in tags:
                hits.append(KGSearchHit(
                    hit_type="note",
                    id=n.id,
                    title=n.title or _first_line(n.body),
                    snippet=_snippet_around(n.body, needle),
                    score=_score(needle, title + " " + body + " " + tags),
                ))
                counts["note"] += 1

    if "annotation" in requested:
        for a in db.query(Annotation):
            text = (a.text or "").lower()
            tags = " ".join(a.tags or []).lower()
            if needle in text or needle in tags:
                hits.append(KGSearchHit(
                    hit_type="annotation",
                    id=a.id,
                    title=f"[{a.kind.value}] {(a.text or '')[:80]}",
                    snippet=a.text or "",
                    score=_score(needle, text + " " + tags),
                    document_id=a.document_id,
                ))
                counts["annotation"] += 1

    hits.sort(key=lambda h: -h.score)
    return KGSearchResponse(query=q, hits=hits[:limit], counts=counts)


def _score(needle: str, haystack: str) -> float:
    """Cheap relevance — relative frequency + position weighting.

    The first match nearest the start of the haystack scores best.
    No real ranking model; that's the search v2 work (#736). This
    is just better than alphabetical.
    """
    if not haystack:
        return 0.0
    haystack = haystack.lower()
    idx = haystack.find(needle)
    if idx < 0:
        return 0.0
    position_score = 1.0 - (idx / max(len(haystack), 1)) * 0.5  # 0.5-1.0
    count = haystack.count(needle)
    return min(1.0, position_score * (1 + 0.1 * (count - 1)))


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    return text.splitlines()[0][:120] if text else ""


def _snippet_around(text: str | None, needle: str, window: int = 80) -> str:
    """Show ``window`` chars around the first match of ``needle``."""
    if not text:
        return ""
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return text[:200]
    start = max(0, idx - window)
    end = min(len(text), idx + len(needle) + window)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet
