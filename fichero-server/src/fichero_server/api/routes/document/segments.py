"""Source-model slice 1 — GET /api/segments/document/{doc_id} (writes nothing).

One engine call that returns a source's segments, whether they still live in
today's ``Artifact.ocr_geometry`` blocks or, once slice 3 lands, in real
``Segment`` records — the caller cannot tell which (`source.one-store`,
`source.seam.read-either-store`). Follows the shape of
``content_representations.py``: a plain read router, no action (this slice
writes nothing so there is nothing to audit).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.models import Artifact, Document, SegmentListResponse
from fichero_server.models.segments import PassRead, legacy_pass_id, segments_from_result

router = APIRouter(prefix="/segments")


@router.get("/document/{doc_id}", response_model=SegmentListResponse)
async def list_document_segments(
    doc_id: str,
    artifact_id: Optional[str] = Query(
        None, description="Restrict to one artifact's boxes"
    ),
    pass_id: Optional[str] = Query(
        None, description="Restrict to one pass (today: legacy:<artifact_id>)"
    ),
    kind: Optional[str] = Query(
        None, description="Restrict to one segment kind (region, line, word, ...)"
    ),
    db: Database = Depends(get_library_database),
) -> SegmentListResponse:
    """The segments of one source page, across whichever of its artifacts
    carry geometry. Opening a page this way writes nothing — the "opening a
    page writes nothing" half of `source.store.ids-on-first-edit` — and a
    document with no geometry yet returns an empty list, not an error.

    **Order.** Passes come back sorted by `(created_at, id)`; segments stay
    in box order within their pass — the order the app's index mapping and
    the route/MCP/CLI parity test both rely on, not "whatever the store
    happened to return".

    **A bad box never fails the page** (`source.seam.read-either-store`):
    a box the anchor cannot hold still comes back as a segment, with its
    rect/polygon unset and the reason in `metadata["geometry_problem"]`
    (`models/segments.py::_build_anchor`).
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    query_kwargs: dict = {"document_id": doc_id}
    if artifact_id:
        query_kwargs["id"] = artifact_id
    artifacts = [a for a in db.query(Artifact, **query_kwargs) if a.ocr_geometry]

    by_pass: list[tuple[Artifact, PassRead, list]] = []
    for artifact in artifacts:
        this_pass_id = legacy_pass_id(artifact.id)
        if pass_id and pass_id != this_pass_id:
            continue
        pass_read, artifact_segments = segments_from_result(
            document_id=doc_id,
            artifact_id=artifact.id,
            result=artifact.ocr_geometry,
            provider=artifact.provider,
            model=artifact.model,
            run_id=artifact.run_id,
            created_at=artifact.created_at,
            artifact_type=artifact.artifact_type,
        )
        if kind:
            artifact_segments = [s for s in artifact_segments if s.kind == kind]
        if not artifact_segments and kind:
            # A kind filter that matched nothing on this artifact still
            # names its pass, once — but naming an EMPTY pass adds noise
            # with no segments behind it, so it is skipped rather than
            # returned with a dangling reference.
            continue
        by_pass.append((artifact, pass_read, artifact_segments))

    # Sort key as a string, not the datetime itself: `created_at` may be
    # `None` (no honest fallback exists), and comparing `None` against a
    # `datetime` raises — an empty string sorts first, which is the right
    # place for "unknown" anyway.
    by_pass.sort(key=lambda entry: (entry[1].created_at.isoformat() if entry[1].created_at else "", entry[1].id))

    passes = [pass_read for _, pass_read, _ in by_pass]
    segments = [segment for _, _, artifact_segments in by_pass for segment in artifact_segments]

    return SegmentListResponse(document_id=doc_id, passes=passes, segments=segments)
