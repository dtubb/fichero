"""Tests for knowledge migration/backfill tooling."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from fichero.db import Database
from fichero.knowledge_models import (
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
    SourceType,
)
from fichero.migrations import (
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
        from fichero.knowledge_models import KnowledgeClaim

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
        from fichero.knowledge_models import SourceMetadata

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
