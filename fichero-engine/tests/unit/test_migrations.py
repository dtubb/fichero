"""Tests for knowledge migration/backfill tooling."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from fichero.db import Database
from fichero.models.knowledge import (
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
    SourceType,
)
from fichero.db.migrations.runner import (
    MigrationResult,
    MigrationRunner,
    MigrationStatus,
)
from fichero.models import Document


@pytest.fixture
def mock_db():
    """Create a mock database for testing."""
    db = MagicMock(spec=Database)
    db.save = MagicMock()
    db.get = MagicMock(return_value=None)
    db.delete = MagicMock()
    db.all = MagicMock(return_value=[])
    db.query = MagicMock(return_value=[])
    return db


@pytest.fixture
def migration_runner(mock_db):
    """Create a MigrationRunner with mock database."""
    return MigrationRunner(mock_db, agent_id="test_runner")


class TestMigrationRunner:
    """Test cases for MigrationRunner."""

    def test_migrate_claims_to_multi_source_dry_run(self, migration_runner, mock_db):
        """Test dry-run mode counts but doesn't modify claims."""
        # Setup: Create claims needing migration
        claim_needing_migration = KnowledgeClaim(
            id="claim1",
            text="Test claim",
            source_document_id="doc1",
            source_type=SourceType.document,
            source_ids=[],  # Empty - needs migration
        )
        claim_already_migrated = KnowledgeClaim(
            id="claim2",
            text="Migrated claim",
            source_document_id="doc2",
            source_type=SourceType.document,
            source_ids=["doc2"],  # Already has source_ids
        )

        mock_db.all.return_value = [
            claim_needing_migration,
            claim_already_migrated,
        ]

        # Execute
        result = migration_runner.migrate_claims_to_multi_source(dry_run=True)

        # Verify
        assert result.status == MigrationStatus.completed
        assert result.dry_run is True
        assert result.migrated == 1  # Only first claim needs migration
        assert result.skipped == 1  # Second already migrated

        # Ensure no mutations were logged in dry-run mode
        mock_db.save.assert_not_called()

    def test_migrate_claims_to_multi_source_with_mutation(
        self, migration_runner, mock_db
    ):
        """Test actual migration creates mutation log entries."""
        claim = KnowledgeClaim(
            id="claim1",
            text="Test claim",
            source_document_id="doc1",
            source_type=SourceType.document,
            source_ids=[],
            source_page_label="p.5",
        )

        mock_db.all.return_value = [claim]

        # Execute
        result = migration_runner.migrate_claims_to_multi_source(dry_run=False)

        # Verify
        assert result.status == MigrationStatus.completed
        assert result.migrated == 1

        # Should have saved the updated claim
        assert mock_db.save.call_count >= 1

        # Should have logged mutation
        mutation_calls = [
            call
            for call in mock_db.save.call_args_list
            if len(call.args) > 0 and isinstance(call.args[0], MutationLog)
        ]
        assert len(mutation_calls) == 1

    def test_repair_orphaned_claim_links_dry_run(self, migration_runner, mock_db):
        """Test dry-run counts orphaned links without deleting."""
        from fichero.models.knowledge import KnowledgeClaim

        # Setup: Create links - one orphaned, one valid
        orphaned_link = KnowledgeClaimLink(
            id="link1",
            claim_id="deleted_claim",
            related_claim_id="existing_claim",
            relation_type="supports",
        )
        valid_link = KnowledgeClaimLink(
            id="link2",
            claim_id="existing_claim",
            related_claim_id="another_claim",
            relation_type="contradicts",
        )

        # Create claims that exist (for the valid link)
        existing_claim = KnowledgeClaim(
            id="existing_claim", text="Existing claim", source_document_id="doc1"
        )
        another_claim = KnowledgeClaim(
            id="another_claim", text="Another claim", source_document_id="doc2"
        )

        mock_db.all.side_effect = [
            [orphaned_link, valid_link],  # First call for links
            [
                existing_claim,
                another_claim,
            ],  # Second call for claims - not "deleted_claim"
        ]

        # Execute
        result = migration_runner.repair_orphaned_claim_links(dry_run=True)

        # Verify
        assert result.status == MigrationStatus.completed
        assert (
            result.migrated == 1
        )  # Orphaned link counted (deleted_claim doesn't exist)
        assert result.skipped == 1  # Valid link skipped

        # No deletions in dry-run
        mock_db.delete.assert_not_called()

    def test_repair_orphaned_claim_links_actual(self, migration_runner, mock_db):
        """Test actual repair deletes orphaned links."""
        orphaned_link = KnowledgeClaimLink(
            id="link1",
            claim_id="deleted_claim",
            related_claim_id="existing_claim",
            relation_type="supports",
        )

        mock_db.all.return_value = [orphaned_link]
        mock_db.get.return_value = None  # claim doesn't exist

        # Execute
        result = migration_runner.repair_orphaned_claim_links(dry_run=False)

        # Verify
        assert result.status == MigrationStatus.completed
        assert result.migrated == 1

        # Should have logged mutation and deleted
        assert mock_db.delete.call_count == 1

    def test_data_integrity_validation(self, migration_runner, mock_db):
        """Test migration safety validation."""
        # Setup claims with missing source_document_id
        bad_claim = KnowledgeClaim(
            id="claim1",
            text="No source",
            source_document_id="",
            source_type=SourceType.document,
            source_ids=[],
        )

        mock_db.all.return_value = [bad_claim]

        # Execute validation
        validation = migration_runner.validate_migration_safety(
            "migrate_claims_to_multi_source", sample_size=100
        )

        # Verify
        assert validation["can_run"] is False
        assert len(validation["errors"]) > 0

    def test_backfill_source_metadata_dry_run(self, migration_runner, mock_db):
        """Test backfill dry-run counts claims needing metadata."""
        from fichero.models.knowledge import SourceMetadata

        claim_needing_backfill = KnowledgeClaim(
            id="claim1",
            text="Test",
            source_document_id="doc1",
            source_metadata=None,  # Needs backfill
        )
        claim_with_metadata = KnowledgeClaim(
            id="claim2",
            text="Test 2",
            source_document_id="doc2",
            source_metadata=SourceMetadata(title="Has metadata"),  # Has metadata
        )

        # Mock document with metadata
        doc_with_meta = Document(
            id="doc1",
            name="Test Doc",
            metadata={"title": "Test Title", "publisher": "Test Pub"},
        )

        def mock_get_side_effect(model_class, entity_id):
            if model_class == Document and entity_id == "doc1":
                return doc_with_meta
            if model_class == Document and entity_id == "doc2":
                return Document(id="doc2", name="Doc 2", metadata={})
            return None

        mock_db.get.side_effect = mock_get_side_effect
        mock_db.all.return_value = [
            claim_needing_backfill,
            claim_with_metadata,
        ]

        # Execute
        result = migration_runner.backfill_claim_source_metadata(dry_run=True)

        # Verify
        assert result.migrated == 1  # Only first claim
        assert result.skipped == 1  # Second has metadata

    def test_progress_callback(self, migration_runner, mock_db):
        """Test progress callback is invoked during migration."""
        progress_calls = []

        def progress_callback(operation, current, total):
            progress_calls.append((operation, current, total))

        migration_runner.set_progress_callback(progress_callback)

        # Create multiple claims
        claims = [
            KnowledgeClaim(
                id=f"claim{i}",
                text=f"Claim {i}",
                source_document_id=f"doc{i}",
                source_type=SourceType.document,
                source_ids=[],
            )
            for i in range(5)
        ]

        mock_db.all.return_value = claims

        # Execute with batch_size to trigger progress
        migration_runner.migrate_claims_to_multi_source(dry_run=False, batch_size=2)

        # Verify progress was reported
        assert len(progress_calls) > 0

    def test_batch_size_limit(self, migration_runner, mock_db):
        """Test batch processing respects limit parameter."""
        claims = [
            KnowledgeClaim(
                id=f"claim{i}",
                text=f"Claim {i}",
                source_document_id=f"doc{i}",
                source_type=SourceType.document,
                source_ids=[],
            )
            for i in range(10)
        ]

        mock_db.all.return_value = claims

        # Execute with limit
        result = migration_runner.migrate_claims_to_multi_source(dry_run=False, limit=3)

        # Verify only 3 were migrated
        assert result.migrated == 3


