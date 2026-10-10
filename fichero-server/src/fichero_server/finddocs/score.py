"""Scoring a folder's proposal against a person's breakdown, kept as a measurement (`finddocs.scored`, #5550).

A person's breakdown of a folder is the documents a person set on its proposal: those a person accepted and
those a person adjusted (rejected ones are left out: a rejection says the run was wrong, not where the document
runs). The run's own call at every join (`proposal.joins`, never changed by an adjustment) is judged where either
page is in one of the person's documents: a boundary when the two pages are not in the same one.

`finddocs.score` stores each score as a `finddocs_score` artifact on the folder; `suggest` reads the newest score
of every folder and names the lowest confidence level the run was at least 99% right at over `MIN_JOINS` joins:
the level a person may turn the auto-accept on at (`finddocs.AUTO_ACCEPT_ABOVE` itself is never set here).
"""
from __future__ import annotations

from typing import Any

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.finddocs import store
from fichero_server.finddocs.propose import BOUNDARY_AT
from fichero_server.models.found_documents import (
    DocumentsProposal,
    FindDocumentsScore,
    FindDocumentsScoreRequest,
    LevelAgreement,
    ProposedDocument,
)

#: The artifact kind a score is kept as, on its folder, and the method that made it.
ARTIFACT_TYPE = "finddocs_score"
MODEL = "find-documents/score-1"
#: The confidence levels agreement is reported at.
LEVELS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)
#: The agreement a level needs to be suggested for the auto-accept (ruled 2026-10-10: boundaries 99% right).
SUGGEST_SHARE = 0.99
#: ponytail: the joins a level needs before it is suggested. At 50, 99% allows no miss; fewer cannot tell 99%
#: from 95% (a level only 95% right passes 20 joins without a miss a third of the time, 50 under one in twelve).
MIN_JOINS = 50


class ScoreNotPossible(ValueError):
    """Nothing to score: the folder has no proposal, or a person set none of its documents. The routes answer 422."""


def breakdown(proposal: DocumentsProposal) -> list[ProposedDocument]:
    """The documents a person set: accepted by a person, or adjusted by one; never a rejected one."""
    return [d for d in proposal.documents if d.state != "rejected" and (
        d.adjusted_by is not None
        or (d.state == "accepted" and d.decided_by is not None and d.decided_by.by == "person"))]


def _certainty(probability: float) -> float:
    return probability if probability >= BOUNDARY_AT else 1.0 - probability


def measure(db: Any, proposal: DocumentsProposal) -> dict[str, Any]:
    """Every number of a score but its record: precision, recall, exact documents, kinds, agreement per level."""
    from fichero_server.models import Document

    person = breakdown(proposal)
    if not person:
        raise ScoreNotPossible(
            "no document in this folder's proposal was accepted or adjusted by a person yet: accept or adjust "
            "some documents, then score")
    owner = {page: n for n, d in enumerate(person) for page in d.page_ids}
    judged = []  # (the run's call, the person's, the run's certainty)
    calls: dict[str, bool] = {}  # the run's call at the join before each page
    for join in proposal.joins:
        called = join.probability >= BOUNDARY_AT
        calls[join.page_id] = called
        left, right = owner.get(join.previous_page_id or ""), owner.get(join.page_id)
        if left is None and right is None:
            continue
        judged.append((called, left != right, _certainty(join.probability)))
    proposed = sum(1 for called, _, _ in judged if called)
    actual = sum(1 for _, truth, _ in judged if truth)
    hits = sum(1 for called, truth, _ in judged if called and truth)

    def exact(document: ProposedDocument) -> bool:
        pages = set(document.page_ids)
        for join in proposal.joins:
            inside_left, inside_right = join.previous_page_id in pages, join.page_id in pages
            if inside_left and inside_right and join.probability >= BOUNDARY_AT:
                return False
            if inside_left != inside_right and join.probability < BOUNDARY_AT:
                return False
        return True

    kinds = []
    for d in person:
        node = db.get(Document, d.accepted_as) if d.state == "accepted" and d.accepted_as else None
        if node is not None and node.prototype_key:
            kinds.append(node.prototype_key == d.prototype_key)
    return {
        "documents": len(person), "joins": len(judged),
        "boundaries_proposed": proposed, "boundaries_actual": actual,
        "precision": hits / proposed if proposed else None, "recall": hits / actual if actual else None,
        "exact_documents": sum(1 for d in person if exact(d)),
        "kinds_confirmed": len(kinds), "kinds_right": sum(kinds),
        "kind_accuracy": sum(kinds) / len(kinds) if kinds else None,
        "levels": [_level(level, [(c == t) for c, t, sure in judged if sure >= level]) for level in LEVELS],
    }


