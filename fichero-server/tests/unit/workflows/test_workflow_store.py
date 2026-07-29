"""
Unit tests for WorkflowStore.

Tests workflow definition persistence, CRUD operations, and import/export.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from fichero_server.db import Database
from fichero_server.models import Workflow
from fichero_server.workflows.workflow_store import WorkflowStore


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / 'test.duckdb'
    yield db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def db(temp_db):
    """Create database instance."""
    return Database(temp_db)


@pytest.fixture
def store(db):
    """Create workflow store instance."""
    return WorkflowStore(db)


@pytest.fixture
def sample_workflow():
    """Create a sample workflow for testing."""
    return Workflow(
        name="Test Workflow",
        description="A test workflow",
        format="nodes",
        nodes=[
            {"id": "node1", "tool": "transcribe", "label": "Transcribe"},
            {"id": "node2", "tool": "summarize", "label": "Summarize"},
        ],
        edges=[
            {"source_node_id": "node1", "target_node_id": "node2"},
        ],
        folder_path="/test",
        tags=["test", "sample"],
        provider="openai",
        model="gpt-4",
    )


class TestCRUDOperations:
    """Test basic CRUD operations."""

    def test_save_workflow(self, store, sample_workflow):
        """Test saving a workflow."""
        store.save(sample_workflow)

        # Verify saved
        retrieved = store.get(sample_workflow.id)
        assert retrieved is not None
        assert retrieved.name == "Test Workflow"
        assert retrieved.description == "A test workflow"
        assert len(retrieved.nodes) == 2
        assert len(retrieved.edges) == 1

    def test_get_workflow(self, store, sample_workflow):
        """Test retrieving a workflow by ID."""
        store.save(sample_workflow)

        workflow = store.get(sample_workflow.id)
        assert workflow is not None
        assert workflow.id == sample_workflow.id
        assert workflow.name == sample_workflow.name

    def test_get_nonexistent_workflow(self, store):
        """Test retrieving non-existent workflow returns None."""
        workflow = store.get("nonexistent-id")
        assert workflow is None

    def test_delete_workflow(self, store, sample_workflow):
        """Test deleting a workflow."""
        store.save(sample_workflow)

        # Delete
        result = store.delete(sample_workflow.id)
        assert result is True

        # Verify deleted
        workflow = store.get(sample_workflow.id)
        assert workflow is None

    def test_delete_nonexistent_workflow(self, store):
        """Test deleting non-existent workflow returns False."""
        result = store.delete("nonexistent-id")
        assert result is False

    def test_update_workflow(self, store, sample_workflow):
        """Test updating a workflow."""
        store.save(sample_workflow)

        # Update
        sample_workflow.name = "Updated Name"
        sample_workflow.description = "Updated description"
        store.save(sample_workflow)

        # Verify updated
        workflow = store.get(sample_workflow.id)
        assert workflow.name == "Updated Name"
        assert workflow.description == "Updated description"

    def test_save_updates_timestamp(self, store, sample_workflow):
        """Test that save updates the updated_at timestamp."""
        store.save(sample_workflow)
        first_updated = sample_workflow.updated_at

        # Wait a tiny bit and save again
        import time
        time.sleep(0.01)

        sample_workflow.name = "Updated"
        store.save(sample_workflow)

        # Timestamp should be newer
        assert sample_workflow.updated_at > first_updated


class TestListOperations:
    """Test listing workflows."""

    def test_list_all_workflows(self, store):
        """Test listing all workflows."""
        # Create multiple workflows
        w1 = Workflow(name="Workflow 1", folder_path="/a")
        w2 = Workflow(name="Workflow 2", folder_path="/b")
        w3 = Workflow(name="Workflow 3", folder_path="/a")

        store.save(w1)
        store.save(w2)
        store.save(w3)

        # List all
        workflows = store.list_all()
        assert len(workflows) == 3

    def test_list_by_folder(self, store):
        """Test listing workflows filtered by folder."""
        w1 = Workflow(name="Workflow 1", folder_path="/archive")
        w2 = Workflow(name="Workflow 2", folder_path="/letters")
        w3 = Workflow(name="Workflow 3", folder_path="/archive")

        store.save(w1)
        store.save(w2)
        store.save(w3)

        # List by folder
        archive_workflows = store.list_all(folder_path="/archive")
        assert len(archive_workflows) == 2
        assert all(w.folder_path == "/archive" for w in archive_workflows)

    def test_list_sorted_by_folder_and_order(self, store):
        """Test that workflows are sorted by folder and sort_order."""
        w1 = Workflow(name="C", folder_path="/b", sort_order=2)
        w2 = Workflow(name="A", folder_path="/a", sort_order=1)
        w3 = Workflow(name="B", folder_path="/b", sort_order=1)

        store.save(w1)
        store.save(w2)
        store.save(w3)

        workflows = store.list_all()

        # Should be sorted by folder_path, then sort_order, then name
        assert workflows[0].name == "A"  # /a, order 1
        assert workflows[1].name == "B"  # /b, order 1
        assert workflows[2].name == "C"  # /b, order 2

    def test_list_templates(self, store):
        """Test listing workflow templates."""
        w1 = Workflow(name="Regular Workflow", is_template=False)
        w2 = Workflow(name="Template 1", is_template=True)
        w3 = Workflow(name="Template 2", is_template=True)

        store.save(w1)
        store.save(w2)
        store.save(w3)

        templates = store.list_templates()
        assert len(templates) == 2
        assert all(w.is_template for w in templates)

    def test_list_empty_database(self, store):
        """Test listing from empty database."""
        workflows = store.list_all()
        assert workflows == []


class TestSearchOperations:
    """Test workflow search functionality."""

    def test_search_by_name(self, store):
        """Test searching workflows by name."""
        w1 = Workflow(name="Transcribe Audio")
        w2 = Workflow(name="Summarize Text")
        w3 = Workflow(name="Transcribe Video")

        store.save(w1)
        store.save(w2)
        store.save(w3)

        # Search for "transcribe"
        results = store.search(name="transcribe")
        assert len(results) == 2
        assert all("transcribe" in w.name.lower() for w in results)

    def test_search_case_insensitive(self, store):
        """Test that name search is case-insensitive."""
        w1 = Workflow(name="UPPERCASE")
        w2 = Workflow(name="lowercase")
        w3 = Workflow(name="MixedCase")

        store.save(w1)
        store.save(w2)
        store.save(w3)

        results = store.search(name="case")
        assert len(results) == 3  # All three contain "case"

    def test_search_by_tags(self, store):
        """Test searching workflows by tags."""
        w1 = Workflow(name="W1", tags=["audio", "transcribe"])
        w2 = Workflow(name="W2", tags=["text", "summarize"])
        w3 = Workflow(name="W3", tags=["audio", "summarize"])

        store.save(w1)
        store.save(w2)
        store.save(w3)

        # Search for workflows with "audio" tag
        results = store.search(tags=["audio"])
        assert len(results) == 2

        # Search for workflows with both "audio" and "summarize" tags
        results = store.search(tags=["audio", "summarize"])
        assert len(results) == 1
        assert results[0].name == "W3"

    def test_search_by_provider(self, store):
        """Test searching workflows by provider."""
        w1 = Workflow(name="W1", provider="openai")
        w2 = Workflow(name="W2", provider="anthropic")
        w3 = Workflow(name="W3", provider="openai")

        store.save(w1)
        store.save(w2)
        store.save(w3)

        results = store.search(provider="openai")
        assert len(results) == 2
        assert all(w.provider == "openai" for w in results)

    def test_search_combined_criteria(self, store):
        """Test searching with multiple criteria."""
        w1 = Workflow(name="OpenAI Transcribe", provider="openai", tags=["audio"])
        w2 = Workflow(name="OpenAI Summarize", provider="openai", tags=["text"])
        w3 = Workflow(name="Anthropic Transcribe", provider="anthropic", tags=["audio"])

        store.save(w1)
        store.save(w2)
        store.save(w3)

        # Search for OpenAI workflows with "audio" tag
        results = store.search(provider="openai", tags=["audio"])
        assert len(results) == 1
        assert results[0].name == "OpenAI Transcribe"


class TestDuplicateOperation:
    """Test workflow duplication."""

    def test_duplicate_workflow(self, store, sample_workflow):
        """Test duplicating a workflow."""
        store.save(sample_workflow)

        # Duplicate
        duplicate = store.duplicate(sample_workflow.id)

        assert duplicate.id != sample_workflow.id
        assert duplicate.name == f"Copy of {sample_workflow.name}"
        assert duplicate.description == sample_workflow.description
        assert duplicate.nodes == sample_workflow.nodes
        assert duplicate.edges == sample_workflow.edges

    def test_duplicate_with_custom_name(self, store, sample_workflow):
        """Test duplicating with custom name."""
        store.save(sample_workflow)

        duplicate = store.duplicate(sample_workflow.id, new_name="Custom Name")

        assert duplicate.name == "Custom Name"

    def test_duplicate_nonexistent_workflow(self, store):
        """Test duplicating non-existent workflow raises error."""
        with pytest.raises(ValueError, match="Workflow not found"):
            store.duplicate("nonexistent-id")


class TestFolderOperations:
    """Test folder-related operations."""

    def test_update_folder(self, store, sample_workflow):
        """Test moving workflow to different folder."""
        sample_workflow.folder_path = "/old"
        store.save(sample_workflow)

        # Move to new folder
        result = store.update_folder(sample_workflow.id, "/new")
        assert result is True

        # Verify moved
        workflow = store.get(sample_workflow.id)
        assert workflow.folder_path == "/new"

    def test_update_folder_nonexistent(self, store):
        """Test updating folder for non-existent workflow."""
        result = store.update_folder("nonexistent-id", "/new")
        assert result is False

    def test_update_sort_order(self, store, sample_workflow):
        """Test updating workflow sort order."""
        sample_workflow.sort_order = 0
        store.save(sample_workflow)

        # Update sort order
        result = store.update_sort_order(sample_workflow.id, 5)
        assert result is True

        # Verify updated
        workflow = store.get(sample_workflow.id)
        assert workflow.sort_order == 5

    def test_update_sort_order_nonexistent(self, store):
        """Test updating sort order for non-existent workflow."""
        result = store.update_sort_order("nonexistent-id", 5)
        assert result is False


class TestExportImport:
    """Test export/import functionality."""

    def test_export_workflow(self, store, sample_workflow):
        """Test exporting workflow to JSON."""
        store.save(sample_workflow)

        json_str = store.export_workflow(sample_workflow.id)

        # Verify valid JSON
        data = json.loads(json_str)
        assert data["name"] == sample_workflow.name
        assert data["id"] == sample_workflow.id
        assert len(data["nodes"]) == 2

    def test_export_nonexistent_workflow(self, store):
        """Test exporting non-existent workflow raises error."""
        with pytest.raises(ValueError, match="Workflow not found"):
            store.export_workflow("nonexistent-id")

    def test_import_workflow(self, store, sample_workflow):
        """Test importing workflow from JSON."""
        store.save(sample_workflow)
        json_str = store.export_workflow(sample_workflow.id)

        # Import with new ID
        imported = store.import_workflow(json_str, new_id=True)

        assert imported.id != sample_workflow.id  # New ID assigned
        assert imported.name == sample_workflow.name
        assert imported.nodes == sample_workflow.nodes

    def test_import_with_original_id(self, store, sample_workflow):
        """Test importing workflow keeping original ID."""
        json_str = json.dumps(sample_workflow.model_dump(mode="json"))

        imported = store.import_workflow(json_str, new_id=False)

        assert imported.id == sample_workflow.id

    def test_import_with_folder_override(self, store, sample_workflow):
        """Test importing workflow with folder override."""
        json_str = json.dumps(sample_workflow.model_dump(mode="json"))

        imported = store.import_workflow(json_str, folder_path="/override")

        assert imported.folder_path == "/override"

    def test_import_invalid_json(self, store):
        """Test importing invalid JSON raises error."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            store.import_workflow("not valid json")

    def test_import_missing_required_fields(self, store):
        """Test importing workflow without required fields."""
        json_str = json.dumps({"description": "Missing name"})

        with pytest.raises(ValueError, match="Missing required field"):
            store.import_workflow(json_str)

    def test_export_to_file(self, store, sample_workflow, temp_db):
        """Test exporting workflow to file."""
        store.save(sample_workflow)

        file_path = temp_db.parent / "exported.json"
        store.export_to_file(sample_workflow.id, file_path)

        assert file_path.exists()
        data = json.loads(file_path.read_text())
        assert data["name"] == sample_workflow.name

    def test_import_from_file(self, store, sample_workflow, temp_db):
        """Test importing workflow from file."""
        store.save(sample_workflow)

        # Export to file
        file_path = temp_db.parent / "exported.json"
        store.export_to_file(sample_workflow.id, file_path)

        # Import from file
        imported = store.import_from_file(file_path, new_id=True)

        assert imported.id != sample_workflow.id
        assert imported.name == sample_workflow.name

    def test_import_from_nonexistent_file(self, store, temp_db):
        """Test importing from non-existent file raises error."""
        file_path = temp_db.parent / "nonexistent.json"

        with pytest.raises(ValueError, match="File not found"):
            store.import_from_file(file_path)


