"""Audited purge of the free NLP draft layer (#4823 S3, team-lead review).

The draft stage (`importers/nlp_draft.py`) writes into real research
libraries by default; before it can default ON again (S1 in the same
review) there must be a way to take the rows back. This is that way back
-- through the ONE audited action layer (`actions/registry.py`), never a
bare route, so it is inspectable/audited/scriptable the same way every
other library-mutating action already is. `entity.purge_nlp_draft`
(domains=["entity", "claim"]): it removes ENTITIES whose provenance is
exclusively the spaCy draft, and -- necessarily -- the draft-only claims
about them, since a bare entity row with no claim is not useful. A
document- or library-wide bulk action, hence the `entity.*` namespace
(this codebase has no `kg.*` action namespace; every action is named for
the domain it primarily acts on -- see `entity.merge`/`entity.unmerge`
which also touch claims).

Scope: ONLY rows whose provenance is EXCLUSIVELY the spaCy draft AND that
show NO independent evidence of ever being touched by anything else --

- `KnowledgeClaim` base rule: `provider == "spacy"`, never corroborated by
  another extractor (`metadata["also_extracted_by"]` -- `_record_
  additional_attribution` in `_entity_writer.py` names every OTHER
  provider that also produced the same statement -- empty here means only
  spaCy ever did), never reviewed (`curation_state == unreviewed`).
- `KnowledgeEntity` base rule: `curation_state == unreviewed`, AND every
  claim that references it (via `entity_ids`) is itself draft-only by the
  claim rule above. An entity with NO referencing claim at all is left
  untouched -- its provenance cannot be verified from here, and this purge
  never guesses (prefer-raise's cousin: absence of evidence is not
  evidence to delete).

CRITICAL CORRECTION (team-lead review, F2): `curation_state` alone is NOT
proof nothing has touched a row. Verified at the code: `update_entity_impl`
(rename, aliases, description, metadata -- everything `entity.update`
edits) NEVER writes `curation_state`; neither does the authority-link route
(`kg/entity_curation.py::link_external_authority`, a bare route, not even
action-registered). So a person can rename an entity, add an alias, attach
a note, link an authority record, or merge into it, and it still reads
`unreviewed`. `_protected_ids` below closes that gap: it treats ANY of the
following as proof of an outside touch, because the draft stage itself
NEVER produces any of them (it calls `upsert_entity`/`save_claim` as plain
functions, bypassing `registry.invoke` entirely -- so an `ActionAudit` row
naming this id is proof positive of a REAL action, never the draft stage):
  * an `ActionAudit` row (any registered action -- update/merge/unmerge/
    batch_curation/assign_time_period/create_link/...) naming this id;
  * an `EntityMergeAudit` row (merge/split/authority-link/undo-*,
    including the authority-link route above, which bypasses ActionAudit
    but still writes here) naming this id as target or source;
  * `entity.metadata["authority_links"]` non-empty (belt-and-suspenders
    alongside the EntityMergeAudit check);
  * a `Note` or `Annotation` whose `linked_entity_ids`/`linked_claim_ids`
    names this id;
  * a `KnowledgeClaimLink` (claim<->claim) or `LibraryItemLink` (general
    node<->node) naming this id.
`find_draft_only_rows` computes the naive candidate set first, then
subtracts anything `_protected_ids` proves was touched -- reported back as
`protected_count`/`protected_reasons` in the action result, so the person
running it can see what it refused to touch and why.

Delete mechanics (team-lead review, confirm-b): goes through the SAME
low-level delete the single-row audited actions use --
`entity.delete`'s `delete_entity_impl` and `claim.delete`'s
`delete_claim_impl` -- not a raw `db.delete`, so vector-index cleanup
(`entity_vectors.remove`) and the `MutationLog` row both still happen.
Claims are deleted BEFORE their entities: by the time an entity is
deleted, every draft claim referencing it is already gone (an entity is
only draft-only when ALL its claims are), so `delete_entity_impl`'s own
claim-detachment step (`cascade_claims=False`) has nothing left to touch.

Undo: NOT wired as `undoable=True` at the bulk level. `entity.delete`'s
single-row undo snapshots one entity + its claims into the audit row; a
library-wide purge can touch thousands of rows, and dumping all of them
into one audit-log row is the wrong tradeoff for a bulk action. `dry_run`
(default True) is the safety net instead -- always run it first, review
the counts, then purge for real. (Each individual delete still goes
through `delete_entity_impl`/`delete_claim_impl`, which write their own
`MutationLog` rows -- so a per-row trail exists, just not one-call undo.)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.db import Database
from fichero_server.models import ActionAudit, Document
from fichero_server.models.knowledge import (
    Annotation,
    ClaimCurationState,
    EntityCurationState,
    EntityMergeAudit,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    LibraryItemLink,
    LibraryItemType,
    Note,
)

logger = logging.getLogger(__name__)

# No bespoke HTTP endpoint (the module docstring explains why: the action
# registry's generic `/api/actions/invoke` is the surface). The router
# exists only so this module is imported at startup the same way every
# other kg/*.py action module is -- see `api/main.py`'s router-include
# list, which is what actually triggers the `@action` decorator below.
router = APIRouter(prefix="/kg")

_DOC_METADATA_KEYS = ("nlp_processed_at", "nlp_error", "nlp_truncated")


def _claim_is_draft_only(claim: KnowledgeClaim) -> bool:
    if claim.provider != "spacy":
        return False
    if claim.curation_state != ClaimCurationState.unreviewed:
        return False
    also_extracted_by = (claim.metadata or {}).get("also_extracted_by") or []
    return not also_extracted_by


def _entity_is_draft_only(
    entity: KnowledgeEntity, claims_by_entity: dict[str, list[KnowledgeClaim]]
) -> bool:
    if entity.curation_state != EntityCurationState.unreviewed:
        return False
    referencing = claims_by_entity.get(entity.id, [])
    if not referencing:
        # No claim proves this entity came from the draft layer -- never
        # guessed, never deleted.
        return False
    return all(_claim_is_draft_only(claim) for claim in referencing)


def _protected_ids(
    db: Database, entity_ids: set[str], claim_ids: set[str]
) -> dict[str, str]:
    """id -> reason, for candidate ids that must SURVIVE despite passing
    the curation_state-based draft-only rule above -- because something
    other than the draft stage has independently touched them (F2, team-
    lead review). See the module docstring for why each source below is
    proof: the draft stage produces none of these itself.
    """
    protected: dict[str, str] = {}
    candidates = entity_ids | claim_ids
    if not candidates:
        return protected

    for audit in db.query(ActionAudit):
        for target_id in audit.target_ids or []:
            if target_id in candidates and target_id not in protected:
                protected[target_id] = f"acted on by {audit.action_name}"

    for audit in db.query(EntityMergeAudit):
        touched = {audit.target_entity_id, *(audit.source_entity_ids or [])}
        for target_id in touched & entity_ids:
            protected.setdefault(
                target_id, "entity curation history (merge/split/authority-link)"
            )

    for note in db.query(Note):
        for target_id in set(note.linked_entity_ids or []) & entity_ids:
            protected.setdefault(target_id, "linked from a note")
        for target_id in set(note.linked_claim_ids or []) & claim_ids:
            protected.setdefault(target_id, "linked from a note")

    for ann in db.query(Annotation):
        for target_id in set(getattr(ann, "linked_entity_ids", None) or []) & entity_ids:
            protected.setdefault(target_id, "linked from an annotation")
        for target_id in set(getattr(ann, "linked_claim_ids", None) or []) & claim_ids:
            protected.setdefault(target_id, "linked from an annotation")

    for link in db.query(KnowledgeClaimLink):
        for target_id in {link.claim_id, link.related_claim_id} & claim_ids:
            protected.setdefault(target_id, "has a claim link")

    for link in db.query(LibraryItemLink):
        for target_id, item_type in (
            (link.source_id, link.source_type), (link.target_id, link.target_type)
        ):
            if item_type == LibraryItemType.entity and target_id in entity_ids:
                protected.setdefault(target_id, "linked via a library item link")
            elif item_type == LibraryItemType.claim and target_id in claim_ids:
                protected.setdefault(target_id, "linked via a library item link")

    for entity_id in entity_ids:
        if entity_id in protected:
            continue
        entity = db.get(KnowledgeEntity, entity_id)
        if entity is not None and (entity.metadata or {}).get("authority_links"):
            protected[entity_id] = "has an authority link"

    return protected


def find_draft_only_rows(
    db: Database, *, document_id: str | None = None
) -> tuple[list[KnowledgeEntity], list[KnowledgeClaim], dict[str, str]]:
    """The rows `entity.purge_nlp_draft` would remove, scoped to one
    document (``document_id`` given) or the whole library (``None``), plus
    a ``{id: reason}`` map of otherwise-eligible rows that survive because
    `_protected_ids` found independent evidence of an outside touch.
    Read-only -- shared by the action's dry-run and real-delete paths so
    they can never disagree about what "draft-only" means.
    """
    if document_id:
        claims = db.query(KnowledgeClaim, source_document_id=document_id)
        entities = [
            e for e in db.query(KnowledgeEntity)
            if document_id in (e.source_document_ids or [])
        ]
    else:
        claims = db.query(KnowledgeClaim)
        entities = db.query(KnowledgeEntity)

    claims_by_entity: dict[str, list[KnowledgeClaim]] = {}
    for claim in claims:
        for entity_id in claim.entity_ids or []:
            claims_by_entity.setdefault(entity_id, []).append(claim)

    candidate_claims = [c for c in claims if _claim_is_draft_only(c)]
    candidate_entities = [
        e for e in entities if _entity_is_draft_only(e, claims_by_entity)
    ]

    protected = _protected_ids(
        db,
        {e.id for e in candidate_entities},
        {c.id for c in candidate_claims},
    )

    draft_claims = [c for c in candidate_claims if c.id not in protected]
    draft_entities = [e for e in candidate_entities if e.id not in protected]
    return draft_entities, draft_claims, protected


def _clear_nlp_metadata(db: Database, doc: Document) -> bool:
    """Clear the NLP-stage markers so a later re-run is possible. Returns
    whether anything actually changed (caller only saves on a real diff,
    same discipline `_thumbnail_stage`/`_embed_stage` already use)."""
    metadata = dict(doc.metadata or {})
    changed = False
    for key in _DOC_METADATA_KEYS:
        if metadata.pop(key, None) is not None:
            changed = True
    if changed:
        doc.metadata = metadata
        db.save(doc)
    return changed


def _protected_breakdown(protected: dict[str, str]) -> dict[str, int]:
    """reason -> count, so the caller sees WHY without a full id dump."""
    breakdown: dict[str, int] = {}
    for reason in protected.values():
        breakdown[reason] = breakdown.get(reason, 0) + 1
    return breakdown


def _emit_purge_changes(ctx: ActionContext, spec: ChangeSpec) -> None:
    """Two coalesced typed delete events (never per-row) -- entities and
    claims get distinct real event types, unlike a single `emit_type`
    field's one string."""
    if not ctx.library_path:
        return
    from fichero_server.api.change_stream import emit_change

    if spec.entity_ids:
        try:
            emit_change(
                ctx.library_path, type="entity.deleted",
                entity_ids=spec.entity_ids, actor=ctx.actor,
            )
        except Exception as exc:  # pragma: no cover - best-effort broadcast
            logger.debug("purge_nlp_draft: entity emit failed (ignored): %s", exc)
    if spec.claim_ids:
        try:
            emit_change(
                ctx.library_path, type="claim.deleted",
                claim_ids=spec.claim_ids, actor=ctx.actor,
            )
        except Exception as exc:  # pragma: no cover - best-effort broadcast
            logger.debug("purge_nlp_draft: claim emit failed (ignored): %s", exc)