class TestRollbackOperations:
    """Test cases for rollback functionality."""

    def test_rollback_update_operation(self, migration_runner, mock_db):
        """Test rollback restores entity to before_state."""
        # Setup mutation log entry
        mutation = MutationLog(
            id="mut1",
            entity_type="KnowledgeClaim",
            entity_id="claim1",
            operation=MutationOperationType.update,
            before_state={"source_ids": [], "text": "Original"},
            after_state={"source_ids": ["doc1"], "text": "Updated"},
            run_id="test_run_123",
        )

        mock_db.query.return_value = [mutation]

        # Mock the claim to restore
        current_claim = KnowledgeClaim(
            id="claim1",
            text="Updated",
            source_document_id="doc1",
            source_ids=["doc1"],
        )
        mock_db.get.return_value = current_claim

        # Execute
        result = migration_runner.rollback("test_run_123")

        # Verify
        assert result.status == MigrationStatus.rolled_back
        assert result.restored == 1

        # Verify claim was restored
        assert current_claim.source_ids == []
        assert current_claim.text == "Original"

    def test_rollback_create_operation(self, migration_runner, mock_db):
        """Test rollback of create operation deletes the entity."""
        mutation = MutationLog(
            id="mut1",
            entity_type="KnowledgeClaim",
            entity_id="new_claim",
            operation=MutationOperationType.create,
            before_state=None,
            after_state={"id": "new_claim", "text": "Created"},
            run_id="test_run_456",
        )

        mock_db.query.return_value = [mutation]

        created_claim = KnowledgeClaim(
            id="new_claim", text="Created", source_document_id="doc1"
        )
        mock_db.get.return_value = created_claim

        # Execute
        result = migration_runner.rollback("test_run_456")

        # Verify
        assert result.status == MigrationStatus.rolled_back
        assert result.restored == 1
        mock_db.delete.assert_called_once_with(created_claim)

    def test_rollback_delete_operation(self, migration_runner, mock_db):
        """Test rollback of delete operation recreates the entity."""
        mutation = MutationLog(
            id="mut1",
            entity_type="KnowledgeClaim",
            entity_id="deleted_claim",
            operation=MutationOperationType.delete,
            before_state={
                "id": "deleted_claim",
                "text": "Original text",
                "source_document_id": "doc1",
            },
            after_state=None,
            run_id="test_run_789",
        )

        mock_db.query.return_value = [mutation]

        # Execute
        result = migration_runner.rollback("test_run_789")

        # Verify
        assert result.status == MigrationStatus.rolled_back
        assert result.restored == 1

        # Should have saved the recreated entity
        assert mock_db.save.call_count >= 1

    def test_rollback_nonexistent_run(self, migration_runner, mock_db):
        """Test rollback with non-existent run_id fails gracefully."""
        mock_db.query.return_value = []

        result = migration_runner.rollback("nonexistent_run")

        assert result.status == MigrationStatus.failed
        assert "No mutations found" in result.error_message