class TestBulkOperations:
    """Test bulk export/import operations."""

    def test_export_all(self, store):
        """Test exporting all workflows."""
        w1 = Workflow(name="W1", folder_path="/a")
        w2 = Workflow(name="W2", folder_path="/b")
        w3 = Workflow(name="W3", folder_path="/a")

        store.save(w1)
        store.save(w2)
        store.save(w3)

        json_str = store.export_all()

        # Verify valid JSON array
        data = json.loads(json_str)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_export_all_by_folder(self, store):
        """Test exporting workflows from specific folder."""
        w1 = Workflow(name="W1", folder_path="/archive")
        w2 = Workflow(name="W2", folder_path="/letters")
        w3 = Workflow(name="W3", folder_path="/archive")

        store.save(w1)
        store.save(w2)
        store.save(w3)

        json_str = store.export_all(folder_path="/archive")

        data = json.loads(json_str)
        assert len(data) == 2
        assert all(w["folder_path"] == "/archive" for w in data)

    def test_import_all(self, store):
        """Test importing multiple workflows."""
        workflows = [
            Workflow(name="W1"),
            Workflow(name="W2"),
            Workflow(name="W3"),
        ]

        # Export as JSON array
        data = [w.model_dump(mode="json") for w in workflows]
        json_str = json.dumps(data)

        # Import
        imported = store.import_all(json_str, new_ids=True)

        assert len(imported) == 3
        assert {w.name for w in imported} == {"W1", "W2", "W3"}

    def test_import_all_with_folder_override(self, store):
        """Test importing workflows with folder override."""
        data = [
            {"name": "W1", "folder_path": "/old"},
            {"name": "W2", "folder_path": "/old"},
        ]
        json_str = json.dumps(data)

        imported = store.import_all(json_str, folder_path="/new")

        assert all(w.folder_path == "/new" for w in imported)

    def test_import_all_invalid_json(self, store):
        """Test importing invalid JSON raises error."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            store.import_all("not valid json")

    def test_import_all_not_array(self, store):
        """Test importing non-array JSON raises error."""
        json_str = json.dumps({"name": "Not an array"})

        with pytest.raises(ValueError, match="must be an array"):
            store.import_all(json_str)

    def test_import_all_skips_invalid_workflows(self, store):
        """Test that import_all skips invalid workflows."""
        data = [
            {"name": "Valid1"},
            {"invalid": "no name field"},  # Invalid
            {"name": "Valid2"},
        ]
        json_str = json.dumps(data)

        imported = store.import_all(json_str)

        # Should import only the valid ones
        assert len(imported) == 2
        assert {w.name for w in imported} == {"Valid1", "Valid2"}
