"""Database migrations for schema upgrades with dry-run, rollback, and audit trail.

All migration functions are idempotent — safe to run multiple times.
Run via: PYTHONPATH=fichero-server/src python scripts/migrate_*.py

Migration Framework Features:
- Dry-run mode: Validate migrations without making changes
- Rollback support: Revert migrations with before/after state tracking
- Audit trail: Log all mutations for compliance and debugging
- Batch operations: Process large datasets in chunks
- Progress callbacks: Real-time progress reporting for long operations

Usage:
    from fichero_server.db.migrations.runner import MigrationRunner
    from fichero_server.db import Database

    db = Database(path)
    runner = MigrationRunner(db)

    # Dry-run to validate
    result = runner.migrate_claims_to_multi_source(dry_run=True)
    print(f"Would migrate {result.migrated} claims")

    # Execute with rollback capture
    result = runner.migrate_claims_to_multi_source(dry_run=False)
    print(f"Migrated {result.migrated} claims, audit_id={result.audit_id}")

    # Rollback if needed
    runner.rollback(result.audit_id)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from fichero_server.core.timeutil import utc_now
from enum import Enum
from typing import Callable, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

from fichero_server.db import Database
from fichero_server.kg._common import parse_kwarg_repr
from fichero_server.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeClaimLink,
    SourceType,
    MutationLog,
    MutationOperationType,
)
from fichero_server.models import Document

logger = logging.getLogger(__name__)
T = TypeVar("T")


class MigrationRunRecord(BaseModel):
    """Persisted migration run summary for status lookups."""

    id: str = Field(description="Stable record id; matches run_id")
    run_id: str
    migration_name: str
    status: str
    migrated: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: bool = False
    audit_id: str | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    details: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MigrationStatus(str, Enum):
    """Status of a migration operation."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    rolled_back = "rolled_back"


class MigrationType(str, Enum):
    """Type of migration operation."""

    schema = "schema"  # Schema changes
    data = "data"  # Data transformations
    backfill = "backfill"  # Fill missing derived data
    repair = "repair"  # Fix corrupted/incorrect data


@dataclass
class MigrationResult:
    """Result of a migration operation."""

    migration_name: str
    status: MigrationStatus
    migrated: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: bool = False
    audit_id: str | None = None
    error_message: str | None = None
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    details: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> int | None:
        """Duration in milliseconds."""
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            "migration_name": self.migration_name,
            "status": self.status.value,
            "migrated": self.migrated,
            "skipped": self.skipped,
            "failed": self.failed,
            "dry_run": self.dry_run,
            "audit_id": self.audit_id,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


@dataclass
class RollbackResult:
    """Result of a rollback operation."""

    audit_id: str
    status: MigrationStatus
    restored: int = 0
    failed: int = 0
    error_message: str | None = None
    started_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None


