"""Database migrations for schema upgrades.

All migration functions are idempotent — safe to run multiple times.
Run via: PYTHONPATH=fichero-api/src python scripts/migrate_claims_to_multi_source.py
"""

from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim, SourceType


def migrate_claims_to_multi_source(db: Database, dry_run: bool = False) -> tuple[int, int]:
    """Migrate KnowledgeClaim records from single-source to multi-source schema.

    Idempotent: checks source_type to avoid double-migration.
    Only migrates claims where source_type is still the default (document) AND
    source_ids is empty.

    Returns (migrated_count, skipped_count).
    """
    all_claims = db.all(KnowledgeClaim)
    migrated = 0
    skipped = 0

    for claim in all_claims:
        # Already migrated — skip
        if claim.source_type != SourceType.document or claim.source_ids:
            skipped += 1
            continue

        # Apply migration
        if not dry_run:
            claim.source_ids = [claim.source_document_id]
            # Ensure source_page_labels has the original page label in the right position
            if not claim.source_page_labels and claim.source_page_label:
                claim.source_page_labels = [claim.source_page_label]
            db.save(claim)

        migrated += 1

    return migrated, skipped
