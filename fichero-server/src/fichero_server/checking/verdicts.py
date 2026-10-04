"""`check.verdict`'s work: the one audited action that records a verdict, whoever checks (`source.check.*`).

Trust is the server's: a person writing directly is `person`; a run, an agent (MCP) or a named checker
model is `model` (`source.check.model-never-a-person`). A model's verdict never curates or verifies: a
model's *reject* of an `unreviewed` statement moves it to `shortlisted`, and nothing further
(`source.check.curation-is-a-persons`); a person's verdict moves nothing, since a person's curation is
the statement's own action (`source.check.person-checks-the-same-way`).
"""
from __future__ import annotations

from typing import Any


from fichero_server.actions.registry import ActionContext, ChangeSpec
from fichero_server.models.checking import CheckVerdict, CheckVerdictParams  # noqa: F401  (re-exported)


def trust_of(ctx: ActionContext, checker_model: str | None) -> str:
    from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
    from fichero_server.models.knowledge import ProvenanceKind

    if checker_model is None and provenance_kind_from_ctx(ctx) is ProvenanceKind.human:
        return "person"
    return "model"


def _proposal(db: Any, params: CheckVerdictParams) -> str | None:
    """The proposal's document; LookupError when there is no such proposal."""
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

    if params.layer == "readings":
        row = db.get(ContentRepresentation, params.target_id)
        if row is not None:
            return row.document_id
        if params.segment_id:
            from fichero_server.api.routes.document.segment_readings import readings_of_segment

            found = next((r for r in readings_of_segment(db, params.segment_id) if r.id == params.target_id), None)
            if found is not None:
                return found.document_id
        raise LookupError(f"no reading {params.target_id}")
    model = KnowledgeClaim if params.layer == "claims" else KnowledgeEntity
    row = db.get(model, params.target_id)
    if row is None:
        raise LookupError(f"no {params.layer[:-1]} {params.target_id}")
    return getattr(row, "source_document_id", None)


def record_verdict(db: Any, params: CheckVerdictParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    """The work of `check.verdict` (registered by `api/routes/check.py`, so it is known at app start)."""
    from fichero_server.models.knowledge import ClaimCurationState, KnowledgeClaim

    trust = trust_of(ctx, params.checker_model)
    if trust == "person" and params.checker_model:
        raise ValueError("a person's verdict names no checker model")
    if params.verdict == "correct" and not (params.correction or params.replacement_id):
        raise ValueError("a correction says what replaces the proposal")
    document_id = _proposal(db, params)
    checker = params.checker_model or (ctx.actor if trust == "person" else f"agent:{ctx.actor or 'unknown'}")
    verdict = CheckVerdict(layer=params.layer, target_id=params.target_id, document_id=document_id,
                           verdict=params.verdict, reasons=params.reasons, correction=params.correction,
                           replacement_id=params.replacement_id, checker=checker, trust=trust,
                           run_id=ctx.run_id, episode_id=params.episode_id)
    db.save(verdict)
    after: dict[str, Any] = {"verdict_id": verdict.id, "trust": trust}
    claim_ids: list[str] = []
    if params.layer == "claims" and trust == "model" and params.verdict == "reject":
        claim = db.get(KnowledgeClaim, params.target_id)
        if claim.curation_state == ClaimCurationState.unreviewed:  # for a person to look at; nothing further
            claim.curation_state = ClaimCurationState.shortlisted
            db.save(claim)
            after["claim_shortlisted"] = claim.id
            claim_ids.append(claim.id)
    return verdict.model_dump(mode="json"), ChangeSpec(
        domains=["check"] + (["claim"] if claim_ids else []), target_ids=[verdict.id], before=None, after=after,
        emit_type="check.verdict", document_ids=[document_id] if document_id else [], claim_ids=claim_ids)
