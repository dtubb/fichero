"""Register step-4 merge/dedup for already-extracted KG rows.

This workflow node mirrors the discrete step-1/2/3 stages:
select the already-imported documents, scope the current library KG rows to
those documents, then re-apply the persisted entity-resolution rules and
claim-suppression rules to the existing entities/claims.

It intentionally does NOT invent new merge heuristics. Entity merges go
through the existing rule resolver + entity-curation merge path; claim
suppression mirrors the existing claim-write semantics; trivial-claim pruning
reuses the shared conservative detector.
"""

from __future__ import annotations

import logging
from fichero_server.core.timeutil import utc_now
from typing import Any

from fichero_server.db import db_manager
from fichero_server.knowledge._common import is_trivial_claim
from fichero_server.models.knowledge import (
    ClaimCurationState,
    ClaimSuppressionRuleAction,
    EntityCurationState,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero_server.llm import LLMConfig
from fichero_server.models import Document
from fichero_server.workflows.curation_guard import (
    CurationSource,
    audited_row_ids,
    clear_conflict,
    record_conflict,
    resolve_curation,
    stamp,
)
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._entity_writer import (
    _apply_entity_resolution_rules,
    _claim_suppression_action,
    _record_source_page,
    upsert_entity,
)
from fichero_server.workflows.tools.import_artifacts import _coerce_documents
from fichero_server.workflows.tools.progress import emit_progress_event
from fichero_server.workflows.tools.sources import files_tool
from fichero_server.workflows.tools._workflow_change_emit import emit_workflow_kg_changes
from fichero_server.workflows.types import DataType, PortDef, State
# NOTE: the api.routes.* handlers are imported at CALL time, not here (#3950).
# A tool importing an API ROUTE is a layering inversion, and it made
# `import fichero_server.workflows.tools` impossible standalone:
#     tools/__init__ -> this module -> api.routes.claim_curation
#     -> api.main -> api.routes.claim_curation (half-initialised)
# See the two use sites in _merge_entity_group / _merge_claim_group below.
from fichero_server.actions.registry import ActionContext

logger = logging.getLogger(__name__)

_REJECTED_ENTITY_STATE = EntityCurationState.rejected


def _descendant_doc_ids(db, root_ids: list[str]) -> set[str]:
    """Return the selected ids plus every descendant document id."""
    queue = list(dict.fromkeys(root_ids))
    seen: set[str] = set()

    while queue:
        doc_id = queue.pop(0)
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        for child in db.query(Document, parent_id=doc_id):
            if child.id not in seen:
                queue.append(child.id)
    return seen


def _scoped_entities(db, scoped_doc_ids: set[str]) -> list[KnowledgeEntity]:
    return [
        entity
        for entity in db.query(KnowledgeEntity)
        if entity.merged_into_id is None
        and scoped_doc_ids.intersection(set(entity.source_document_ids or []))
    ]


def _scoped_claims(db, scoped_doc_ids: set[str]) -> list[KnowledgeClaim]:
    return [
        claim
        for claim in db.query(KnowledgeClaim)
        if claim.merged_into_id is None and claim.source_document_id in scoped_doc_ids
    ]


def _claim_target_state(
    claim: KnowledgeClaim,
    action: ClaimSuppressionRuleAction,
) -> tuple[ClaimCurationState, float]:
    if action == ClaimSuppressionRuleAction.disable:
        return ClaimCurationState.rejected, claim.confidence
    # Existing rows use the same conservative suppression semantics as
    # write-time demotion: mark rejected and cap confidence.
    return ClaimCurationState.rejected, min(claim.confidence, 0.2)


@register_tool(
    name="merge_dedup_only",
    parallelism="reducing",
    display_name="Merge / Dedup",
    description="Apply existing entity-resolution rules, claim suppression, and trivial-claim pruning to existing KG rows",
    category="utility",
    icon="arrow.merge",
    color="teal",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Selected document metadata, typically from Files.documents",
        ),
        PortDef(
            id="barrier",
            name="Barrier (sync)",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
            description="Optional dependency-only input used by chained presets.",
        ),
    ],
    output_ports=[
        PortDef(
            id="summary",
            name="Summary",
            port_type="output",
            data_type=DataType.JSON,
            description="Applied merge/dedup counts",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of scoped documents",
        ),
    ],
    sort_order=38,
)
async def merge_dedup_only(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Apply persisted entity/claim curation rules to the current KG rows."""
    del llm_config  # deterministic stage

    library_path = state.get("library_path", "")
    if not library_path:
        return {"summary": _empty_summary(), "count": 0}

    db = db_manager.get_database(library_path)
    raw_documents = list(inputs.get("documents") or [])
    if not raw_documents:
        fallback = await files_tool(
            inputs={},
            state=state,
            llm_config=LLMConfig(provider="", model=""),
        )
        raw_documents = list(fallback.get("documents") or [])

    documents = _coerce_documents(raw_documents, db, library_path)
    if not documents:
        return {"summary": _empty_summary(), "count": 0}

    scoped_doc_ids = _descendant_doc_ids(db, [document.id for document in documents])
    if not scoped_doc_ids:
        return {"summary": _empty_summary(), "count": 0}

    progress_callback = inputs.get("__progress_callback")
    action_ctx = ActionContext(actor="workflow", library_path=library_path)
    summary = {
        "documents_scoped": len(scoped_doc_ids),
        "entities_examined": 0,
        "entities_merged": 0,
        "entities_reclassified": 0,
        "entities_suppressed": 0,
        "claims_examined": 0,
        "claims_suppressed": 0,
        "claims_pruned_trivial": 0,
        "claim_merges": 0,
        # Curation survival (#4415). A re-run must not regenerate over a
        # correction, and must say when it declined to and why — a preserved
        # row that reports nothing is indistinguishable from a row that was
        # quietly overwritten.
        "entities_curated_preserved": 0,
        "claims_curated_preserved": 0,
        "conflicts_recorded": 0,
        "conflicts_cleared": 0,
    }
    touched_entity_ids: list[str] = []
    touched_claim_ids: list[str] = []

    entities = _scoped_entities(db, scoped_doc_ids)

    # Batched: resolves the provenance of every unmarked row in one pass over
    # the audit tables, where a query per row would run thousands of times on a
    # real folder. Claims are deliberately NOT hoisted up here to share the
    # call — the entity merge below repoints `claim.entity_ids`, and a claim
    # list read before that holds stale ids, which silently breaks the
    # duplicate-grouping key further down.
    audited_ids = audited_row_ids(db, {entity.id for entity in entities})

    summary["entities_examined"] = len(entities)
    await emit_progress_event(
        progress_callback,
        "file_start",
        "",
        "Merge / Dedup entities",
        1,
        2,
        message=f"Applying entity-resolution rules to {len(entities)} entities",
    )

    for entity in entities:
        resolved = _apply_entity_resolution_rules(db, entity.canonical_name, entity.entity_type)

        # A hand-merged or hand-approved entity is a durable statement that the
        # extractor got this wrong. The rules still RUN — an improved rule set
        # may have something to say — but they may not overwrite: the proposal
        # is recorded beside the row instead, so the disagreement is visible
        # and decidable rather than silently resolved in either direction.
        curation = resolve_curation(entity, audited_ids=audited_ids)
        if curation.is_protected:
            if resolved is None:
                agrees = entity.curation_state == _REJECTED_ENTITY_STATE
                proposal: dict | None = {"curation_state": _REJECTED_ENTITY_STATE.value}
                reason = "no entity-resolution rule matched; tool would suppress"
            else:
                target_name, target_type = resolved
                agrees = (
                    target_name == entity.canonical_name and target_type == entity.entity_type
                )
                proposal = {
                    "merge_into_canonical_name": target_name,
                    "merge_into_entity_type": getattr(target_type, "value", target_type),
                }
                reason = "entity-resolution rule would merge this entity elsewhere"

            if agrees:
                conflict_changed = clear_conflict(entity)
                summary["conflicts_cleared"] += int(conflict_changed)
            else:
                conflict_changed = record_conflict(entity, proposal=proposal, reason=reason)
                summary["conflicts_recorded"] += 1

            # Write down the verdict we derived from the audit tables so the
            # next run reads it off the row instead of re-deriving it.
            stamp_changed = stamp(
                entity,
                source=curation.source,
                actor=curation.actor,
                basis=curation.basis,
            )

            if conflict_changed or stamp_changed:
                entity.updated_at = utc_now()
                db.save(entity)
                touched_entity_ids.append(entity.id)
            summary["entities_curated_preserved"] += 1
            continue

        if resolved is None:
            if entity.curation_state != _REJECTED_ENTITY_STATE:
                entity.curation_state = _REJECTED_ENTITY_STATE
                entity.updated_at = utc_now()
                stamp(entity, source=CurationSource.tool, basis="merge_dedup_only")
                db.save(entity)
                touched_entity_ids.append(entity.id)
                summary["entities_suppressed"] += 1
            continue

        target_name, target_type = resolved
        if target_name == entity.canonical_name and target_type == entity.entity_type:
            continue

        target_id = upsert_entity(
            db,
            canonical_name=target_name,
            entity_type=target_type,
            aliases=list(entity.aliases or []),
            description=entity.description,
            source_document_id=(entity.source_document_ids or [None])[0],
        )
        if target_id is None or target_id == entity.id:
            continue

        target_entity = db.get(KnowledgeEntity, target_id)
        if target_entity is None:
            continue
        for source_document_id in entity.source_document_ids or []:
            _record_source_page(db, target_entity, source_document_id)

        # Imported here rather than at module scope: cycle via api.main (#3950).
        from fichero_server.api.routes.kg_entity_curation import EntityMergeRequest, merge_entities

        await merge_entities(
            EntityMergeRequest(
                absorbing_entity_id=target_id,
                absorbed_entity_ids=[entity.id],
                merged_aliases=[entity.canonical_name],
            ),
            db=db,
            ctx=action_ctx,
        )
        touched_entity_ids.extend([target_id, entity.id])
        summary["entities_merged"] += 1
        if target_type != entity.entity_type:
            summary["entities_reclassified"] += 1

    await emit_progress_event(
        progress_callback,
        "file_complete",
        "",
        "Merge / Dedup entities",
        1,
        2,
        message="Applied entity-resolution rules",
    )

    # Read AFTER the entity merges so `entity_ids` reflect the repointing.
    claims = _scoped_claims(db, scoped_doc_ids)
    audited_ids = audited_row_ids(db, {claim.id for claim in claims})
    summary["claims_examined"] = len(claims)
    await emit_progress_event(
        progress_callback,
        "file_start",
        "",
        "Merge / Dedup claims",
        2,
        2,
        message=f"Applying claim suppression to {len(claims)} claims",
    )

    duplicate_groups: dict[tuple[Any, ...], list[KnowledgeClaim]] = {}
    for claim in claims:
        action = _claim_suppression_action(
            db,
            subject_canonical=claim.subject_canonical,
            predicate_verb=claim.predicate_verb,
            object_phrase=claim.object_phrase,
        )

        # A corrected claim outranks both the suppression rules and the
        # trivial-claim pruner. Same contract as entities: compute, decline to
        # overwrite, record the disagreement where it can be seen.
        curation = resolve_curation(claim, audited_ids=audited_ids)
        if curation.is_protected:
            proposal: dict | None = None
            reason = ""
            if action is not None:
                next_state, next_confidence = _claim_target_state(claim, action)
                if claim.curation_state != next_state or claim.confidence != next_confidence:
                    proposal = {
                        "curation_state": next_state.value,
                        "confidence": next_confidence,
                    }
                    reason = "claim-suppression rule would demote this claim"
            if proposal is None and is_trivial_claim(claim):
                next_confidence = min(claim.confidence, 0.2)
                if (
                    claim.curation_state != ClaimCurationState.rejected
                    or claim.confidence != next_confidence
                ):
                    proposal = {
                        "curation_state": ClaimCurationState.rejected.value,
                        "confidence": next_confidence,
                    }
                    reason = "trivial-claim pruner would reject this claim"

            if proposal is None:
                conflict_changed = clear_conflict(claim)
                summary["conflicts_cleared"] += int(conflict_changed)
            else:
                conflict_changed = record_conflict(claim, proposal=proposal, reason=reason)
                summary["conflicts_recorded"] += 1

            stamp_changed = stamp(
                claim,
                source=curation.source,
                actor=curation.actor,
                basis=curation.basis,
            )

            if conflict_changed or stamp_changed:
                claim.updated_at = utc_now()
                db.save(claim)
                touched_claim_ids.append(claim.id)
            summary["claims_curated_preserved"] += 1

            key = (
                claim.source_document_id,
                claim.source_page_label,
                claim.subject_canonical,
                claim.predicate_verb,
                claim.object_phrase,
                tuple(sorted(claim.entity_ids or [])),
            )
            duplicate_groups.setdefault(key, []).append(claim)
            continue

        if action is not None:
            next_state, next_confidence = _claim_target_state(claim, action)
            if (
                claim.curation_state != next_state
                or claim.confidence != next_confidence
            ):
                claim.curation_state = next_state
                claim.confidence = next_confidence
                claim.updated_at = utc_now()
                stamp(claim, source=CurationSource.tool, basis="merge_dedup_only")
                db.save(claim)
                touched_claim_ids.append(claim.id)
                summary["claims_suppressed"] += 1

        if is_trivial_claim(claim):
            next_confidence = min(claim.confidence, 0.2)
            if (
                claim.curation_state != ClaimCurationState.rejected
                or claim.confidence != next_confidence
            ):
                claim.curation_state = ClaimCurationState.rejected
                claim.confidence = next_confidence
                claim.updated_at = utc_now()
                stamp(claim, source=CurationSource.tool, basis="merge_dedup_only")
                db.save(claim)
                touched_claim_ids.append(claim.id)
                summary["claims_pruned_trivial"] += 1

        key = (
            claim.source_document_id,
            claim.source_page_label,
            claim.subject_canonical,
            claim.predicate_verb,
            claim.object_phrase,
            tuple(sorted(claim.entity_ids or [])),
        )
        duplicate_groups.setdefault(key, []).append(claim)

    for grouped_claims in duplicate_groups.values():
        live_claims = [claim for claim in grouped_claims if claim.merged_into_id is None]
        if len(live_claims) < 2:
            continue
        survivor = min(live_claims, key=lambda claim: (claim.created_at, claim.id))

        # Absorbing a curated claim destroys it just as surely as rewriting its
        # curation_state — it stops being a live row. A corrected claim is
        # therefore never in the absorbed set; the duplicate it "should" have
        # folded into is recorded as a disagreement instead.
        absorbed = []
        for claim in live_claims:
            if claim.id == survivor.id:
                continue
            claim_curation = resolve_curation(claim, audited_ids=audited_ids)
            if claim_curation.is_protected:
                if record_conflict(
                    claim,
                    proposal={"merge_into_claim_id": survivor.id},
                    reason="claim deduplication would absorb this claim",
                ):
                    claim.updated_at = utc_now()
                    db.save(claim)
                    touched_claim_ids.append(claim.id)
                summary["conflicts_recorded"] += 1
                summary["claims_curated_preserved"] += 1
                continue
            absorbed.append(claim)

        if not absorbed:
            continue
        # Imported here rather than at module scope: cycle via api.main (#3950).
        from fichero_server.api.routes.claim.curation import ClaimMergeRequest, merge_claims

        await merge_claims(
            ClaimMergeRequest(
                surviving_claim_id=survivor.id,
                absorbed_claim_ids=[claim.id for claim in absorbed],
            ),
            db=db,
            ctx=action_ctx,
        )
        touched_claim_ids.extend([survivor.id, *[claim.id for claim in absorbed]])
        summary["claim_merges"] += len(absorbed)

    await emit_progress_event(
        progress_callback,
        "file_complete",
        "",
        "Merge / Dedup claims",
        2,
        2,
        message="Applied claim suppression and trivial-claim pruning",
    )
    if touched_entity_ids or touched_claim_ids:
        emit_workflow_kg_changes(
            str(db.path.parent),
            entity_ids=touched_entity_ids,
            claim_ids=touched_claim_ids,
            document_ids=sorted(scoped_doc_ids),
        )

    return {"summary": summary, "count": len(scoped_doc_ids)}


def _empty_summary() -> dict[str, int]:
    return {
        "documents_scoped": 0,
        "entities_examined": 0,
        "entities_merged": 0,
        "entities_reclassified": 0,
        "entities_suppressed": 0,
        "claims_examined": 0,
        "claims_suppressed": 0,
        "claims_pruned_trivial": 0,
        "claim_merges": 0,
        "entities_curated_preserved": 0,
        "claims_curated_preserved": 0,
        "conflicts_recorded": 0,
        "conflicts_cleared": 0,
    }
