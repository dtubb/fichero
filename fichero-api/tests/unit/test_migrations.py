"""Unit tests for migration framework with dry-run, rollback, and audit trail.

Tests cover:
- MigrationRunner functionality
- Dry-run mode validation
- Rollback operations
- Audit trail logging
- Batch processing
- Repair operations
"""

import pytest
from unittest.mock import Mock

from fichero.migrations import (
    MigrationRunner,
    MigrationStatus,
    migrate_claims_to_multi_source,
)
from fichero.knowledge_models import (
    KnowledgeClaim,
    KnowledgeClaimLink,
    SourceType,
    ClaimRelationType,
    MutationLog,
    MutationOperationType,
)
from fichero.models import Document


class TestMigrationRunner:
    """Test suite for MigrationRunner class."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock Database for testing."""
        db = Mock()
        db.save = Mock()
        db.get = Mock(return_value=None)
        db.all = Mock(return_value=[])
        db.delete = Mock()
        db.query = Mock(return_value=[])
        return db

    @pytest.fixture
    def runner(self, mock_db):
        """Create a MigrationRunner with mock database."""
        return MigrationRunner(mock_db, agent_id="test_agent")

    def test_migrate_claims_to_multi_source_dry_run(self, runner, mock_db):
        """Test dry-run mode for claims migration."""
        # Setup: claims that need migration
        claim1 = KnowledgeClaim(
            id="claim1",
            text="Test claim 1",
            source_document_id="doc1",
            source_type=SourceType.document,
            source_ids=[],  # Empty - needs migration
        )
        claim2 = KnowledgeClaim(
            id="claim2",
            text="Test claim 2",
            source_document_id="doc2",
            source_type=SourceType.document,
            source_ids=["doc2"],  # Already migrated
        )

        mock_db.all.return_value = [claim1, claim2]

        # Execute: dry run
        result = runner.migrate_claims_to_multi_source(dry_run=True)

        # Assert
        assert result.status == MigrationStatus.completed
        assert result.migrated == 1  # Only claim1 needs migration
        assert result.skipped == 1  # claim2 already migrated
        assert result.dry_run is True
        assert result.audit_id is None  # No mutations in dry-run

        # Verify no saves were made
        mock_db.save.assert_not_called()

    def test_migrate_claims_to_multi_source_live(self, runner, mock_db):
        """Test live execution of claims migration."""
        # Setup: claim needing migration
        claim1 = KnowledgeClaim(
            id="claim1",
            text="Test claim 1",
            source_document_id="doc1",
            source_page_label="p.5",
            source_type=SourceType.document,
            source_ids=[],
        )

        mock_db.all.return_value = [claim1]

        # Execute: live run
        result = runner.migrate_claims_to_multi_source(dry_run=False)

        # Assert
        assert result.status == MigrationStatus.completed
        assert result.migrated == 1
        assert result.skipped == 0

        # Verify claim was saved with migrated data
        mock_db.save.assert_any_call(claim1)

        # Verify claim has migrated data
        assert claim1.source_ids == ["doc1"]
        assert claim1.source_page_labels == ["p.5"]

    def test_migrate_claims_audit_trail(self, runner, mock_db):
        """Test that migrations create audit trail."""
        # Setup
        claim1 = KnowledgeClaim(
            id="claim1",
            text="Test claim 1",
            source_document_id="doc1",
            source_type=SourceType.document,
            source_ids=[],
        )
        mock_db.all.return_value = [claim1]

        # Execute
        result = runner.migrate_claims_to_multi_source(dry_run=False)

        # Assert: mutation was logged
        mutation_calls = [
            call for call in mock_db.save.call_args_list
            if len(call.args) == 1 and isinstance(call.args[0], MutationLog)
        ]
        assert len(mutation_calls) == 1

        mutation = mutation_calls[0].args[0]
        assert mutation.entity_type == "KnowledgeClaim"
        assert mutation.entity_id == "claim1"
        assert mutation.operation == MutationOperationType.update
        assert mutation.before_state == {"source_ids": [], "source_page_labels": []}
        assert "run_id" in result.details

    def test_rollback_update_operation(self, runner, mock_db):
        """Test rollback of an update operation."""
        # Setup: create a mutation log for an update
        run_id = "test_run_123"
        mutation = MutationLog(
            id="mut1",
            entity_type="KnowledgeClaim",
            entity_id="claim1",
            operation=MutationOperationType.update,
            before_state={"source_ids": [], "source_page_labels": []},
            after_state={"source_ids": ["doc1"], "source_page_labels": ["p.1"]},
            run_id=run_id,
        )

        # The entity as it currently exists
        current_claim = KnowledgeClaim(
            id="claim1",
            text="Test",
            source_document_id="doc1",
            source_ids=["doc1"],
            source_page_labels=["p.1"],
        )

        mock_db.query.return_value = [mutation]
        mock_db.get.return_value = current_claim

        # Execute rollback
        result = runner.rollback(run_id)

        # Assert
        assert result.status == MigrationStatus.rolled_back
        assert result.restored == 1
        assert result.failed == 0

        # Verify entity was restored
        mock_db.save.assert_called()
        saved_calls = [
            c for c in mock_db.save.call_args_list
            if isinstance(c.args[0], KnowledgeClaim)
        ]
        assert len(saved_calls) == 1
        restored_claim = saved_calls[0].args[0]
        assert restored_claim.source_ids == []
        assert restored_claim.source_page_labels == []

    def test_rollback_delete_operation(self, runner, mock_db):
        """Test rollback of a delete operation."""
        run_id = "test_run_456"
        mutation = MutationLog(
            id="mut2",
            entity_type="KnowledgeClaimLink",
            entity_id="link1",
            operation=MutationOperationType.delete,
            before_state={
                "id": "link1",
                "claim_id": "claim1",
                "related_claim_id": "claim2",
                "relation_type": "supports",
            },
            run_id=run_id,
        )

        mock_db.query.return_value = [mutation]
        mock_db.get.return_value = None  # Link was deleted

        # Execute rollback
        result = runner.rollback(run_id)

        # Assert
        assert result.status == MigrationStatus.rolled_back
        assert result.restored == 1

        # Verify entity was recreated
        mock_db.save.assert_called()
        saved_calls = [
            c for c in mock_db.save.call_args_list
            if isinstance(c.args[0], KnowledgeClaimLink)
        ]
        assert len(saved_calls) == 1
        restored_link = saved_calls[0].args[0]
        assert restored_link.id == "link1"
        assert restored_link.claim_id == "claim1"

    def test_repair_orphaned_claim_links(self, runner, mock_db):
        """Test repair of orphaned claim links."""
        # Setup: link pointing to deleted claim
        orphaned_link = KnowledgeClaimLink(
            id="orphan_link",
            claim_id="deleted_claim",
            related_claim_id="existing_claim",
            relation_type=ClaimRelationType.supports,
        )
        existing_link = KnowledgeClaimLink(
            id="valid_link",
            claim_id="existing_claim",
            related_claim_id="other_claim",
            relation_type=ClaimRelationType.supports,
        )

        runner._get_model_class = Mock(return_value=KnowledgeClaimLink)
        mock_db.all.side_effect = [
            [orphaned_link, existing_link],  # First call: all links
            [],  # Second call: no existing claims (both deleted)
        ]

        # Execute dry run
        result = runner.repair_orphaned_claim_links(dry_run=True)

        # Assert
        assert result.migrated == 2  # Both deleted because no claims exist
        assert result.skipped == 0
        assert mock_db.delete.call_count == 0  # Dry run doesn't delete

    def test_progress_callback(self, runner, mock_db):
        """Test progress callback is called during batch processing."""
        callback = Mock()
        runner.set_progress_callback(callback)

        # Setup: multiple claims
        claims = [
            KnowledgeClaim(
                id=f"claim{i}",
                text=f"Test {i}",
                source_document_id=f"doc{i}",
                source_type=SourceType.document,
                source_ids=[],
            )
            for i in range(10)
        ]
        mock_db.all.return_value = claims

        # Execute with batch size
        runner.migrate_claims_to_multi_source(  # result unused, testing callback
            dry_run=True, batch_size=5
        )

        # Assert callback was called
        assert callback.call_count > 0
        callback.assert_any_call("migrate_claims", 5, 10)

    def test_legacy_migration_function(self, mock_db):
        """Test backward-compatible legacy migration function."""
        claim1 = KnowledgeClaim(
            id="claim1",
            text="Test",
            source_document_id="doc1",
            source_type=SourceType.document,
            source_ids=[],
        )
        mock_db.all.return_value = [claim1]

        # Use legacy function
        migrated, skipped = migrate_claims_to_multi_source(mock_db, dry_run=False)

        assert migrated == 1
        assert skipped == 0

    def test_migrate_with_batch_size(self, runner, mock_db):
        """Test migration with batch processing."""
        # Setup: many claims
        claims = [
            KnowledgeClaim(
                id=f"claim{i}",
                text=f"Test {i}",
                source_document_id=f"doc{i}",
                source_type=SourceType.document,
                source_ids=[],
            )
            for i in range(25)
        ]
        mock_db.all.return_value = claims

        callback = Mock()
        runner.set_progress_callback(callback)

        # Execute: small batch size
        result = runner.migrate_claims_to_multi_source(
            dry_run=False, batch_size=10
        )

        # Assert
        assert result.migrated == 25
        assert result.status == MigrationStatus.completed

        # Progress should be reported at 10 and 20
        progress_calls = [
            c for c in callback.call_args_list
            if c.args[0] == "migrate_claims"
        ]
        assert len(progress_calls) >= 2

    def test_validation_safety_checks(self, runner, mock_db):
        """Test migration safety validation."""
        # Setup: claim missing source_document_id
        bad_claim = KnowledgeClaim(
            id="bad_claim",
            text="Bad claim",
            source_document_id="",  # Empty!
            source_type=SourceType.document,
            source_ids=[],
        )
        mock_db.all.return_value = [bad_claim]

        # Execute validation
        validation = runner.validate_migration_safety(
            "migrate_claims_to_multi_source", sample_size=10
        )

        # Assert: validation should flag the error
        assert validation["can_run"] is False
        assert len(validation["errors"]) > 0
        assert "bad_claim" in validation["errors"][0]


