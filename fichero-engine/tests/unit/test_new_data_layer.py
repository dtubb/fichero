"""Tests for new data layer (db.py + models.py).

Verifies:
- Pydantic models work correctly
- db.save/get/query/delete work
- Document hierarchy queries
"""
import pytest
from pathlib import Path
import tempfile

from fichero.models import (
    Document, Artifact, Workflow, Run, DocType, FileType, Status, RunStatus
)
from fichero.db import Database


@pytest.fixture
def test_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        db = Database(db_path)
        yield db
        db.close()


class TestModels:
    """Test Pydantic model creation and validation."""

    def test_document_creation(self):
        """Document should have sensible defaults."""
        doc = Document(name="test.jpg")
        assert doc.id  # Auto-generated
        assert doc.name == "test.jpg"
        assert doc.doc_type == DocType.file
        assert doc.status == Status.pending

    def test_document_with_metadata(self):
        """Document metadata dict should work."""
        doc = Document(
            name="letter.jpg",
            path="/path/to/letter.jpg",
            metadata={"source_type": "local", "width": 800, "height": 600}
        )
        assert doc.width == 800
        assert doc.height == 600
        assert doc.source_type == "local"

    def test_document_collection(self):
        """Collection-type documents."""
        collection = Document(
            name="Archive 2024",
            doc_type=DocType.folder,
        )
        assert collection.doc_type == DocType.folder

    def test_artifact_creation(self):
        """Artifact should link to document."""
        artifact = Artifact(
            document_id="doc123",
            artifact_type="transcription",
            content="Hello world",
            provider="openai",
            model="gpt-4o"
        )
        assert artifact.document_id == "doc123"
        assert artifact.artifact_type == "transcription"
        assert artifact.content == "Hello world"

    def test_workflow_creation(self):
        """Workflow should store steps."""
        workflow = Workflow(
            name="OCR Pipeline",
            steps=[
                {"name": "enhance", "tool": "enhance"},
                {"name": "transcribe", "tool": "transcribe", "provider": "qwen"}
            ]
        )
        assert workflow.name == "OCR Pipeline"
        assert len(workflow.steps) == 2

    def test_run_creation(self):
        """Run should track workflow execution."""
        run = Run(
            workflow_id="wf123",
            document_ids=["doc1", "doc2"],
        )
        assert run.workflow_id == "wf123"
        assert len(run.document_ids) == 2
        assert run.status == RunStatus.queued


