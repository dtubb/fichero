"""A transfer between two projects: the request, the result report, and the record each project keeps (#5657).

Spec: `docs/contributor_manual/specs/source/moving-between-projects.md` ("One engine action",
"No cross-file transaction", "The result report"). One `POST /api/documents/transfer` plans
(`dry_run`) or copies a selection from one open project into another; the result names what
travelled, what was cut and why, the vocabulary matched or made, and the merges proposed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now


def _new_id() -> str:
    return uuid.uuid4().hex


class TransferMode(str, Enum):
    """The Finder's grammar between projects: a drag moves, ⌥-drag copies."""

    copy = "copy"
    move = "move"


class TransferState(str, Enum):
    """The journal (`transfer.action.journal-recovers`): where a transfer got to.

    ``planned`` is a dry run's answer; ``sending`` the source's mirror before the target is written;
    ``writing`` the target's record before any row; ``verified`` after the read-back; ``done`` at the
    end; ``rolled_back`` after a failure removed everything the transfer wrote; ``undone`` after undo."""

    planned = "planned"
    sending = "sending"
    writing = "writing"
    verified = "verified"
    done = "done"
    rolled_back = "rolled_back"
    undone = "undone"


class TransferRole(str, Enum):
    """Which side of the transfer a project's record is (`transfer.action.record-in-both`)."""

    source = "source"
    target = "target"


class TransferRequest(BaseModel):
    """The drop, as the app (or the CLI, or MCP) sends it. The target project is the library header."""

    items: list[str] = Field(min_length=1, description="Ids of the nodes to transfer, in the source project; each carries its subtree.")
    source: str = Field(description="The source project's package path (an open .fichero).")
    target_parent_id: str | None = Field(
        default=None, description="The folder in the target the items land in; absent: the target's Sources folder."
    )
    mode: TransferMode = TransferMode.copy
    dry_run: bool = Field(default=False, description="Plan only: write nothing and return what would happen.")


class TransferCount(BaseModel):
    """How many rows of one kind travel (planned) and, after a copy, were written and read back."""

    kind: str
    planned: int
    written: int | None = None


class TransferCut(BaseModel):
    """An edge that crosses the edge of the set, cut on purpose and listed (`transfer.cut.listed-never-silent`)."""

    kind: str = Field(description="The kind of row the edge belongs to (TypedLink, KnowledgeClaim, CanvasItem, ...).")
    row: str = Field(description="The source row's id.")
    field: str = Field(description="The field that named something left behind.")
    points_to: str = Field(description="What it named, in the source.")
    name: str | None = Field(default=None, description="A readable name for the row, when it has one.")
    whole_row: bool = Field(
        default=False, description="True when the row itself does not travel; false when it travels without this edge."
    )
    reason: str


class TransferLeftBehind(BaseModel):
    """A node of the selection's subtree that stays in the source, and why."""

    item: str
    name: str
    reason: str


class TransferVocabulary(BaseModel):
    """A project vocabulary entry the carried rows use, matched by key in the target (`transfer.page.kind-matched-by-key`)."""

    vocabulary: str = Field(description="reading_kind, reading_level, document_type, link_type, hand, allograph, framework")
    key: str
    made: bool = Field(description="True when the target had none and the transfer makes (made) it.")
    difference: str | None = Field(
        default=None, description="Same key, different fields: the target's is kept and the difference named."
    )


class TransferEntityProposal(BaseModel):
    """A carried entity matched in the target: written new, and offered as a merge a person decides."""

    carried_entity: str = Field(description="The carried entity's id in the source.")
    name: str
    entity_type: str
    target_entity: str = Field(description="The target's entity it may be the same as.")
    target_name: str
    reason: str = Field(description='"same Wikidata Q-id …", "same name and type".')
    proposal: str | None = Field(default=None, description="The EntityMatchCandidate id in the target (absent in a dry run).")


