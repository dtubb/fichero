"""What the user pointed at when they started a run (#4397 #4396 #4427).

`selected_doc_ids` rode untyped inside `ExecuteWorkflowRequest.inputs`, a
`dict[str, Any]`. There was no schema for the selection at all — not a weak
contract, an absent one. That is *why* #4396 was possible: a client sent a
whole folder when the user had picked one file, and nothing in the contract
could reject it, because there was no contract to violate.

The important part is not that the field is typed. It is that it describes
**what the user pointed at** rather than a pre-resolved list of ids.

A flat `list[str]` would fix the type and keep the wrong division of labour:
the client would still be the thing deciding what a folder means, and the
server would still have to trust it. With a declared *kind*, the server
resolves scope — which is #4427's rule, and what turns #4396 from a bug that
was fixed into a request that cannot be expressed.

Concretely: a client that claims `kind=folder` and sends 47 ids is now
rejected at the boundary. A client that sends 47 ids can only honestly call
them `documents`, at which point the server's own expansion is the authority
and there is nothing left for the client to get wrong.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SelectionKind(str, Enum):
    """What sort of thing the user selected.

    An enum, not a string, for the same reason `artifact_type` is being made
    one (#4426): the generated Swift client gets a compile error instead of a
    silent mismatch. A vocabulary the client can misspell is a vocabulary that
    will eventually be misspelled.
    """

    #: An explicit set of documents the user picked. The ids ARE the scope.
    documents = "documents"
    #: One folder. The server expands it — the client must not.
    folder = "folder"
    #: One collection. As above.
    collection = "collection"
    #: One group of documents (a letter, a case): its member documents, in the
    #: group's own order (#5604). The server expands it, as it does a folder.
    group = "group"
    #: Segments at any level (regions, lines, words, signs), by segment id
    #: (#5604). Each is run on its own picture, cut to it, with its current
    #: reading; what a step writes from it attaches to that segment.
    segments = "segments"


#: Kinds that name a single container the server expands. Sending more than
#: one id for these is the #4396 shape stated in the request itself.
_SINGLE_CONTAINER_KINDS = frozenset(
    {SelectionKind.folder, SelectionKind.collection, SelectionKind.group}
)


class WorkflowSelection(BaseModel):
    """The declared scope of a run.

    Validation is the whole point: this is the first place in the system that
    can say "that request does not describe a coherent selection" and refuse,
    rather than running and discovering the scope was wrong from its effects
    on real archival data.
    """

    kind: SelectionKind
    ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_shape(self) -> "WorkflowSelection":
        cleaned = [str(i).strip() for i in self.ids if str(i).strip()]
        if not cleaned:
            raise ValueError(
                f"selection.kind={self.kind.value} requires at least one id; "
                "an empty selection is not a scope, it is a missing argument"
            )
        if self.kind in _SINGLE_CONTAINER_KINDS and len(cleaned) != 1:
            # The #4396 assertion, made structural: a folder run is scoped to
            # ONE folder. A client sending the folder's contents alongside (or
            # instead of) the folder is describing a different run than the
            # user asked for, and that is now unrepresentable rather than
            # merely discouraged.
            raise ValueError(
                f"selection.kind={self.kind.value} names a single container "
                f"but {len(cleaned)} ids were sent. The server expands a "
                "container; a client that has already expanded it should say "
                f"kind={SelectionKind.documents.value} instead."
            )
        object.__setattr__(self, "ids", cleaned)
        return self

    @property
    def container_id(self) -> str | None:
        """The container this run is scoped to, when it is scoped to one."""
        if self.kind in _SINGLE_CONTAINER_KINDS and self.ids:
            return self.ids[0]
        return None


# ── Resolving the kinds that are not plain documents (#5604) ────────────────
#
# `source.extract.run-on-any-level`: a run can be pointed at segments (any
# level) or at a group of documents. Resolving them needs the project, so these
# functions take the database; the model above stays a pure request shape.


#: The key a work unit's document carries when it is a SEGMENT of that page, not the page:
#: ``{"segment_id", "level", "text"}``. The reader reads the segment's picture; the save writes
#: what was read on the segment (`llm_base`), never onto the page's text.
SEGMENT_TARGET_KEY = "segment_target"


def segment_target_of(document) -> dict | None:
    """The segment a work unit's document stands for, or None for an ordinary page."""
    if isinstance(document, dict):
        target = document.get(SEGMENT_TARGET_KEY)
    else:
        target = (getattr(document, "model_extra", None) or {}).get(SEGMENT_TARGET_KEY)
    return target if isinstance(target, dict) and target.get("segment_id") else None


class SelectionRefused(ValueError):
    """The selection names something this run cannot honestly be run on.

    Raised before the run starts, with the words a person reads: a step that
    reads pages is never quietly run on the whole page when it was pointed at
    one line of it.
    """


def live_segments(db, segment_ids: list[str]) -> list:
    """The segments the ids mean now, in the order given (forwarded through
    merges and splits by the one resolver). Refuses an id with no live segment."""
    from fichero_server.models.segments import (  # noqa: PLC0415
        Segment,
        primary_live_segment_id,
        resolve_segment,
    )

    rows = []
    for segment_id in segment_ids:
        live_id = primary_live_segment_id(resolve_segment(db, segment_id))
        row = db.get(Segment, live_id) if live_id else None
        if row is None:
            raise SelectionRefused(f"segment {segment_id} is not in this project, or was deleted")
        rows.append(row)
    return rows


def selection_document_ids(db, selection: WorkflowSelection) -> list[str]:
    """The document ids a run's scope is recorded and resolved by.

    For segments, the pages they are on (each once, in the order first named);
    for every other kind, the ids as sent.
    """
    if selection.kind is not SelectionKind.segments:
        return list(selection.ids)
    return list(dict.fromkeys(row.document_id for row in live_segments(db, selection.ids)))


def refuse_unfit_selection(db, nodes: list[dict], selection: WorkflowSelection | None) -> None:
    """Refuse, in words, a selection the workflow's steps cannot run on.

    A group must be a group. Segments must exist, and every step of the
    workflow must be one that takes a segment (`tool_outputs.runs_on_segments`):
    a step that runs on pages is refused rather than run on the whole page.
    """
    if selection is None:
        return
    if selection.kind is SelectionKind.group:
        from fichero_server.models import DocType, Document  # noqa: PLC0415

        group = db.get(Document, selection.ids[0])
        if group is None or group.doc_type != DocType.group:
            raise SelectionRefused(f"{selection.ids[0]} is not a group of documents in this project")
        return
    if selection.kind is not SelectionKind.segments:
        return

    from fichero_server.workflows.registry import get_tool_def  # noqa: PLC0415
    from fichero_server.workflows.tool_outputs import runs_on_segments  # noqa: PLC0415

    segments = live_segments(db, selection.ids)
    level = segments[0].kind
    for node in nodes or []:
        tool = str(node.get("tool") or "")
        if runs_on_segments(tool):
            continue
        tool_def = get_tool_def(tool)
        name = (tool_def.display_name if tool_def is not None else "") or tool
        raise SelectionRefused(f"{name} runs on pages, not on a {level}")
