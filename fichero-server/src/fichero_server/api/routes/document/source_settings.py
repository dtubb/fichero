"""Source-model slice 9 (#4938) — setting the cascade's facts at the levels
ABOVE a segment: the project, and a node (a folder, a document, a page).

Spec: `build-notes-readings-cascade-orders.md`, "Slice 9", and the build note
"The write path" there.

**WHY THIS DOES NOT HANDLE SEGMENTS, ruled 2026-09-26 (option A).** The build
notes designed ONE entry point for every level. By the time this was built,
`segment.update` already owned a segment's version snapshot, its stale check, its
inverse and its audit row, and it had grown the three facts as ordinary columns
beside the segment's other ones. Routing a segment's language through here would
have made `segment.update` *the only segment action that cannot change some of
the segment's own columns* — not untidiness but a trap, because the next reader
finds that odd and "fixes" it. So the single-entry-point design did not survive
contact with a constraint the notes did not know about, and the asymmetry is
deliberate: **project and node here, segment through `segment.update`**, with a
typed refusal that names it rather than leaving a caller to hunt.

The invariants are the SAME at every level, which is the point of having ruled
rather than drifted:

* provenance is engine-set from `ctx` and never accepted from a caller
  (#4868/#4869) — a setter that stores a value without its `{status, source,
  basis, level}` is how `says-where-from` quietly stops being true;
* every script is checked against this library's declarations
  (`assert_known_script`) and every direction against the six
  (`assert_known_direction`), so a validated segment path beside an unvalidated
  project path — the sibling-defect shape — cannot happen;
* clearing means NEVER DETERMINED again, not `unknown`, which is a positive
  finding that somebody looked.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.db import Database
from fichero_server.llm.language_policy import (
    LEVEL_DOCUMENT,
    LEVEL_PROJECT,
    SOURCE_DETECTED,
    SOURCE_USER,
    STATUS_KNOWN,
    BadDirection,
    assert_known_direction,
    build_language_meta,
    resolve_direction,
    resolve_language,
    resolve_script,
)
from fichero_server.models import Document
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.source_declarations import (
    PROJECT_FACT_KEYS,
    UnknownProjectFact,
    UnknownScript,
    assert_known_script,
    clear_project_fact,
    project_facts,
    resolve_encoding,
    set_project_fact,
)
from fichero_server.models.segments import Segment

router = APIRouter(prefix="/source-settings")

#: The levels this action writes. `segment` is deliberately absent — see the
#: module docstring and :class:`SegmentLevelIsElsewhere`.
LEVEL_PROJECT_PARAM = "project"
LEVEL_NODE_PARAM = "node"
WRITABLE_LEVELS: tuple[str, ...] = (LEVEL_PROJECT_PARAM, LEVEL_NODE_PARAM)


class SegmentLevelIsElsewhere(ValueError):
    """Raised when a caller asks to set a fact on a SEGMENT through this action.

    Names the alternative in the message, because a refusal that says only "not
    supported here" sends the reader hunting through the action registry for
    something that is one call away.
    """

    def __init__(self) -> None:
        super().__init__(
            "a segment's language, script and direction are set through "
            "`segment.update` (with its expected_version), and cleared through "
            "`segment.facts_clear`; this action sets the project and node levels"
        )


class UnknownSettingLevel(ValueError):
    """Raised for a level that is not one of the two this action writes."""

    def __init__(self, level: str) -> None:
        self.level = level
        super().__init__(
            f"{level!r} is not a level this action writes; allowed: "
            + ", ".join(WRITABLE_LEVELS)
        )


class NodeNeedsATarget(ValueError):
    """Raised when `level="node"` arrives without the node it is about."""

    def __init__(self) -> None:
        super().__init__("level 'node' needs target_id: which folder, document or page")


def _as_http_error(exc: Exception) -> HTTPException:
    """One place mapping a refusal to a status code, as `segments.py` does."""
    if isinstance(
        exc,
        (
            SegmentLevelIsElsewhere,
            UnknownSettingLevel,
            NodeNeedsATarget,
            UnknownProjectFact,
            UnknownScript,
            BadDirection,
        ),
    ):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


def _checked(db: Database, key: str, value: str) -> None:
    """The validation every level shares."""
    if key == "script":
        assert_known_script(db, value)
    if key == "direction":
        assert_known_direction(value)


def _meta_for(ctx: ActionContext, *, level: str, noun: str) -> dict:
    """The provenance the cascade reads, built from `ctx` and never from a caller.

    Uses `provenance_kind_from_ctx`, the ONE function deciding "who made this"
    for every source-model write, rather than re-deriving it here. A local
    `ctx.actor and not ctx.run_id` looked equivalent and was not: an agent acting
    through MCP sets `via_mcp` and no `run_id`, so it would have been recorded as
    a person — the #4868/#4869 defect exactly, reintroduced one level up.
    """
    by_a_person = provenance_kind_from_ctx(ctx) == ProvenanceKind.human
    return build_language_meta(
        status=STATUS_KNOWN,
        source=SOURCE_USER if by_a_person else SOURCE_DETECTED,
        level=level,
        basis=f"set on this {noun} by " + ("a person" if by_a_person else "a machine"),
    )


class SourceSettingSetParams(BaseModel):
    """`level` is `project` or `node`; a segment's facts live on the segment.

    `key` is one of language, script, direction. Encoding is deliberately absent:
    it is a property of the SCRIPT, recorded on the script row, and a page's
    encoding is read from there through the cascade.
    """

    model_config = ConfigDict(extra="forbid")

    level: str
    key: str
    value: str
    #: The node this is about, for `level="node"`. None for the project, which
    #: has exactly one of itself.
    target_id: Optional[str] = None


def _invert_source_setting_set(before, after, ctx: ActionContext):
    """Undo restores the value that was there, or clears it when there was none.

    Reads only `after` for the address and `before` for the old value, which is a
    SETTING and not a researcher's words — the one kind of value that belongs in
    an audit row (the same rule `source_setting` follows in the build notes).
    """
    if not after:
        return None
    address = {
        "level": after.get("level"),
        "key": after.get("key"),
        "target_id": after.get("target_id"),
    }
    if not address["level"] or not address["key"]:
        return None
    previous = (before or {}).get("value")
    if previous:
        return ("source_setting.set", {**address, "value": previous})
    return ("source_setting.clear", address)


@action(
    "source_setting.set",
    SourceSettingSetParams,
    domains=["source_setting"],
    undoable=True,
    invert=_invert_source_setting_set,
)
def _action_source_setting_set(
    db: Database, params: SourceSettingSetParams, ctx: ActionContext
):
    """Record one of the three facts at the project or node level."""
    if params.level == "segment":
        raise _as_http_error(SegmentLevelIsElsewhere())
    if params.level not in WRITABLE_LEVELS:
        raise _as_http_error(UnknownSettingLevel(params.level))
    if params.key not in PROJECT_FACT_KEYS:
        raise _as_http_error(UnknownProjectFact(params.key))
    if not params.value:
        raise HTTPException(status_code=422, detail="value is empty: use source_setting.clear")
    try:
        _checked(db, params.key, params.value)
    except ValueError as refusal:
        raise _as_http_error(refusal) from refusal

    if params.level == LEVEL_PROJECT_PARAM:
        was = getattr(project_facts(db), params.key)
        set_project_fact(
            db, params.key, params.value,
            meta=_meta_for(ctx, level=LEVEL_PROJECT, noun="project"),
        )
        target_ids = ["project"]
        document_ids: list[str] = []
    else:
        if not params.target_id:
            raise _as_http_error(NodeNeedsATarget())
        node = db.get(Document, params.target_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Node not found: {params.target_id}")
        was = getattr(node, params.key)
        setattr(node, params.key, params.value)
        setattr(
            node, f"{params.key}_meta",
            _meta_for(ctx, level=LEVEL_DOCUMENT, noun="node"),
        )
        db.save(node)
        target_ids = [node.id]
        document_ids = [node.id]

    address = {"level": params.level, "key": params.key, "target_id": params.target_id}
    spec = ChangeSpec(
        domains=["source_setting"],
        target_ids=target_ids,
        before={**address, "value": was},
        after={**address, "value": params.value},
        emit_type="source_setting.changed",
        document_ids=document_ids,
    )
    return {**address, "value": params.value}, spec


class SourceSettingClearParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str
    key: str
    target_id: Optional[str] = None


def _invert_source_setting_clear(before, after, ctx: ActionContext):
    """Puts back what was cleared. Nothing to do when there was nothing set."""
    previous = (before or {}).get("value")
    if not previous or not before:
        return None
    return (
        "source_setting.set",
        {
            "level": before.get("level"),
            "key": before.get("key"),
            "target_id": before.get("target_id"),
            "value": previous,
        },
    )


@action(
    "source_setting.clear",
    SourceSettingClearParams,
    domains=["source_setting"],
    undoable=True,
    invert=_invert_source_setting_clear,
)
def _action_source_setting_clear(
    db: Database, params: SourceSettingClearParams, ctx: ActionContext
):
    """Return one fact at one level to NEVER DETERMINED.

    Not to `unknown`: that is a positive finding that somebody looked and could
    not tell, it STOPS the cascade's walk, and it is written by setting a value's
    meta rather than by clearing. Clearing removes the statement, and the level
    below answers again.
    """
    if params.level == "segment":
        raise _as_http_error(SegmentLevelIsElsewhere())
    if params.level not in WRITABLE_LEVELS:
        raise _as_http_error(UnknownSettingLevel(params.level))
    if params.key not in PROJECT_FACT_KEYS:
        raise _as_http_error(UnknownProjectFact(params.key))

    if params.level == LEVEL_PROJECT_PARAM:
        was = getattr(project_facts(db), params.key)
        clear_project_fact(db, params.key)
        target_ids = ["project"]
        document_ids: list[str] = []
    else:
        if not params.target_id:
            raise _as_http_error(NodeNeedsATarget())
        node = db.get(Document, params.target_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Node not found: {params.target_id}")
        was = getattr(node, params.key)
        setattr(node, params.key, None)
        # The meta goes with the value: provenance for a fact that is no longer
        # there would say somebody determined something that does not exist.
        setattr(node, f"{params.key}_meta", None)
        db.save(node)
        target_ids = [node.id]
        document_ids = [node.id]

    address = {"level": params.level, "key": params.key, "target_id": params.target_id}
    spec = ChangeSpec(
        domains=["source_setting"],
        target_ids=target_ids,
        before={**address, "value": was},
        after={**address, "value": None},
        emit_type="source_setting.changed",
        document_ids=document_ids,
    )
    return {**address, "value": None}, spec


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


class SettingResolution(BaseModel):
    """One resolved fact, with the rung that answered."""

    key: str
    value: str | None
    status: str
    source: str
    basis: str
    #: `None` when no rung stated it — a pinned request, or a derivation.
    level: str | None = None


class ResolvedSourceSettings(BaseModel):
    document_id: str | None = None
    segment_id: str | None = None
    settings: list[SettingResolution]


def _text_of(db: Database, segment: Segment | None, document: Document | None) -> str | None:
    """The segment's counting reading, else the page's text: what the letters rung reads."""
    if segment is not None:
        from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment

        items = readings_of_segment(db, segment.id)
        by_id = {item.id: item.content for item in items}
        for answer in counting_by_kind(db, segment.id, items).values():
            if answer.representation_id in by_id:
                return by_id[answer.representation_id]
        return None
    return getattr(document, "page_content", None) or None


@router.get("/resolve", response_model=ResolvedSourceSettings)
async def resolve_source_settings(
    document_id: Optional[str] = Query(None, description="The document, when no segment"),
    segment_id: Optional[str] = Query(None, description="The segment to resolve for"),
    db: Database = Depends(get_library_database),
) -> ResolvedSourceSettings:
    """`GET /api/source-settings/resolve` — the three facts and the encoding, each
    with the rung that answered (`source.lang.says-where-from`).

    For ONE selection, not for a list: resolving every segment of a page here
    would be one walk per row, which is why the seam carries what is SET and this
    answers what is RESOLVED.
    """
    segment = db.get(Segment, segment_id) if segment_id else None
    if segment_id and segment is None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
    document = None
    document_id = document_id or (segment.document_id if segment else None)
    if document_id:
        document = db.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    project = project_facts(db)
    # The TEXT is evidence too (#5176): with nothing stated, a Syriac line's letters name its
    # script, and its script's letters its direction -- the same rungs the page text's
    # derivation uses (`resolve_direction(text=)`), not a second implementation. Language is
    # never guessed from the script; without a statement it is "not determined", naming it.
    text = _text_of(db, segment, document)
    script = resolve_script(segment=segment, document=document, project=project, text=text)
    language = resolve_language(
        document=document, segment=segment, detect=False,
        script=script.language if script.source == SOURCE_DETECTED else None,
    )
    from fichero_server.api.routes.document.segment_readings import direction_rungs

    # The rungs above the page from the SAME function the derivation and the Reader use (#5172).
    direction = resolve_direction(
        segment=segment, document=document, text=text, **direction_rungs(db, document)
    )
    encoding = resolve_encoding(
        db, segment=segment, document=document, project=project, script=script.language
    )

    return ResolvedSourceSettings(
        document_id=document_id,
        segment_id=segment_id,
        settings=[
            SettingResolution(
                key=key,
                value=resolution.language,
                status=resolution.status,
                source=resolution.source,
                basis=resolution.basis,
                level=resolution.level,
            )
            for key, resolution in (
                ("language", language),
                ("script", script),
                ("direction", direction),
                ("encoding", encoding),
            )
        ],
    )


class SourceSettingWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str
    key: str
    #: `None` clears the setting, which is the same act as `source_setting.clear`
    #: and is routed to it — one HTTP verb for "state this" and "stop stating it"
    #: keeps the client from having to know two endpoints for one control.
    value: Optional[str] = None
    target_id: Optional[str] = None


@router.put("", response_model=dict)
async def put_source_setting(
    body: SourceSettingWrite,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict:
    """`PUT /api/source-settings` — state a fact, or stop stating it."""
    params = body.model_dump(exclude_none=True)
    if body.value:
        name = "source_setting.set"
    else:
        name = "source_setting.clear"
        params.pop("value", None)
    result = registry.invoke(db, name, params, ctx)
    return {"ok": result.ok, "result": result.result, "audit_id": result.audit_id}