class TransferResult(BaseModel):
    """The report: stored on the record, returned by the route, printed by the CLI and MCP."""

    transfer_id: str
    mode: TransferMode
    dry_run: bool
    state: TransferState
    source: str
    target: str
    target_parent_id: str
    actor: str
    when: datetime = Field(default_factory=utc_now)
    counts: list[TransferCount] = Field(default_factory=list)
    files: int = 0
    bytes: int = 0
    linked_files: list[str] = Field(default_factory=list, description="Items whose original is linked: the reference travels, not the file.")
    vocabulary: list[TransferVocabulary] = Field(default_factory=list)
    proposals: list[TransferEntityProposal] = Field(default_factory=list)
    entities_new: int = 0
    cuts: list[TransferCut] = Field(default_factory=list)
    left_behind: list[TransferLeftBehind] = Field(default_factory=list)
    copies: list[str] = Field(default_factory=list, description="The new ids of the top-level items in the target (empty in a dry run).")
    audit: str | None = Field(
        default=None, description="The target's audit row of this transfer: undo it (`POST /api/actions/audit/{audit}/undo`)."
    )
    error: str | None = None
    machine: str | None = Field(default=None, description="Between machines: the other engine (the source's, on the side it landed).")
    objects_sent: int | None = Field(
        default=None, description="Between machines: objects sent this time; a resumed send sends only what had not arrived.")
    linked_elsewhere: list[str] = Field(
        default_factory=list, description="Between machines: per linked item, where its original stays, in words.")


class MachineTransferRequest(BaseModel):
    """A copy to another engine (`transfer.machine.copy-only`). The library header names the SOURCE project here."""

    items: list[str] = Field(min_length=1, description="Ids of the nodes to copy, in this project; each carries its subtree.")
    machine: str = Field(description="A paired machine's id (GET /api/machines).")
    target_project: str = Field(description="The project on that machine, by its package path there, as it lists its projects.")
    target_parent_id: str | None = Field(default=None, description="The folder there; absent: its Sources folder.")
    pages_may_leave: bool = Field(False, description="The person's yes for these pages to go to that machine.")
    resume: str | None = Field(default=None, description="A transfer that stopped: send again, only what has not arrived.")


class IncomingTransfer(BaseModel):
    """The sending engine opens a copy on this one: what will arrive, from where (`transfer.machine.carriers-reused`)."""

    transfer_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    manifest: dict[str, Any] = Field(description="A SyncManifest: every object by its sha256 and size; one is the rows.")
    source_machine: str
    source_project: str = Field(description="The source project's package path on the source machine.")
    contract: str = Field(description="The sender's contract sha256: versions must match.")


class IncomingStatus(BaseModel):
    transfer_id: str
    objects: int
    missing: list[str] = Field(description="The sha256 of each object not yet arrived and verified here.")


class IncomingLand(BaseModel):
    target_parent_id: str | None = None


class TransferRecord(BaseModel):
    """The transfer's record in ONE project (same id in both): the journal, and what undo reads.

    In the target: the full id map, the files written, the proposals made and the result. In the source:
    the items sent, the mode and the target. Field names avoid the `_id(s)` suffix on purpose: these
    are the record's own bookkeeping, not ids a later transfer re-points."""

    id: str = Field(default_factory=_new_id)
    role: TransferRole
    state: TransferState
    mode: TransferMode
    source_project: str
    target_project: str
    items: list[str] = Field(default_factory=list)
    copies: list[str] = Field(default_factory=list)
    id_map: dict[str, str] = Field(default_factory=dict)
    files_written: list[str] = Field(default_factory=list)
    proposals: list[str] = Field(default_factory=list)
    #: A carried segment version's or forwarding's original audit pointer, by its new row id
    #: (`transfer.page.audit-pointers`: the row itself points at this transfer's audit row).
    source_audits: dict[str, str] = Field(default_factory=dict)
    #: In the target: every row the transfer wrote, by kind (what a move's compensation removes).
    written: dict[str, list[str]] = Field(default_factory=dict)
    #: In the source (a move): the nodes the move sent to the Trash, alive until then (what undo puts back).
    trashed: list[str] = Field(default_factory=list)
    #: In the source (a move): each edge cut there, as it was, so undo can put it back.
    source_cuts: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