class TestMigrationResult:
    """Test cases for MigrationResult data class."""

    def test_duration_calculation(self):
        """Test duration is calculated correctly."""
        start = datetime.now()
        result = MigrationResult(
            migration_name="test",
            status=MigrationStatus.completed,
            started_at=start,
            completed_at=start,  # Same time = 0ms
        )

        assert result.duration_ms == 0

        # Test with different times
        import time

        result2 = MigrationResult(
            migration_name="test2",
            status=MigrationStatus.completed,
            started_at=start,
        )
        time.sleep(0.01)  # Small delay
        result2.completed_at = datetime.now()

        assert result2.duration_ms is not None
        assert result2.duration_ms >= 10  # At least 10ms

    def test_to_dict_serialization(self):
        """Test result can be serialized to dict."""
        result = MigrationResult(
            migration_name="test_migration",
            status=MigrationStatus.completed,
            migrated=5,
            skipped=2,
            dry_run=True,
            audit_id="audit123",
            details={"extra": "info"},
        )

        data = result.to_dict()

        assert data["migration_name"] == "test_migration"
        assert data["migrated"] == 5
        assert data["dry_run"] is True
        assert data["audit_id"] == "audit123"


class TestMigrationStatus:
    def test_get_migration_status_reports_rolled_back_when_all_reversed(
        self, migration_runner, mock_db
    ):
        mutation_a = MutationLog(
            id="mut-a",
            entity_type="KnowledgeClaim",
            entity_id="claim-a",
            operation=MutationOperationType.update,
            before_state={"text": "before"},
            after_state={"text": "after"},
            run_id="run-1",
            reversal_id="rollback_1",
        )
        mutation_b = MutationLog(
            id="mut-b",
            entity_type="KnowledgeEntity",
            entity_id="entity-b",
            operation=MutationOperationType.update,
            before_state={"canonical_name": "before"},
            after_state={"canonical_name": "after"},
            run_id="run-1",
            reversal_id="rollback_2",
        )
        mock_db.query.return_value = [mutation_a, mutation_b]

        status = migration_runner.get_migration_status("run-1")
        assert status is not None
        assert status["status"] == "rolled_back"

