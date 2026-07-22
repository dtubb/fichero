"""API routes for knowledge migration operations.

Provides endpoints for:
- Running migrations with dry-run support
- Checking migration status
- Rolling back migrations
- Validating migration safety
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.db import Database

from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.db.migrations.runner import MigrationRunner

router = APIRouter(prefix="/migrations", tags=["migrations"])


# =============================================================================
# Request/Response Models
# =============================================================================


class MigrationCommand(str, Enum):
    """Available migration commands."""

    migrate_claims_to_multi_source = "migrate_claims_to_multi_source"
    backfill_claim_source_metadata = "backfill_claim_source_metadata"
    repair_orphaned_claim_links = "repair_orphaned_claim_links"
    repair_kg_svo_repr_leak = "repair_kg_svo_repr_leak"


class MigrationRunRequest(BaseModel):
    """Request to run a migration."""

    command: MigrationCommand
    dry_run: bool = Field(default=False, description="Validate without making changes")
    batch_size: int | None = Field(default=None, ge=1, description="Process in batches")
    limit: int | None = Field(
        default=None, ge=1, description="Maximum items to process"
    )


class MigrationStatusResponse(BaseModel):
    """Status of a migration run."""

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
    duration_ms: int | None = None
    details: dict = Field(default_factory=dict)


class MigrationStatusQuery(BaseModel):
    """Request to query migration status."""

    run_id: str = Field(description="Migration run ID from previous run")


class RollbackRequest(BaseModel):
    """Request to rollback a migration."""

    run_id: str = Field(description="Migration run ID to rollback")


class RollbackResponse(BaseModel):
    """Response from rollback operation."""

    audit_id: str
    status: str
    restored: int = 0
    failed: int = 0
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class MigrationValidationRequest(BaseModel):
    """Request to validate migration safety."""

    command: MigrationCommand
    sample_size: int = Field(default=100, ge=1, le=1000)


class MigrationValidationResponse(BaseModel):
    """Validation result for a migration."""

    migration_name: str
    sample_size: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    can_run: bool = True


class MigrationInfo(BaseModel):
    """Information about an available migration."""

    name: str
    description: str
    type: str
    idempotent: bool = True


class MigrationListResponse(BaseModel):
    """Response listing available migrations."""

    migrations: list[MigrationInfo]


class DataIntegrityCheckResponse(BaseModel):
    """Response from data integrity check."""

    entity_count: int
    claim_count: int
    link_count: int
    orphaned_links: int = 0
    orphaned_entities: int = 0
    claims_without_sources: int = 0
    checks_passed: bool


AVAILABLE_MIGRATIONS = [
    MigrationInfo(
        name="migrate_claims_to_multi_source",
        description="Migrate KnowledgeClaim from single-source to multi-source schema",
        type="data",
        idempotent=True,
    ),
    MigrationInfo(
        name="backfill_claim_source_metadata",
        description="Backfill source_metadata for claims from their source documents",
        type="backfill",
        idempotent=True,
    ),
    MigrationInfo(
        name="repair_orphaned_claim_links",
        description="Remove claim links pointing to deleted claims",
        type="repair",
        idempotent=True,
    ),
    MigrationInfo(
        name="repair_kg_svo_repr_leak",
        description=(
            "Repair claims/entities where a leaked kwarg-repr "
            "(verb='X', object='Y') was stored verbatim (#1030)"
        ),
        type="repair",
        idempotent=True,
    ),
]


# =============================================================================
# Helper Functions
# =============================================================================


def _migration_result_to_response(result) -> MigrationStatusResponse:
    """Convert MigrationResult to API response."""
    return MigrationStatusResponse(
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
        duration_ms=result.duration_ms,
        details=result.details,
    )


def _rollback_result_to_response(result) -> RollbackResponse:
    """Convert RollbackResult to API response."""
    return RollbackResponse(
        audit_id=result.audit_id,
        status=result.status.value,
        restored=result.restored,
        failed=result.failed,
        error_message=result.error_message,
        started_at=result.started_at,
        completed_at=result.completed_at,
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=MigrationListResponse)
async def list_migrations(
    db: Database = Depends(get_library_database),
) -> MigrationListResponse:
    """List all available migrations with descriptions."""
    return MigrationListResponse(migrations=AVAILABLE_MIGRATIONS)


@router.post("/run", response_model=MigrationStatusResponse)
async def run_migration(
    request: MigrationRunRequest,
    db: Database = Depends(get_library_database_for_write),
) -> MigrationStatusResponse:
    """Run a migration with optional dry-run mode.

    Dry-run mode validates the migration and returns counts without
    making any changes to the database. The audit_id can be used
    to rollback the migration if needed.
    """
    runner = MigrationRunner(db)

    try:
        if request.command == MigrationCommand.migrate_claims_to_multi_source:
            result = runner.migrate_claims_to_multi_source(
                dry_run=request.dry_run,
                batch_size=request.batch_size,
                limit=request.limit,
            )
        elif request.command == MigrationCommand.backfill_claim_source_metadata:
            result = runner.backfill_claim_source_metadata(
                dry_run=request.dry_run,
                batch_size=request.batch_size,
            )
        elif request.command == MigrationCommand.repair_orphaned_claim_links:
            result = runner.repair_orphaned_claim_links(
                dry_run=request.dry_run,
            )
        elif request.command == MigrationCommand.repair_kg_svo_repr_leak:
            result = runner.repair_kg_svo_repr_leak(
                dry_run=request.dry_run,
            )
        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown command: {request.command}"
            )

        runner.save_run_result(result)
        return _migration_result_to_response(result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


@router.post("/validate", response_model=MigrationValidationResponse)
async def validate_migration(
    request: MigrationValidationRequest,
    db: Database = Depends(get_library_database_for_write),
) -> MigrationValidationResponse:
    """Validate if a migration can run safely on the current data.

    Performs pre-flight checks on a sample of data and returns
    any warnings or errors that would prevent safe execution.
    """
    runner = MigrationRunner(db)

    validation = runner.validate_migration_safety(
        request.command.value, sample_size=request.sample_size
    )

    return MigrationValidationResponse(
        migration_name=validation["migration_name"],
        sample_size=validation["sample_size"],
        warnings=validation["warnings"],
        errors=validation["errors"],
        can_run=validation["can_run"],
    )


@router.get("/status/{run_id}", response_model=MigrationStatusResponse)
async def get_migration_status(
    run_id: str,
    db: Database = Depends(get_library_database),
) -> MigrationStatusResponse:
    """Get the status of a migration run by its audit ID.

    Returns detailed information about the migration including
    counts, timing, and any errors.
    """
    runner = MigrationRunner(db)
    status = runner.get_migration_status(run_id)

    if status is None:
        raise HTTPException(status_code=404, detail=f"Migration run {run_id} not found")

    return MigrationStatusResponse(
        migration_name=status.get("migration_name", status.get("run_id", "unknown")),
        status=status.get("status", "unknown"),
        migrated=status.get("migrated", status.get("total_mutations", 0)),
        skipped=status.get("skipped", 0),
        failed=status.get("failed", 0),
        dry_run=status.get("dry_run", False),
        audit_id=status.get("audit_id"),
        error_message=status.get("error_message"),
        started_at=datetime.fromisoformat(status["started_at"])
        if isinstance(status.get("started_at"), str)
        else status["started_at"],
        completed_at=datetime.fromisoformat(status["completed_at"])
        if isinstance(status.get("completed_at"), str) and status.get("completed_at")
        else status.get("completed_at"),
        details=status.get("details", status),
    )


@router.post("/rollback", response_model=RollbackResponse)
async def rollback_migration(
    request: RollbackRequest,
    db: Database = Depends(get_library_database_for_write),
) -> RollbackResponse:
    """Rollback a migration using its audit ID.

    Restores all entities modified by the migration to their
    pre-migration state. This is only possible if the mutation
    logs are still present.
    """
    runner = MigrationRunner(db)

    try:
        result = runner.rollback(request.run_id)
        return _rollback_result_to_response(result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")


@router.get("/integrity-check", response_model=DataIntegrityCheckResponse)
async def data_integrity_check(
    db: Database = Depends(get_library_database),
) -> DataIntegrityCheckResponse:
    """Run data integrity checks on the knowledge graph.

    Returns counts and identifies orphaned links, unreferenced entities,
    and claims without valid sources.
    """
    from fichero.models.knowledge import (
        KnowledgeClaim,
        KnowledgeClaimLink,
        KnowledgeEntity,
    )

    # Get counts
    entities = db.all(KnowledgeEntity)
    claims = db.all(KnowledgeClaim)
    links = db.all(KnowledgeClaimLink)

    # Find orphaned links
    claim_ids = {c.id for c in claims}
    orphaned_links = [
        link
        for link in links
        if link.claim_id not in claim_ids or link.related_claim_id not in claim_ids
    ]

    # Find orphaned entities (not referenced by any claim)
    referenced_entity_ids = set()
    for claim in claims:
        referenced_entity_ids.update(claim.entity_ids)

    orphaned_entities = [e for e in entities if e.id not in referenced_entity_ids]

    # Find claims without sources
    claims_without_sources = [
        c for c in claims if not c.source_document_id and not c.source_ids
    ]

    return DataIntegrityCheckResponse(
        entity_count=len(entities),
        claim_count=len(claims),
        link_count=len(links),
        orphaned_links=len(orphaned_links),
        orphaned_entities=len(orphaned_entities),
        claims_without_sources=len(claims_without_sources),
        checks_passed=(len(orphaned_links) == 0 and len(claims_without_sources) == 0),
    )