class MigrationRunner:
    """Runner for database migrations with dry-run, rollback, and audit support."""

    def __init__(self, db: Database, agent_id: str = "migration_runner"):
        self.db = db
        self.agent_id = agent_id
        self._progress_callback: Callable[[str, int, int], None] | None = None

    def set_progress_callback(
        self, callback: Callable[[str, int, int], None] | None
    ) -> None:
        """Set callback for progress updates: (operation, current, total)."""
        self._progress_callback = callback

    def _report_progress(self, operation: str, current: int, total: int) -> None:
        """Report progress if callback is set."""
        if self._progress_callback:
            self._progress_callback(operation, current, total)

    def save_run_result(self, result: MigrationResult) -> str:
        """Persist a run summary so status lookups round-trip the returned run_id."""
        run_id = result.details.get("run_id") or result.audit_id
        if not run_id:
            raise ValueError("Migration result is missing a run_id")
        self.db.save(
            MigrationRunRecord(
                id=run_id,
                run_id=run_id,
                migration_name=result.migration_name,
                status=result.status.value,
                migrated=result.migrated,
                skipped=result.skipped,
                failed=result.failed,
                dry_run=result.dry_run,
                audit_id=result.audit_id,
                error_message=result.error_message,
                started_at=result.started_at,
                completed_at=result.completed_at,
                details=result.details,
            )
        )
        return run_id

    def _log_mutation(
        self,
        entity_type: str,
        entity_id: str,
        operation: MutationOperationType,
        before_state: dict | None = None,
        after_state: dict | None = None,
        changed_fields: list[str] | None = None,
        run_id: str | None = None,
    ) -> str:
        """Log a mutation for audit trail and potential rollback."""
        mutation = MutationLog(
            id=uuid4().hex,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            before_state=before_state,
            after_state=after_state,
            changed_fields=changed_fields,
            run_id=run_id or f"migration_{uuid4().hex[:8]}",
            agent_id=self.agent_id,
            created_by="migration_runner",
        )
        self.db.save(mutation)
        return mutation.id

    def migrate_claims_to_multi_source(
        self,
        dry_run: bool = False,
        batch_size: int | None = None,
        limit: int | None = None,
    ) -> MigrationResult:
        """Migrate KnowledgeClaim records from single-source to multi-source schema.

        Idempotent: checks source_type to avoid double-migration.
        Only migrates claims where source_type is still the default (document) AND
        source_ids is empty.

        Args:
            dry_run: If True, only count what would be migrated without making changes
            batch_size: Process in batches (None = all at once)
            limit: Maximum number of claims to process (None = no limit)

        Returns:
            MigrationResult with counts and audit trail ID
        """
        result = MigrationResult(
            migration_name="migrate_claims_to_multi_source",
            status=MigrationStatus.running,
            dry_run=dry_run,
        )

        try:
            all_claims = self.db.all(KnowledgeClaim)
            run_id = f"migrate_{uuid4().hex[:8]}"
            processed = 0

            for claim in all_claims:
                if limit and processed >= limit:
                    break

                # Already migrated — skip
                if claim.source_type != SourceType.document or claim.source_ids:
                    result.skipped += 1
                    continue

                # Capture before state for rollback
                before_state = {
                    "source_ids": claim.source_ids.copy() if claim.source_ids else [],
                    "source_page_labels": (
                        claim.source_page_labels.copy()
                        if claim.source_page_labels
                        else []
                    ),
                }

                if not dry_run:
                    # Apply migration
                    claim.source_ids = [claim.source_document_id]
                    if not claim.source_page_labels and claim.source_page_label:
                        claim.source_page_labels = [claim.source_page_label]

                    # Save the claim
                    self.db.save(claim)

                    # Log mutation for rollback support
                    after_state = {
                        "source_ids": claim.source_ids.copy(),
                        "source_page_labels": claim.source_page_labels.copy(),
                    }
                    self._log_mutation(
                        entity_type="KnowledgeClaim",
                        entity_id=claim.id,
                        operation=MutationOperationType.update,
                        before_state=before_state,
                        after_state=after_state,
                        changed_fields=["source_ids", "source_page_labels"],
                        run_id=run_id,
                    )
                    if not result.audit_id:
                        result.audit_id = run_id

                result.migrated += 1
                processed += 1

                if batch_size and processed % batch_size == 0:
                    self._report_progress("migrate_claims", processed, len(all_claims))

            result.status = MigrationStatus.completed
            result.completed_at = utc_now()
            result.details = {"run_id": run_id, "total_claims": len(all_claims)}

            logger.info(
                f"Migration complete: {result.migrated} migrated, "
                f"{result.skipped} skipped"
            )

        except Exception as e:
            result.status = MigrationStatus.failed
            result.error_message = str(e)
            result.completed_at = utc_now()
            logger.error(f"Migration failed: {e}")
            raise

        return result

    def backfill_claim_source_metadata(
        self,
        dry_run: bool = False,
        batch_size: int | None = None,
    ) -> MigrationResult:
        """Backfill source_metadata for claims from their source documents.

        Populates claim.source_metadata from document metadata for claims
        that have a source_document_id but no source_metadata.

        Args:
            dry_run: If True, only count what would be backfilled
            batch_size: Process in batches (None = all at once)

        Returns:
            MigrationResult with counts and audit trail ID
        """
        result = MigrationResult(
            migration_name="backfill_claim_source_metadata",
            status=MigrationStatus.running,
            dry_run=dry_run,
        )

        try:
            all_claims = self.db.all(KnowledgeClaim)
            run_id = f"backfill_{uuid4().hex[:8]}"
            processed = 0

            for claim in all_claims:
                # Skip if already has source_metadata
                if claim.source_metadata is not None:
                    result.skipped += 1
                    continue

                # Get source document
                source_doc = self.db.get(Document, claim.source_document_id)
                if not source_doc or not source_doc.metadata:
                    result.skipped += 1
                    continue

                # Capture before state
                before_state = (
                    {"source_metadata": None}
                    if claim.source_metadata is None
                    else {"source_metadata": claim.source_metadata.model_dump()}
                )

                if not dry_run:
                    # Build source_metadata from document
                    from fichero_server.models.knowledge import SourceMetadata

                    doc_meta = source_doc.metadata
                    source_metadata = SourceMetadata(
                        title=doc_meta.get("title")
                        or (source_doc.name if source_doc else None),
                        date=doc_meta.get("date"),
                        publisher=doc_meta.get("publisher"),
                        rights=doc_meta.get("rights"),
                        language=doc_meta.get("language"),
                    )
                    claim.source_metadata = source_metadata
                    self.db.save(claim)

                    # Log mutation
                    after_state = {"source_metadata": source_metadata.model_dump()}
                    self._log_mutation(
                        entity_type="KnowledgeClaim",
                        entity_id=claim.id,
                        operation=MutationOperationType.update,
                        before_state=before_state,
                        after_state=after_state,
                        changed_fields=["source_metadata"],
                        run_id=run_id,
                    )
                    if not result.audit_id:
                        result.audit_id = run_id

                result.migrated += 1
                processed += 1

                if batch_size and processed % batch_size == 0:
                    self._report_progress(
                        "backfill_source_metadata", processed, len(all_claims)
                    )

            result.status = MigrationStatus.completed
            result.completed_at = utc_now()
            result.details = {"run_id": run_id, "total_claims": len(all_claims)}

            logger.info(
                f"Backfill complete: {result.migrated} updated, "
                f"{result.skipped} skipped"
            )

        except Exception as e:
            result.status = MigrationStatus.failed
            result.error_message = str(e)
            result.completed_at = utc_now()
            logger.error(f"Backfill failed: {e}")
            raise

        return result

    def repair_orphaned_claim_links(
        self,
        dry_run: bool = False,
    ) -> MigrationResult:
        """Repair claim links pointing to deleted claims.

        Identifies KnowledgeClaimLink records where either claim_id or
        related_claim_id points to a non-existent claim, and removes them.

        Args:
            dry_run: If True, only count what would be repaired

        Returns:
            MigrationResult with counts of removed links
        """
        result = MigrationResult(
            migration_name="repair_orphaned_claim_links",
            status=MigrationStatus.running,
            dry_run=dry_run,
        )

        try:
            all_links = self.db.all(KnowledgeClaimLink)
            all_claim_ids = {c.id for c in self.db.all(KnowledgeClaim)}
            run_id = f"repair_{uuid4().hex[:8]}"

            for link in all_links:
                claim_exists = link.claim_id in all_claim_ids
                related_exists = link.related_claim_id in all_claim_ids

                if claim_exists and related_exists:
                    result.skipped += 1
                    continue

                # Orphaned link
                if not dry_run:
                    # Log before deletion
                    self._log_mutation(
                        entity_type="KnowledgeClaimLink",
                        entity_id=link.id,
                        operation=MutationOperationType.delete,
                        before_state=link.model_dump(),
                        after_state=None,
                        changed_fields=["deleted"],
                        run_id=run_id,
                    )
                    self.db.delete(link)

                    if not result.audit_id:
                        result.audit_id = run_id

                result.migrated += 1

            result.status = MigrationStatus.completed
            result.completed_at = utc_now()
            result.details = {
                "run_id": run_id,
                "total_links": len(all_links),
                "orphaned_removed": result.migrated,
            }

            logger.info(f"Repair complete: {result.migrated} orphaned links removed")

        except Exception as e:
            result.status = MigrationStatus.failed
            result.error_message = str(e)
            result.completed_at = utc_now()
            logger.error(f"Repair failed: {e}")
            raise

        return result

    def repair_kg_svo_repr_leak(
        self,
        dry_run: bool = False,
    ) -> MigrationResult:
        """Repair KG rows where a leaked kwarg-repr was stored verbatim.

        Weaker / fallback LLMs sometimes echoed the prompt's kwarg example
        ("verb='X', object='Y'") back into a single field. Before
        ``extractors._normalize_kwarg_repr_fields`` caught it at write
        time (#1030), the literal repr composed into
        ``KnowledgeClaim.text``, ``predicate_verb``/``object_phrase``,
        ``metadata['verb'/'object']``, ``source_excerpt``, and
        ``KnowledgeEntity.description`` — rendering raw
        ``verb='...', object='...'`` in the inspector and KG viewer.

        For each polluted row this re-parses the repr, restores the
        structured SVO fields, recomposes a readable text/description,
        and clears the repr from ``source_excerpt`` (it was never a real
        verbatim quote). Detection uses ``kg._common.parse_kwarg_repr``,
        the same primitive the forward write-time guard uses.

        Idempotent: rows that no longer parse as a repr are skipped.

        Args:
            dry_run: If True, only count what would be repaired.

        Returns:
            MigrationResult with counts and audit trail ID.
        """
        result = MigrationResult(
            migration_name="repair_kg_svo_repr_leak",
            status=MigrationStatus.running,
            dry_run=dry_run,
        )
        try:
            run_id = f"repair_{uuid4().hex[:8]}"
            claims = self.db.all(KnowledgeClaim)
            entities = self.db.all(KnowledgeEntity)

            # Per-row try/except: a single bad row must not abort the
            # whole cleanup — the migration may persist a row mutation
            # *before* its audit-log row writes, so an abort on row N+1
            # would leave N's mutation un-audited and unrecoverable.
            # The failed counter + the logged id give operators what
            # they need to recover.
            claims_repaired = 0
            for claim in claims:
                try:
                    if self._repair_claim_svo_repr(claim, dry_run, run_id):
                        claims_repaired += 1
                        result.migrated += 1
                    else:
                        result.skipped += 1
                except Exception as row_err:
                    logger.error(
                        "SVO repr repair: claim %s failed — mutation may be "
                        "saved without an audit row: %s",
                        claim.id,
                        row_err,
                    )
                    result.failed += 1

            entities_repaired = 0
            for entity in entities:
                try:
                    if self._repair_entity_svo_repr(entity, dry_run, run_id):
                        entities_repaired += 1
                        result.migrated += 1
                    else:
                        result.skipped += 1
                except Exception as row_err:
                    logger.error(
                        "SVO repr repair: entity %s failed — mutation may be "
                        "saved without an audit row: %s",
                        entity.id,
                        row_err,
                    )
                    result.failed += 1

            result.status = MigrationStatus.completed
            result.completed_at = utc_now()
            if result.migrated and not dry_run:
                result.audit_id = run_id
            result.details = {
                "run_id": run_id,
                "total_claims": len(claims),
                "total_entities": len(entities),
                "claims_repaired": claims_repaired,
                "entities_repaired": entities_repaired,
            }

            logger.info(
                f"SVO repr repair complete: {claims_repaired} claims, "
                f"{entities_repaired} entities repaired, "
                f"{result.skipped} skipped"
            )

        except Exception as e:
            result.status = MigrationStatus.failed
            result.error_message = str(e)
            result.completed_at = utc_now()
            logger.error(f"SVO repr repair failed: {e}")
            raise

        return result

    def _repair_claim_svo_repr(
        self,
        claim: KnowledgeClaim,
        dry_run: bool,
        run_id: str,
    ) -> list[str]:
        """Repair leaked SVO repr in a single claim. Returns the list of
        changed field names (empty when nothing needs repair)."""
        meta = claim.metadata or {}
        parsed = (
            parse_kwarg_repr(claim.text)
            or parse_kwarg_repr(claim.predicate_verb or "")
            or parse_kwarg_repr(claim.object_phrase or "")
            or parse_kwarg_repr(str(meta.get("verb") or ""))
            or parse_kwarg_repr(str(meta.get("object") or ""))
            or parse_kwarg_repr(claim.source_excerpt or "")
        )
        if not parsed:
            return []

        verb = (parsed.get("verb") or "").strip()
        obj = (parsed.get("object") or "").strip()
        # A repr that yielded neither verb nor object carries no
        # recoverable SVO — leave the row for manual review rather than
        # blanking it.
        if not verb and not obj:
            return []

        new_predicate_verb = claim.predicate_verb
        if verb and (
            not claim.predicate_verb or parse_kwarg_repr(claim.predicate_verb)
        ):
            new_predicate_verb = verb

        new_object_phrase = claim.object_phrase
        if obj and (
            not claim.object_phrase or parse_kwarg_repr(claim.object_phrase)
        ):
            new_object_phrase = obj

        new_meta = dict(meta)
        if verb and (
            not new_meta.get("verb")
            or parse_kwarg_repr(str(new_meta.get("verb")))
        ):
            new_meta["verb"] = verb
        if obj and (
            not new_meta.get("object")
            or parse_kwarg_repr(str(new_meta.get("object")))
        ):
            new_meta["object"] = obj

        new_excerpt = claim.source_excerpt
        if claim.source_excerpt and parse_kwarg_repr(claim.source_excerpt):
            new_excerpt = None

        new_text = claim.text
        if parse_kwarg_repr(claim.text):
            predicate = f"{verb} {obj}".strip()
            # Date-style claims have no entity_ids and were composed
            # as "{stem}: {verb} {obj}." — mirror that shape on repair.
            is_date_claim = not claim.entity_ids and bool(
                new_meta.get("date_text") or new_meta.get("date_normalized")
            )
            if is_date_claim:
                stem = str(
                    new_meta.get("subject")
                    or new_meta.get("date_normalized")
                    or new_meta.get("date_text")
                    or ""
                ).strip()
                if stem and predicate:
                    new_text = f"{stem}: {predicate}."
                else:
                    new_text = stem or predicate
            else:
                subject = str(
                    claim.subject_canonical or new_meta.get("subject") or ""
                ).strip()
                if subject and predicate:
                    # Deliberately NOT routed through
                    # knowledge._common.render_statement (#4172): a migration
                    # must keep producing byte-identical output forever, so it
                    # cannot follow a helper whose ordering is meant to change
                    # for VSO/SOV languages. Frozen on purpose.
                    new_text = f"{subject} {predicate}."
                else:
                    new_text = subject or predicate

        changed: list[str] = []
        if new_text != claim.text:
            changed.append("text")
        if new_predicate_verb != claim.predicate_verb:
            changed.append("predicate_verb")
        if new_object_phrase != claim.object_phrase:
            changed.append("object_phrase")
        if new_meta != meta:
            changed.append("metadata")
        if new_excerpt != claim.source_excerpt:
            changed.append("source_excerpt")

        if not changed or dry_run:
            return changed

        before_state = {
            "text": claim.text,
            "predicate_verb": claim.predicate_verb,
            "object_phrase": claim.object_phrase,
            "source_excerpt": claim.source_excerpt,
            "metadata": dict(meta),
        }
        claim.text = new_text
        claim.predicate_verb = new_predicate_verb
        claim.object_phrase = new_object_phrase
        claim.metadata = new_meta
        claim.source_excerpt = new_excerpt
        self.db.save(claim)
        logger.info(
            "SVO repr repair: claim %s fields %s rewritten",
            claim.id,
            ",".join(changed),
        )
        self._log_mutation(
            entity_type="KnowledgeClaim",
            entity_id=claim.id,
            operation=MutationOperationType.update,
            before_state=before_state,
            after_state={
                "text": claim.text,
                "predicate_verb": claim.predicate_verb,
                "object_phrase": claim.object_phrase,
                "source_excerpt": claim.source_excerpt,
                "metadata": dict(claim.metadata or {}),
            },
            changed_fields=changed,
            run_id=run_id,
        )
        return changed

    def _repair_entity_svo_repr(
        self,
        entity: KnowledgeEntity,
        dry_run: bool,
        run_id: str,
    ) -> list[str]:
        """Repair leaked SVO repr in a single entity's description."""
        if not entity.description:
            return []
        parsed = parse_kwarg_repr(entity.description)
        if not parsed:
            return []
        verb = (parsed.get("verb") or "").strip()
        obj = (parsed.get("object") or "").strip()
        # Mirror the claim-side guard: a repr that parsed but yielded
        # neither verb nor object has no recoverable SVO. Leave the row
        # for manual review rather than blanking the description.
        if not verb and not obj:
            return []
        new_description = f"{verb} {obj}".strip()
        if not new_description or new_description == entity.description:
            return []
        if dry_run:
            return ["description"]
        before_state = {"description": entity.description}
        entity.description = new_description
        self.db.save(entity)
        self._log_mutation(
            entity_type="KnowledgeEntity",
            entity_id=entity.id,
            operation=MutationOperationType.update,
            before_state=before_state,
            after_state={"description": entity.description},
            changed_fields=["description"],
            run_id=run_id,
        )
        logger.info(
            "SVO repr repair: entity %s description rewritten", entity.id
        )
        return ["description"]

    def rollback(self, run_id: str) -> RollbackResult:
        """Rollback mutations from a migration run.

        Reverts all mutations logged with the given run_id, restoring
        entities to their before_state.

        Args:
            run_id: The migration run ID to rollback

        Returns:
            RollbackResult with counts of restored entities
        """
        result = RollbackResult(audit_id=run_id, status=MigrationStatus.running)

        try:
            # Find all mutations for this run
            mutations = self.db.query(MutationLog, run_id=run_id)

            if not mutations:
                result.status = MigrationStatus.failed
                result.error_message = f"No mutations found for run_id: {run_id}"
                return result

            # Sort by created_at descending to undo in reverse order
            mutations.sort(key=lambda m: m.created_at, reverse=True)

            for mutation in mutations:
                try:
                    if mutation.operation == MutationOperationType.create:
                        # Delete the created entity
                        self._rollback_create(mutation)
                    elif mutation.operation == MutationOperationType.update:
                        # Restore to before_state
                        self._rollback_update(mutation)
                    elif mutation.operation == MutationOperationType.delete:
                        # Recreate from before_state
                        self._rollback_delete(mutation)

                    result.restored += 1

                except Exception as e:
                    logger.error(f"Failed to rollback mutation {mutation.id}: {e}")
                    result.failed += 1

            # Mark mutations as rolled back
            for mutation in mutations:
                mutation.reversal_id = f"rollback_{uuid4().hex[:8]}"
                self.db.save(mutation)

            result.status = MigrationStatus.rolled_back
            result.completed_at = utc_now()

            logger.info(
                f"Rollback complete: {result.restored} restored, {result.failed} failed"
            )

        except Exception as e:
            result.status = MigrationStatus.failed
            result.error_message = str(e)
            result.completed_at = utc_now()
            logger.error(f"Rollback failed: {e}")
            raise

        return result

    def _rollback_create(self, mutation: MutationLog) -> None:
        """Rollback a create operation by deleting the entity."""
        # Get the model class from entity_type
        model_cls = self._get_model_class(mutation.entity_type)
        if model_cls:
            entity = self.db.get(model_cls, mutation.entity_id)
            if entity:
                self.db.delete(entity)

    def _rollback_update(self, mutation: MutationLog) -> None:
        """Rollback an update operation by restoring before_state."""
        if not mutation.before_state:
            return

        model_cls = self._get_model_class(mutation.entity_type)
        if not model_cls:
            return

        entity = self.db.get(model_cls, mutation.entity_id)
        if not entity:
            return

        # Restore fields from before_state
        for field_name, value in mutation.before_state.items():
            if hasattr(entity, field_name):
                setattr(entity, field_name, value)

        self.db.save(entity)

    def _rollback_delete(self, mutation: MutationLog) -> None:
        """Rollback a delete operation by recreating the entity."""
        if not mutation.before_state:
            return

        model_cls = self._get_model_class(mutation.entity_type)
        if not model_cls:
            return

        # Recreate entity from before_state
        entity = model_cls(**mutation.before_state)
        self.db.save(entity)

    def _get_model_class(self, entity_type: str) -> type | None:
        """Get model class from entity type name."""
        model_map = {
            "KnowledgeClaim": KnowledgeClaim,
            "KnowledgeEntity": KnowledgeEntity,
            "KnowledgeClaimLink": KnowledgeClaimLink,
            "Document": Document,
            "MutationLog": MutationLog,
        }
        return model_map.get(entity_type)

    def get_migration_status(self, run_id: str) -> dict | None:
        """Get status of a migration run from its audit logs."""
        records = self.db.query(MigrationRunRecord, run_id=run_id)
        run_records = [record for record in records if isinstance(record, MigrationRunRecord)]
        if run_records:
            return run_records[0].model_dump()

        mutations = self.db.query(MutationLog, run_id=run_id)
        if not mutations:
            return None

        all_reversed = all(bool(m.reversal_id) for m in mutations)
        status = MigrationStatus.rolled_back.value if all_reversed else MigrationStatus.completed.value

        return {
            "run_id": run_id,
            "status": status,
            "total_mutations": len(mutations),
            "entity_types": list(set(m.entity_type for m in mutations)),
            "created_at": min(m.created_at for m in mutations).isoformat(),
            "last_mutation": max(m.created_at for m in mutations).isoformat(),
        }

    def validate_migration_safety(
        self, migration_name: str, sample_size: int = 100
    ) -> dict:
        """Validate migration safety on a sample of data.

        Returns validation report with warnings and errors.
        """
        validation = {
            "migration_name": migration_name,
            "sample_size": sample_size,
            "warnings": [],
            "errors": [],
            "can_run": True,
        }

        if migration_name == "migrate_claims_to_multi_source":
            claims = self.db.all(KnowledgeClaim)[:sample_size]
            for claim in claims:
                if claim.source_type != SourceType.document:
                    continue
                if not claim.source_document_id:
                    validation["errors"].append(
                        f"Claim {claim.id} has no source_document_id"
                    )
                    validation["can_run"] = False

        return validation


# Legacy standalone migration function for backward compatibility
def migrate_claims_to_multi_source(
    db: Database, dry_run: bool = False
) -> tuple[int, int]:
    """Migrate KnowledgeClaim records from single-source to multi-source schema.

    Legacy function for backward compatibility.
    Use MigrationRunner for new code.

    Returns (migrated_count, skipped_count).
    """
    runner = MigrationRunner(db)
    result = runner.migrate_claims_to_multi_source(dry_run=dry_run)
    return result.migrated, result.skipped
