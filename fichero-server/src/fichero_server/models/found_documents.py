"""A Find the Documents proposal, as stored and as every surface reads it (`finddocs.*`, #5550).

Stored as a hypothesis, never a change: the `data` of a `grouping` artifact on the folder (the artifact
kind that holds "which pages belong together" until a person approves). These models are its one typed
shape: the job writes it through them and the routes read it back through them.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from fichero_server.finddocs import AUTO_ACCEPT_ABOVE

#: What a proposed document or group can be in: still proposed, accepted (made a group node), or rejected.
ProposalState = Literal["proposed", "accepted", "rejected"]
#: A proposal is current until a later run on its folder proposes for any of its pages: then it is superseded,
#: kept (its answers teach, `finddocs.corrections-teach`) but no longer listed or accepted.
ProposalCurrency = Literal["current", "superseded"]
#: What a page that is not a document's own page turned out to be.
FindingKind = Literal["blank-verso", "blank-page", "duplicate-shot", "no-reading"]


class Signal(BaseModel):
    """One piece of evidence, named: a cue in the table, a page number, a sentence running over the break."""

    cue: str = Field(description="The cue's id in the table (`finddocs/cues.py`), or a furniture or continuity signal.")
    role: Literal["opening", "closing", "furniture", "continuity", "kind"]
    weight: float = Field(description="Its log-odds: above zero says a document starts here, below says it runs on.")
    page_id: str
    line: str | None = Field(None, description="The line it was read from, cut short.")


class ProposedJoin(BaseModel):
    """The join between two neighbouring written pages and the probability that a document starts at the second."""

    page_id: str = Field(description="The page after the join.")
    previous_page_id: str | None = None
    probability: float = Field(description="That a new document starts at `page_id` (0 to 1).")
    signals: list[Signal] = Field(default_factory=list)


class PageFinding(BaseModel):
    """A page reported, not made a document: a blank verso, a blank page, a second shot of a leaf, a page unread."""

    kind: FindingKind
    page_id: str
    of_page_id: str | None = Field(None, description="The recto of a verso, or the first shot of a duplicate.")
    similarity: float | None = None
    reason: str


class Decision(BaseModel):
    """Who accepted or rejected a proposed document or group: the run that made the proposal (its own
    auto-accept) or a person. A person's answer is a label; the run's is not (`finddocs.corrections-teach`)."""

    by: Literal["run", "person"]
    run_id: str | None = Field(None, description="The run that accepted it by itself.")
    actor: str | None = Field(None, description="The person who decided.")


class ProposedDocument(BaseModel):
    index: int
    name: str
    page_ids: list[str] = Field(description="Every page of the document in order, its blank versos and second shots too.")
    first_position: int = Field(description="Where it starts in the folder's pages (0-based).")
    last_position: int
    kind: str | None = Field(None, description="The prototype its opening cues suggest (Sentencia, Carta, Cable …).")
    prototype_key: str | None = None
    date: str | None = Field(None, description="Its date as read from its place-and-date line (ISO), when it has one.")
    parties: list[str] = Field(default_factory=list)
    confidence: float = Field(description="The least certain of its start, its end and the joins inside it.")
    reasons: list[str] = Field(default_factory=list)
    state: ProposalState = "proposed"
    accepted_as: str | None = Field(None, description="The group node (or the one page) it became.")
    decided_by: Decision | None = None


class ProposedGroup(BaseModel):
    """Documents that belong together (a case, a correspondence), in order."""

    index: int
    label: str
    document_indexes: list[int]
    parties: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    state: ProposalState = "proposed"
    accepted_as: str | None = None
    decided_by: Decision | None = None


class DocumentsProposal(BaseModel):
    """What one run of Find the Documents proposes for one folder's pages."""

    id: str = Field(description="The artifact that holds it.")
    folder_id: str | None = None
    page_ids: list[str] = Field(description="The pages looked at, in the folder's order.")
    method: str = "rules-1"
    job_id: str | None = None
    leaves: int = Field(0, description="Leaves the pages pair into (a written page and its blank verso are one).")
    documents: list[ProposedDocument] = Field(default_factory=list)
    groups: list[ProposedGroup] = Field(default_factory=list)
    findings: list[PageFinding] = Field(default_factory=list)
    joins: list[ProposedJoin] = Field(default_factory=list)
    created_at: str | None = None
    state: ProposalCurrency = "current"
    superseded_by: str | None = Field(None, description="The later proposal for the same pages.")


class FindDocumentsRequest(BaseModel):
    scope_ids: list[str] = Field(min_length=1, description="Folders, or a selection of pages (each with its folder).")
    accept_above: float | None = Field(
        AUTO_ACCEPT_ABOVE, ge=0.0, le=1.0,
        description="Accept, as the run ends, the boundaries of every proposed document at least this confident; "
                    "kinds and cases stay proposals for a person. Left out: the project's default, off until a "
                    "box a person broke down is scored (ruled 2026-10-10); null leaves all for a person.")


class FindDocumentsAcceptRequest(BaseModel):
    document_indexes: list[int] | None = Field(None, description="The documents to accept; none with no "
                                               "`min_confidence` accepts them all.")
    min_confidence: float | None = Field(None, ge=0.0, le=1.0, description="Accept every document at least this confident.")
    arrange: bool = Field(True, description="Lay the folder's canvas out in the documents' order.")
    groups: bool = Field(True, description="Also accept each proposed group whose documents are all accepted.")


class FindDocumentsRejectRequest(BaseModel):
    document_indexes: list[int] = Field(min_length=1)


class FindDocumentsAcceptResult(BaseModel):
    proposal: DocumentsProposal
    accepted: list[int]
    groups_made: list[str]
    audit_id: str = Field(description="The accept's audit row: undoing it restores the folder as it was.")


class FindDocumentsRun(BaseModel):
    job_id: str
    state: str
    reason: str | None = None
    proposal_ids: list[str] = Field(default_factory=list)