class TestBackfillOperations:
    """Test suite for backfill operations."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.save = Mock()
        db.get = Mock(return_value=None)
        db.all = Mock(return_value=[])
        return db

    @pytest.fixture
    def runner(self, mock_db):
        return MigrationRunner(mock_db)

    def test_backfill_source_metadata_dry_run(self, runner, mock_db):
        """Test dry-run of source metadata backfill."""
        # Setup: claim without source_metadata
        claim = KnowledgeClaim(
            id="claim1",
            text="Test claim",
            source_document_id="doc1",
            source_metadata=None,  # Needs backfill
        )
        mock_db.all.return_value = [claim]

        # Source document with metadata
        source_doc = Document(
            id="doc1",
            name="test.pdf",
            path="/test.pdf",
            metadata={
                "title": "Test Document",
                "date": "2024-01-01",
            },
        )
        mock_db.get.return_value = source_doc

        # Execute: dry run
        result = runner.backfill_claim_source_metadata(dry_run=True)

        # Assert
        assert result.migrated == 1
        assert result.skipped == 0
        assert result.dry_run is True

        # No saves in dry-run
        mutation_saves = [
            c for c in mock_db.save.call_args_list
            if len(c.args) == 1 and isinstance(c.args[0], MutationLog)
        ]
        assert len(mutation_saves) == 0

    def test_backfill_skips_already_filled(self, runner, mock_db):
        """Test backfill skips claims that already have source_metadata."""
        from fichero.knowledge_models import SourceMetadata

        # Setup: claim with existing source_metadata
        claim = KnowledgeClaim(
            id="claim1",
            text="Test claim",
            source_document_id="doc1",
            source_metadata=SourceMetadata(title="Already Filled"),
        )
        mock_db.all.return_value = [claim]

        # Execute
        result = runner.backfill_claim_source_metadata(dry_run=False)

        # Assert
        assert result.migrated == 0
        assert result.skipped == 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def runner(self):
        mock_db = Mock()
        mock_db.save = Mock()
        return MigrationRunner(mock_db)

    def test_rollback_no_mutations(self, runner):
        """Test rollback when no mutations exist."""
        runner.db.query.return_value = []

        result = runner.rollback("nonexistent_run")

        assert result.status == MigrationStatus.failed
        assert "No mutations found" in result.error_message

    def test_model_class_lookup(self, runner):
        """Test model class lookup from entity type names."""
        from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
        from fichero.models import Document

        assert runner._get_model_class("KnowledgeClaim") == KnowledgeClaim
        assert runner._get_model_class("KnowledgeEntity") == KnowledgeEntity
        assert runner._get_model_class("Document") == Document
        assert runner._get_model_class("UnknownType") is None

    def test_empty_database(self, runner):
        """Test migration with empty database."""
        runner.db.all.return_value = []

        result = runner.migrate_claims_to_multi_source(dry_run=False)

        assert result.migrated == 0
        assert result.skipped == 0
        assert result.status == MigrationStatus.completed