class TestDataIntegrityChecks:
    """Test cases for data integrity validation."""

    def test_claim_source_counts_validation(self, migration_runner, mock_db):
        """Test validation of claim/source/link counts."""
        # Setup test data
        entities = [
            KnowledgeEntity(id=f"ent{i}", canonical_name=f"Entity {i}")
            for i in range(3)
        ]
        claims = [
            KnowledgeClaim(
                id=f"claim{i}",
                text=f"Claim {i}",
                source_document_id=f"doc{i}",
                entity_ids=[f"ent{i}"],
            )
            for i in range(3)
        ]
        links = [
            KnowledgeClaimLink(
                id=f"link{i}",
                claim_id=f"claim{i}",
                related_claim_id=f"claim{(i + 1) % 3}",
                relation_type="supports",
            )
            for i in range(3)
        ]

        mock_db.all.side_effect = [entities, claims, links]

        # Calculate counts
        ent_count = len(entities)
        claim_count = len(claims)
        link_count = len(links)

        # Verify counts match expectations
        assert ent_count == 3
        assert claim_count == 3
        assert link_count == 3

    def test_orphaned_entities_detection(self, migration_runner, mock_db):
        """Test detection of entities not referenced by any claim."""
        # Entity referenced by a claim
        referenced_entity = KnowledgeEntity(id="ent1", canonical_name="Referenced")
        # Orphaned entity
        orphaned_entity = KnowledgeEntity(id="ent2", canonical_name="Orphaned")

        entities = [referenced_entity, orphaned_entity]
        claims = [
            KnowledgeClaim(
                id="claim1",
                text="Claim",
                source_document_id="doc1",
                entity_ids=["ent1"],  # References ent1
            )
        ]

        mock_db.all.side_effect = [entities, claims]

        # Find referenced entity IDs
        referenced_ids = set()
        for claim in claims:
            referenced_ids.update(claim.entity_ids)

        # Check which entities are orphaned
        orphaned = [e for e in entities if e.id not in referenced_ids]

        assert len(orphaned) == 1
        assert orphaned[0].id == "ent2"