class TestDatabase:
    """Test database operations."""

    def test_save_and_get(self, test_db):
        """Save and retrieve a document."""
        doc = Document(name="test.jpg", path="/path/test.jpg")
        doc_id = doc.id

        test_db.save(doc)
        retrieved = test_db.get(Document, doc_id)

        assert retrieved is not None
        assert retrieved.id == doc_id
        assert retrieved.name == "test.jpg"
        assert retrieved.path == "/path/test.jpg"

    def test_save_updates(self, test_db):
        """Save should update existing record."""
        doc = Document(name="original.jpg")
        doc_id = doc.id
        test_db.save(doc)

        # Update and save again
        doc.name = "renamed.jpg"
        test_db.save(doc)

        retrieved = test_db.get(Document, doc_id)
        assert retrieved.name == "renamed.jpg"

    def test_query_with_filters(self, test_db):
        """Query with equality filters."""
        # Create parent
        parent = Document(name="Archive", doc_type=DocType.folder)
        test_db.save(parent)

        # Create children
        child1 = Document(name="doc1.jpg", parent_id=parent.id)
        child2 = Document(name="doc2.jpg", parent_id=parent.id)
        child3 = Document(name="other.jpg", parent_id="different")
        test_db.save(child1)
        test_db.save(child2)
        test_db.save(child3)

        # Query children of parent
        children = test_db.query(Document, parent_id=parent.id)
        assert len(children) == 2
        names = {c.name for c in children}
        assert names == {"doc1.jpg", "doc2.jpg"}

    def test_query_by_doctype(self, test_db):
        """Query by enum value."""
        coll1 = Document(name="Collection 1", doc_type=DocType.folder)
        coll2 = Document(name="Collection 2", doc_type=DocType.folder)
        file1 = Document(name="file.jpg", doc_type=DocType.file)
        test_db.save(coll1)
        test_db.save(coll2)
        test_db.save(file1)

        collections = test_db.query(Document, doc_type=DocType.folder)
        assert len(collections) == 2

        files = test_db.query(Document, doc_type=DocType.file)
        assert len(files) == 1

    def test_delete(self, test_db):
        """Delete should remove record."""
        doc = Document(name="to_delete.jpg")
        test_db.save(doc)

        # Verify exists
        assert test_db.get(Document, doc.id) is not None

        # Delete
        test_db.delete(doc)
        assert test_db.get(Document, doc.id) is None

    def test_count(self, test_db):
        """Count should return correct number."""
        for i in range(5):
            test_db.save(Document(name=f"doc{i}.jpg"))

        assert test_db.count(Document) == 5

    def test_count_with_filter(self, test_db):
        """Count with filter."""
        parent_id = "parent123"
        for i in range(3):
            test_db.save(Document(name=f"child{i}.jpg", parent_id=parent_id))
        test_db.save(Document(name="other.jpg", parent_id="different"))

        assert test_db.count(Document, parent_id=parent_id) == 3

    def test_all(self, test_db):
        """Get all documents."""
        test_db.save(Document(name="doc1.jpg"))
        test_db.save(Document(name="doc2.jpg"))

        all_docs = test_db.all(Document)
        assert len(all_docs) == 2

    def test_metadata_json_roundtrip(self, test_db):
        """Metadata dict should survive save/load."""
        doc = Document(
            name="test.jpg",
            metadata={
                "source_type": "local",
                "dimensions": {"width": 800, "height": 600},
                "tags": ["archive", "letter", "1920s"]
            }
        )
        test_db.save(doc)

        retrieved = test_db.get(Document, doc.id)
        assert retrieved.metadata["source_type"] == "local"
        assert retrieved.metadata["dimensions"]["width"] == 800
        assert retrieved.metadata["tags"] == ["archive", "letter", "1920s"]

    def test_artifact_query(self, test_db):
        """Query artifacts by document_id."""
        doc = Document(name="test.jpg")
        test_db.save(doc)

        # Create multiple artifacts for same document
        a1 = Artifact(document_id=doc.id, artifact_type="transcription", content="Hello")
        a2 = Artifact(document_id=doc.id, artifact_type="entities", data={"people": ["John"]})
        a3 = Artifact(document_id="other", artifact_type="transcription", content="Other")
        test_db.save(a1)
        test_db.save(a2)
        test_db.save(a3)

        artifacts = test_db.query(Artifact, document_id=doc.id)
        assert len(artifacts) == 2
        types = {a.artifact_type for a in artifacts}
        assert types == {"transcription", "entities"}


class TestDocumentHierarchy:
    """Test document hierarchy patterns."""

    def test_collection_folder_file_hierarchy(self, test_db):
        """Build and query a typical hierarchy."""
        # Collection
        collection = Document(
            name="Historical Archive",
            doc_type=DocType.folder
        )
        test_db.save(collection)

        # Folder in collection
        folder = Document(
            name="1920s Letters",
            doc_type=DocType.folder,
            parent_id=collection.id
        )
        test_db.save(folder)

        # Files in folder
        file1 = Document(
            name="letter_001.jpg",
            doc_type=DocType.file,
            parent_id=folder.id,
            file_type=FileType.image
        )
        file2 = Document(
            name="letter_002.jpg",
            doc_type=DocType.file,
            parent_id=folder.id,
            file_type=FileType.image
        )
        test_db.save(file1)
        test_db.save(file2)

        # Query: get top-level collections
        collections = test_db.query(Document, doc_type=DocType.folder, parent_id=None)
        assert len(collections) == 1

        # Query: get folders in collection
        folders = test_db.query(Document, parent_id=collection.id, doc_type=DocType.folder)
        assert len(folders) == 1
        assert folders[0].name == "1920s Letters"

        # Query: get files in folder
        files = test_db.query(Document, parent_id=folder.id, doc_type=DocType.file)
        assert len(files) == 2


class TestIdentity:
    """Test that querying returns independent objects (no identity map)."""

    def test_query_returns_new_objects(self, test_db):
        """Each query should return fresh objects."""
        doc = Document(name="test.jpg")
        test_db.save(doc)

        doc1 = test_db.get(Document, doc.id)
        doc2 = test_db.get(Document, doc.id)

        # Same data
        assert doc1.id == doc2.id
        assert doc1.name == doc2.name

        # Different objects (no identity map)
        assert doc1 is not doc2

        # Modifying one doesn't affect the other
        doc1.name = "modified.jpg"
        assert doc2.name == "test.jpg"
