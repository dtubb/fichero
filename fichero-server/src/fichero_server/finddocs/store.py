"""Where a Find the Documents proposal is kept: a hypothesis beside the source, never a change to it (#5550).

The existing store for "which pages belong together" until a person approves: a `grouping` artifact, on the
folder (or, for pages at the project's root, on its first page), whose `data` is the typed
`DocumentsProposal`. Light on purpose: the accept action imports it at engine start.
"""
from __future__ import annotations

from typing import Any

from fichero_server.models.found_documents import DocumentsProposal

#: The artifact kind a proposal is stored as, and the method that made it.
ARTIFACT_TYPE = "grouping"
PROVIDER = "fichero"
MODEL = "find-documents/rules-1"


def store(db: Any, proposal: DocumentsProposal, anchor_id: str) -> DocumentsProposal:
    from fichero_server.core.timeutil import utc_now
    from fichero_server.models import Artifact

    artifact = Artifact(document_id=anchor_id, artifact_type=ARTIFACT_TYPE, provider=PROVIDER, model=MODEL,
                        run_id=proposal.job_id,
                        confidence=min((d.confidence for d in proposal.documents), default=None))
    proposal = proposal.model_copy(update={"id": artifact.id, "created_at": utc_now().isoformat()})
    artifact.data = proposal.model_dump(mode="json")
    db.save(artifact)
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


def proposals(db: Any, folder_id: str | None = None) -> list[DocumentsProposal]:
    """Every stored proposal (of one folder), newest first."""
    from fichero_server.models import Artifact

    rows = [a for a in db.query(Artifact, artifact_type=ARTIFACT_TYPE) if a.model == MODEL]
    found = [DocumentsProposal.model_validate(a.data) for a in rows]
    if folder_id is not None:
        found = [p for p in found if p.folder_id == folder_id]
    return sorted(found, key=lambda p: (p.created_at or "", p.id), reverse=True)
