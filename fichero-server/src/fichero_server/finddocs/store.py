"""Where a Find the Documents proposal is kept: a hypothesis beside the source, never a change to it (#5550).

The existing store for "which pages belong together" until a person approves: a `grouping` artifact, on the
folder (or, for pages at the project's root, on its first page), whose `data` is the typed
`DocumentsProposal`. Light on purpose: the accept action imports it at engine start.

A later run's proposal for any of the same pages of a folder supersedes the earlier one (`state`
"superseded"): it is kept, for what its answers teach, but no longer listed by default or accepted, so the
same pages are never offered twice.
"""
from __future__ import annotations

from typing import Any

from fichero_server.models.found_documents import DocumentsProposal

#: The artifact kind a proposal is stored as, and the method that made it.
ARTIFACT_TYPE = "grouping"
PROVIDER = "fichero"
MODEL = "find-documents/rules-1"


class ProposalOutOfDate(Exception):
    """A proposal that no longer describes the folder: superseded by a later run, or a document whose pages
    are no longer the folder's loose pages (grouped, moved or deleted since). The routes answer 409."""


def store(db: Any, proposal: DocumentsProposal, anchor_id: str) -> DocumentsProposal:
    from fichero_server.core.timeutil import utc_now
    from fichero_server.models import Artifact

    artifact = Artifact(document_id=anchor_id, artifact_type=ARTIFACT_TYPE, provider=PROVIDER, model=MODEL,
                        run_id=proposal.job_id,
                        confidence=min((d.confidence for d in proposal.documents), default=None))
    proposal = proposal.model_copy(update={"id": artifact.id, "created_at": utc_now().isoformat()})
    artifact.data = proposal.model_dump(mode="json")
    db.save(artifact)
    mine = set(proposal.page_ids)
    for older in proposals(db, proposal.folder_id):
        if older.id != proposal.id and older.folder_id == proposal.folder_id and older.state == "current" \
                and mine & set(older.page_ids):
            write(db, older.model_copy(update={"state": "superseded", "superseded_by": proposal.id}))
    return proposal


def read(db: Any, proposal_id: str) -> DocumentsProposal:
    from fichero_server.models import Artifact

    artifact = db.get(Artifact, proposal_id)
    if artifact is None or artifact.artifact_type != ARTIFACT_TYPE or artifact.model != MODEL:
        raise LookupError(f"no Find the Documents proposal {proposal_id}")
    return DocumentsProposal.model_validate(artifact.data)


def write(db: Any, proposal: DocumentsProposal) -> None:
    from fichero_server.models import Artifact

    artifact = db.get(Artifact, proposal.id)
    if artifact is None:
        raise LookupError(f"no Find the Documents proposal {proposal.id}")
    artifact.data = proposal.model_dump(mode="json")
    db.save(artifact)


def proposals(db: Any, folder_id: str | None = None, *, superseded: bool = True) -> list[DocumentsProposal]:
    """Every stored proposal (of one folder), newest first; `superseded=False` leaves out those a later run
    replaced."""
    from fichero_server.models import Artifact

    rows = [a for a in db.query(Artifact, artifact_type=ARTIFACT_TYPE) if a.model == MODEL]
    found = [DocumentsProposal.model_validate(a.data) for a in rows]
    if folder_id is not None:
        found = [p for p in found if p.folder_id == folder_id]
    if not superseded:
        found = [p for p in found if p.state != "superseded"]
    return sorted(found, key=lambda p: (p.created_at or "", p.id), reverse=True)
