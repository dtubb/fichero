"""Source-model slice 10 (#4931) — writing and reading the one typed link.

Spec: `build-notes-readings-cascade-orders.md`, "Slice 10 → One typed-link
record". Behaviours: `source.link.typed`, `source.link.any-depth`,
`source.link.both-ways`.

**This slice puts SEGMENTS on the record. It moves none of the four existing link
records** — notes, the canvas's two, and the value inside a prediction's metadata
each converge in their own later slice, with their own tests and owner. What this
slice owes them is that no word is lost when they do, which is why the vocabulary
is seeded from every set that already holds the idea (`models/typed_links.py`).

`source.link.any-depth`: an end is a segment of ANY granularity — a region, a
line, a word, a character. Nothing here reads the granularity, which is what makes
that true rather than merely intended: a link between two characters is the same
row as a link between two regions.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import Segment
from fichero_server.models.segments import assert_not_provisional
from fichero_server.models.typed_links import (
    LibraryLinkType,
    LinkEndKind,
    LinkNeedsTwoEnds,
    TypedLink,
    UnknownLinkType,
    resolve_link_type,
)

router = APIRouter(prefix="/links")

#: Relations where "from" and "to" carry no meaning. Stored `directed=False` so a
#: reader is never shown a direction that says nothing — "A is the same as B" has
#: no other end to read it from.
SYMMETRIC_LINK_TYPES: frozenset[str] = frozenset({"same_as", "free", "related_to"})


def _as_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (UnknownLinkType, LinkNeedsTwoEnds)):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


def link_types(db: Database) -> list[str]:
    """Every link-type key this library allows.

    Reads the TABLE, never the shipped list: a project's added type is as real as
    a seeded one, and a reader that fell back to the constant would refuse it.
    Falls back to the shipped keys only when the table is empty (a library opened
    by code older than the seed), so a read never refuses everything because a
    seed did not run.
    """
    from fichero_server.models.typed_links import builtin_link_types

    keys = [row.key for row in db.query(LibraryLinkType) if row.key]
    return keys or [key for key, _label, _inverse in builtin_link_types()]


def assert_known_link_type(db: Database, link_type: str) -> str:
    """Refuse a type outside this library's vocabulary; return the resolved key.

    Resolves a display alias first (`references` → `cites`), in ONE place, so an
    alias cannot be honoured by some writers and refused by others — which is how
    an alias quietly becomes a second key.
    """
    resolved = resolve_link_type(link_type)
    allowed = link_types(db)
    if resolved not in allowed:
        raise UnknownLinkType(link_type, allowed)
    return resolved


class TypedLinkCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_id: str
    to_id: str
    link_type: str
    from_kind: str = LinkEndKind.segment.value
    to_kind: str = LinkEndKind.segment.value
    certainty: Optional[float] = None
    #: Capped: it goes into the audit chain, which nothing can purge. A short
    #: reason for the link, never a quotation from the source.
    note: Optional[str] = None


def _invert_link_create(before, after, ctx: ActionContext):
    link_id = (after or {}).get("link_id")
    return ("typed_link.delete", {"link_id": link_id}) if link_id else None


@action(
    "typed_link.create",
    TypedLinkCreateParams,
    domains=["typed_link"],
    undoable=True,
    invert=_invert_link_create,
)
def _action_link_create(db: Database, params: TypedLinkCreateParams, ctx: ActionContext):
    """Link two things, with a type this library knows (`source.link.typed`)."""
    if params.from_id == params.to_id:
        raise _as_http_error(LinkNeedsTwoEnds(params.from_id))
    known_kinds = {kind.value for kind in LinkEndKind}
    for end_id, kind in ((params.from_id, params.from_kind), (params.to_id, params.to_kind)):
        if kind not in known_kinds:
            # An end of no known kind was stored as given; a reader could not tell what it named.
            raise HTTPException(status_code=422, detail=f"unknown link end kind {kind!r}; one of {', '.join(sorted(known_kinds))}")
        if kind == LinkEndKind.segment.value:
            assert_not_provisional(end_id, what="segment id")
            if db.get(Segment, end_id) is None:
                raise HTTPException(status_code=404, detail=f"Segment not found: {end_id}")
        elif kind == LinkEndKind.entity.value:
            # A place segment `names` its place ENTITY (maps D, `source.geo.place-segment-names-entity`):
            # a live one -- a merged entity answers with the one it was merged into.
            from fichero_server.models.knowledge import KnowledgeEntity

            entity = db.get(KnowledgeEntity, end_id)
            if entity is None:
                raise HTTPException(status_code=404, detail=f"Entity not found: {end_id}")
            if entity.merged_into_id:
                raise HTTPException(status_code=422, detail=f"entity {end_id} was merged into {entity.merged_into_id}; link that one")
    try:
        resolved = assert_known_link_type(db, params.link_type)
    except ValueError as refusal:
        raise _as_http_error(refusal) from refusal

    link = TypedLink(
        from_kind=params.from_kind,
        from_id=params.from_id,
        to_kind=params.to_kind,
        to_id=params.to_id,
        link_type=resolved,
        directed=resolved not in SYMMETRIC_LINK_TYPES,
        provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None,
        certainty=params.certainty,
        note=params.note,
    )
    db.save(link)

    spec = ChangeSpec(
        domains=["typed_link"],
        target_ids=[link.id],
        before=None,
        after={"link_id": link.id, "link_type": link.link_type},
        emit_type="typed_link.created",
        segment_ids=[
            end_id
            for end_id, kind in (
                (link.from_id, link.from_kind), (link.to_id, link.to_kind)
            )
            if kind == LinkEndKind.segment.value
        ],
    )
    return {"link_id": link.id, "link_type": link.link_type, "directed": link.directed}, spec


class TypedLinkDeleteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str


def _invert_link_delete(before, after, ctx: ActionContext):
    link_id = (after or {}).get("link_id")
    return ("typed_link.restore", {"link_id": link_id}) if link_id else None


@action(
    "typed_link.delete",
    TypedLinkDeleteParams,
    domains=["typed_link"],
    undoable=True,
    invert=_invert_link_delete,
)
def _action_link_delete(db: Database, params: TypedLinkDeleteParams, ctx: ActionContext):
    """Withdraw a link. Soft, so a withdrawn relation is still auditable."""
    link = db.get(TypedLink, params.link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Link not found: {params.link_id}")
    link.deleted_at = utc_now()
    db.save(link)

    spec = ChangeSpec(
        domains=["typed_link"],
        target_ids=[link.id],
        before={"link_id": link.id, "deleted": False},
        after={"link_id": link.id, "deleted": True},
        emit_type="typed_link.deleted",
    )
    return {"link_id": link.id, "deleted": True}, spec


@action(
    "typed_link.restore",
    TypedLinkDeleteParams,
    domains=["typed_link"],
    undoable=False,
)
def _action_link_restore(db: Database, params: TypedLinkDeleteParams, ctx: ActionContext):
    link = db.get(TypedLink, params.link_id)
    if link is None:
        raise HTTPException(status_code=404, detail=f"Link not found: {params.link_id}")
    link.deleted_at = None
    db.save(link)

    spec = ChangeSpec(
        domains=["typed_link"],
        target_ids=[link.id],
        before={"link_id": link.id, "deleted": True},
        after={"link_id": link.id, "deleted": False},
        emit_type="typed_link.created",
    )
    return {"link_id": link.id, "deleted": False}, spec


# ---------------------------------------------------------------------------
# Reads — from either end (`source.link.both-ways`)
# ---------------------------------------------------------------------------


class LinkRead(BaseModel):
    """One link as seen FROM ONE END, which is why `label` is not `link_type`.

    The same row read from the other end reads differently: A *glosses* B, B *is
    glossed by* A. A surface that showed `link_type` from both ends would tell a
    reader the wrong sentence half the time.
    """

    id: str
    link_type: str
    #: How the relation reads from the end that was asked about.
    label: str
    directed: bool
    #: The thing at the OTHER end from the one asked about.
    other_kind: str
    other_id: str
    #: True when the end asked about is the link's `to` end.
    inbound: bool
    certainty: float | None = None
    note: str | None = None


class LinkListResponse(BaseModel):
    end_id: str
    links: list[LinkRead]


def _labels(db: Database) -> dict[str, tuple[str, str]]:
    return {
        row.key: (row.label, row.inverse_label) for row in db.query(LibraryLinkType)
    }


@router.get("/of/{end_id}", response_model=LinkListResponse)
async def links_of(
    end_id: str,
    include_deleted: bool = Query(False, description="Include withdrawn links"),
    db: Database = Depends(get_library_database),
) -> LinkListResponse:
    """`GET /api/links/of/{end_id}` — every link touching one thing, from either
    side (`source.link.both-ways`).

    ONE call for both directions, because "what relates to this line" is one
    question a reader asks, not two. Two indexed reads answer it
    (`idx_typedlinks_from_id`, `idx_typedlinks_to_id`).
    """
    labels = _labels(db)
    links: list[LinkRead] = []
    for row in db.query(TypedLink, from_id=end_id):
        if row.deleted_at is not None and not include_deleted:
            continue
        label, _inverse = labels.get(row.link_type, (row.link_type, row.link_type))
        links.append(
            LinkRead(
                id=row.id, link_type=row.link_type, label=label, directed=row.directed,
                other_kind=row.to_kind, other_id=row.to_id, inbound=False,
                certainty=row.certainty, note=row.note,
            )
        )
    for row in db.query(TypedLink, to_id=end_id):
        if row.deleted_at is not None and not include_deleted:
            continue
        label, inverse = labels.get(row.link_type, (row.link_type, row.link_type))
        links.append(
            LinkRead(
                id=row.id, link_type=row.link_type,
                # From this end the sentence runs the other way -- unless the
                # relation is symmetric, where there is no other way to run.
                label=label if not row.directed else inverse,
                directed=row.directed,
                other_kind=row.from_kind, other_id=row.from_id, inbound=True,
                certainty=row.certainty, note=row.note,
            )
        )
    links.sort(key=lambda row: (row.link_type, row.other_id, row.id))
    return LinkListResponse(end_id=end_id, links=links)


class LinkTypeRead(BaseModel):
    key: str
    label: str
    inverse_label: str
    builtin: bool


class LinkTypeListResponse(BaseModel):
    types: list[LinkTypeRead]
    #: Words that mean one of the keys above. Shown so a client can accept what a
    #: person types without holding its own list.
    aliases: dict[str, str]


@router.get("/types", response_model=LinkTypeListResponse)
async def list_link_types(db: Database = Depends(get_library_database)) -> LinkTypeListResponse:
    """`GET /api/links/types` — this library's link vocabulary, with its aliases."""
    from fichero_server.models.typed_links import LINK_TYPE_ALIASES

    return LinkTypeListResponse(
        types=[
            LinkTypeRead(
                key=row.key, label=row.label, inverse_label=row.inverse_label,
                builtin=row.builtin,
            )
            for row in sorted(db.query(LibraryLinkType), key=lambda row: row.key)
        ],
        aliases=dict(LINK_TYPE_ALIASES),
    )


class TypedLinkWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_id: str
    to_id: str
    link_type: str
    from_kind: str = LinkEndKind.segment.value
    to_kind: str = LinkEndKind.segment.value
    certainty: Optional[float] = None
    note: Optional[str] = None


@router.post("", response_model=dict)
async def create_link(
    body: TypedLinkWrite,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict:
    result = registry.invoke(db, "typed_link.create", body.model_dump(), ctx)
    return {"ok": result.ok, "result": result.result, "audit_id": result.audit_id}