def _level(level: float, agreements: list[bool]) -> LevelAgreement:
    agreed = sum(agreements)
    return LevelAgreement(level=level, joins=len(agreements), agreed=agreed,
                          share=agreed / len(agreements) if agreements else None)


def _proposal(db: Any, params: FindDocumentsScoreRequest) -> DocumentsProposal:
    from fichero_server.models import Document

    if db.get(Document, params.folder_id) is None:
        raise LookupError(f"no folder {params.folder_id}")
    if params.proposal_id:
        proposal = store.read(db, params.proposal_id)
        if proposal.folder_id != params.folder_id:
            raise ScoreNotPossible(f"proposal {params.proposal_id} is not this folder's")
        return proposal
    current = store.proposals(db, params.folder_id, superseded=False)
    if not current:
        raise ScoreNotPossible("Find the Documents has not been run on this folder: run it, set some documents, "
                               "then score")
    return current[0]


def scores(db: Any, folder_id: str | None = None) -> list[FindDocumentsScore]:
    """The stored scores (of one folder), newest first."""
    from fichero_server.models import Artifact

    rows = [a for a in db.query(Artifact, artifact_type=ARTIFACT_TYPE) if a.model == MODEL and a.data]
    found = [FindDocumentsScore.model_validate(a.data) for a in rows]
    if folder_id is not None:
        found = [s for s in found if s.folder_id == folder_id]
    return sorted(found, key=lambda s: (s.scored_at, s.id), reverse=True)


def pooled(db: Any) -> list[LevelAgreement]:
    """The agreement at each level over the newest score of every folder (an older score of a folder is the
    same pages judged again, so it is not counted twice)."""
    newest: dict[str, FindDocumentsScore] = {}
    for s in scores(db):
        newest.setdefault(s.folder_id, s)
    out = []
    for level in LEVELS:
        rows = [lv for s in newest.values() for lv in s.levels if lv.level == level]
        joins, agreed = sum(lv.joins for lv in rows), sum(lv.agreed for lv in rows)
        out.append(LevelAgreement(level=level, joins=joins, agreed=agreed, share=agreed / joins if joins else None))
    return out


def suggest(levels: list[LevelAgreement]) -> float | None:
    """The lowest level at least `SUGGEST_SHARE` agreed over at least `MIN_JOINS` joins; None until one is."""
    return next((lv.level for lv in levels
                 if lv.joins >= MIN_JOINS and lv.share is not None and lv.share >= SUGGEST_SHARE), None)


@action("finddocs.score", FindDocumentsScoreRequest, domains=["document"], undoable=False)
def _action_score(db: Any, params: FindDocumentsScoreRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.core.timeutil import utc_now
    from fichero_server.models import Artifact

    proposal = _proposal(db, params)
    numbers = measure(db, proposal)
    artifact = Artifact(document_id=params.folder_id, artifact_type=ARTIFACT_TYPE, provider=store.PROVIDER,
                        model=MODEL, run_id=proposal.job_id, confidence=numbers["precision"])
    score = FindDocumentsScore(id=artifact.id, folder_id=params.folder_id, proposal_id=proposal.id,
                               job_id=proposal.job_id, scored_at=utc_now().isoformat(), scored_by=ctx.actor,
                               **numbers)
    artifact.data = score.model_dump(mode="json")
    db.save(artifact)
    return ({"score": artifact.data},
            ChangeSpec(domains=["document"], target_ids=[params.folder_id],
                       after={"score_id": artifact.id, "proposal_id": proposal.id}))