class PurgeNlpDraftParams(BaseModel):
    """``entity.purge_nlp_draft`` params (#4823 S3)."""

    #: Scope to one document, or the whole library when omitted.
    document_id: str | None = None
    #: Default True -- counts only, nothing deleted. The safety net in
    #: place of full undo (see module docstring).
    dry_run: bool = True


@action(
    "entity.purge_nlp_draft",
    PurgeNlpDraftParams,
    domains=["entity", "claim"],
    undoable=False,
)
def _action_purge_nlp_draft(
    db: Database, params: PurgeNlpDraftParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    draft_entities, draft_claims, protected = find_draft_only_rows(
        db, document_id=params.document_id
    )
    entity_ids = [e.id for e in draft_entities]
    claim_ids = [c.id for c in draft_claims]

    if not params.dry_run:
        # Same low-level delete the single-row audited actions use, so
        # vector-index cleanup + MutationLog both still happen. Claims
        # first -- see module docstring.
        from fichero_server.api.routes.claim.claims import delete_claim_impl
        from fichero_server.api.routes.entity.entities import delete_entity_impl

        for claim_id in claim_ids:
            try:
                delete_claim_impl(db, claim_id, ctx.actor)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "purge_nlp_draft: claim delete failed for %s: %s",
                    claim_id, exc,
                )
        for entity_id in entity_ids:
            try:
                delete_entity_impl(
                    db, entity_id, cascade_claims=False, actor=ctx.actor,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "purge_nlp_draft: entity delete failed for %s: %s",
                    entity_id, exc,
                )

        if params.document_id:
            doc = db.get(Document, params.document_id)
            if doc is not None:
                _clear_nlp_metadata(db, doc)
        else:
            for doc in db.query(Document):
                _clear_nlp_metadata(db, doc)

    result = {
        "entity_count": len(entity_ids),
        "claim_count": len(claim_ids),
        "protected_count": len(protected),
        "protected_reasons": _protected_breakdown(protected),
        "dry_run": params.dry_run,
        "document_id": params.document_id,
    }
    spec = ChangeSpec(
        domains=["entity", "claim"],
        target_ids=entity_ids + claim_ids,
        entity_ids=entity_ids,
        claim_ids=claim_ids,
        after=result,
        emit_type=None if params.dry_run else "entity.deleted",
        emit_fn=_emit_purge_changes if not params.dry_run else None,
    )
    return result, spec