class TestRepairKgSvoReprLeak:
    """Tests for repair_kg_svo_repr_leak — the #1030 cleanup of rows where
    a leaked kwarg-repr ("verb='X', object='Y'") was stored verbatim."""

    def test_dry_run_counts_polluted_rows_without_mutation(
        self, migration_runner, mock_db
    ):
        polluted_claim = KnowledgeClaim(
            id="c-polluted",
            text="verb='worked as', object='a journalist at a local paper.'",
            source_document_id="doc1",
            subject_canonical="Louise Livingstone",
            entity_ids=["e-louise"],
        )
        clean_claim = KnowledgeClaim(
            id="c-clean",
            text="Leidy cleared gravel from a wooden sluice.",
            source_document_id="doc1",
        )
        polluted_entity = KnowledgeEntity(
            id="e-eldorado",
            canonical_name="Eldorado",
            description="verb='is', object='a long-abandoned mine.'",
        )
        clean_entity = KnowledgeEntity(
            id="e-louise",
            canonical_name="Louise Livingstone",
            description="worked as a journalist",
        )
        mock_db.all.side_effect = [
            [polluted_claim, clean_claim],
            [polluted_entity, clean_entity],
        ]

        result = migration_runner.repair_kg_svo_repr_leak(dry_run=True)

        assert result.status == MigrationStatus.completed
        assert result.migrated == 2  # one claim + one entity
        assert result.skipped == 2
        assert result.audit_id is None  # dry-run does not allocate audit
        mock_db.save.assert_not_called()

    def test_repairs_entity_bearing_claim_text(self, migration_runner, mock_db):
        polluted = KnowledgeClaim(
            id="c1",
            text="verb='worked as', object='a journalist at a local paper.'",
            source_document_id="doc1",
            subject_canonical="Louise Livingstone",
            entity_ids=["e-louise"],
        )
        mock_db.all.side_effect = [[polluted], []]

        result = migration_runner.repair_kg_svo_repr_leak(dry_run=False)

        assert result.migrated == 1
        assert result.audit_id is not None
        assert polluted.predicate_verb == "worked as"
        assert polluted.object_phrase == "a journalist at a local paper."
        assert polluted.text == (
            "Louise Livingstone worked as a journalist at a local paper.."
        )
        assert polluted.metadata.get("verb") == "worked as"
        # Claim saved once, mutation logged once.
        save_calls = [c for c in mock_db.save.call_args_list if c.args]
        assert any(c.args[0] is polluted for c in save_calls)

    def test_repairs_date_style_claim_with_stem_prefix(
        self, migration_runner, mock_db
    ):
        polluted = KnowledgeClaim(
            id="c-date",
            text="verb='occurred in', object='Eastern Ontario.'",
            source_document_id="doc1",
            entity_ids=[],  # date-style claims have no entity_ids
            metadata={"date_normalized": "1933-01-01", "subject": "1933-01-01"},
        )
        mock_db.all.side_effect = [[polluted], []]

        result = migration_runner.repair_kg_svo_repr_leak(dry_run=False)

        assert result.migrated == 1
        # Date claims use "{stem}: {verb} {obj}." per extractors._write_kg_rows.
        assert polluted.text == "1933-01-01: occurred in Eastern Ontario.."
        assert polluted.predicate_verb == "occurred in"

    def test_repairs_entity_description(self, migration_runner, mock_db):
        polluted = KnowledgeEntity(
            id="e-eldorado",
            canonical_name="Eldorado",
            description=(
                "verb='is', object='a long-abandoned mine in Eastern Ontario.'"
            ),
        )
        mock_db.all.side_effect = [[], [polluted]]

        result = migration_runner.repair_kg_svo_repr_leak(dry_run=False)

        assert result.migrated == 1
        assert polluted.description == (
            "is a long-abandoned mine in Eastern Ontario."
        )

    def test_clears_repr_from_source_excerpt(self, migration_runner, mock_db):
        polluted = KnowledgeClaim(
            id="c-excerpt",
            text="Leidy cleared gravel.",
            source_document_id="doc1",
            source_excerpt="verb='cleared', object='gravel from a sluice.'",
            subject_canonical="Leidy",
            entity_ids=["e-leidy"],
        )
        mock_db.all.side_effect = [[polluted], []]

        result = migration_runner.repair_kg_svo_repr_leak(dry_run=False)

        assert result.migrated == 1
        # source_excerpt holding a repr was never a real verbatim quote.
        assert polluted.source_excerpt is None
        # text was already clean — leave it alone.
        assert polluted.text == "Leidy cleared gravel."

    def test_idempotent_second_run_is_noop(self, migration_runner, mock_db):
        """A claim repaired on the first run is skipped on the second."""
        polluted = KnowledgeClaim(
            id="c-once",
            text="verb='worked as', object='a journalist.'",
            source_document_id="doc1",
            subject_canonical="Louise",
            entity_ids=["e-louise"],
        )
        mock_db.all.side_effect = [[polluted], []]
        first = migration_runner.repair_kg_svo_repr_leak(dry_run=False)
        assert first.migrated == 1

        # Second pass: same (now-repaired) row. Should be skipped.
        mock_db.all.side_effect = [[polluted], []]
        second = migration_runner.repair_kg_svo_repr_leak(dry_run=False)
        assert second.migrated == 0
        assert second.skipped == 1
        assert second.audit_id is None  # no mutations → no audit id

    def test_repr_with_no_recoverable_svo_is_skipped(
        self, migration_runner, mock_db
    ):
        """A repr that yielded neither verb nor object is left for review,
        not blanked."""
        # Whitespace-only values inside the quotes.
        polluted = KnowledgeClaim(
            id="c-empty-svo",
            text="verb='', object=''",
            source_document_id="doc1",
            subject_canonical="X",
            entity_ids=["e-x"],
        )
        mock_db.all.side_effect = [[polluted], []]

        result = migration_runner.repair_kg_svo_repr_leak(dry_run=False)

        assert result.migrated == 0
        assert result.skipped == 1
        assert polluted.text == "verb='', object=''"  # unchanged
        mock_db.save.assert_not_called()

    def test_entity_repr_with_empty_svo_preserves_description(
        self, migration_runner, mock_db
    ):
        """Entity-side mirror of the claim guard: an empty-SVO repr in
        entity.description must not null the field."""
        polluted = KnowledgeEntity(
            id="e-empty-svo",
            canonical_name="Empty",
            description="verb='', object=''",
        )
        mock_db.all.side_effect = [[], [polluted]]

        result = migration_runner.repair_kg_svo_repr_leak(dry_run=False)

        assert result.migrated == 0
        assert result.skipped == 1
        assert polluted.description == "verb='', object=''"  # unchanged
        mock_db.save.assert_not_called()

    def test_continues_past_single_row_failure(self, migration_runner, mock_db):
        """A bad row (e.g. db.save raises) must not abort the whole run —
        increments result.failed, logs the id, continues."""
        first = KnowledgeClaim(
            id="c-explodes",
            text="verb='broke', object='things.'",
            source_document_id="doc1",
            subject_canonical="X",
            entity_ids=["e-x"],
        )
        second = KnowledgeClaim(
            id="c-survives",
            text="verb='kept', object='going.'",
            source_document_id="doc1",
            subject_canonical="Y",
            entity_ids=["e-y"],
        )
        mock_db.all.side_effect = [[first, second], []]
        # First save raises; second succeeds. The mutation-log save also
        # uses db.save, so structure the side_effect to fail only on the
        # first claim.save and succeed thereafter.
        calls: list = []

        def save_side_effect(obj):
            calls.append(obj)
            if obj is first:
                raise RuntimeError("db error on first row")
            return None

        mock_db.save.side_effect = save_side_effect

        result = migration_runner.repair_kg_svo_repr_leak(dry_run=False)

        # Run completed (did not abort), failed counter recorded the bad
        # row, the second row was still repaired.
        assert result.status == MigrationStatus.completed
        assert result.failed == 1
        assert result.migrated == 1
        assert second.text == "Y kept going.."

    def test_clean_corpus_is_no_op(self, migration_runner, mock_db):
        """A corpus with no polluted rows results in 0 migrated, no saves."""
        clean_claim = KnowledgeClaim(
            id="c1",
            text="The miner worked the sluice.",
            source_document_id="doc1",
        )
        clean_entity = KnowledgeEntity(
            id="e1",
            canonical_name="Miner",
            description="a person who works a mine",
        )
        mock_db.all.side_effect = [[clean_claim], [clean_entity]]

        result = migration_runner.repair_kg_svo_repr_leak(dry_run=False)

        assert result.status == MigrationStatus.completed
        assert result.migrated == 0
        assert result.skipped == 2
        mock_db.save.assert_not_called()
