"""
Tests for the db.py data layer.

Tests the simple Pythonic interface for:
- DuckDB storage (documents, artifacts, workflows, runs, traces, notes, events)
- LanceDB vector storage
- Parquet export/import
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from fichero.models import (
    Document, Artifact, Workflow, Run, Trace, Note, Event,
    DocType, FileType, Status, RunStatus
)
from fichero.db import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test.duckdb"
    db = Database(db_path)
    yield db
    db.close()
    shutil.rmtree(tmpdir)


class TestDatabaseBasics:
    """Test basic database operations."""

    def test_create_database(self, temp_db):
        """Test database creation."""
        assert temp_db.conn is not None
        assert temp_db.path.exists()

    def test_default_path(self):
        """Test default database path."""
        db = Database()
        expected = Path.home() / "Library/Application Support/com.tubb.fichero/library.duckdb"
        assert db.path == expected
        db.close()


class TestDocumentCRUD:
    """Test Document CRUD operations."""

    def test_save_and_get(self, temp_db):
        """Test saving and retrieving a document."""
        doc = Document(name="Test Collection", path="/test/path", doc_type=DocType.folder)
        temp_db.save(doc)

        retrieved = temp_db.get(Document, doc.id)
        assert retrieved is not None
        assert retrieved.name == "Test Collection"
        assert retrieved.path == "/test/path"
        assert retrieved.doc_type == DocType.folder

    def test_get_nonexistent(self, temp_db):
        """Test getting a nonexistent document."""
        result = temp_db.get(Document, "nonexistent")
        assert result is None

    def test_update(self, temp_db):
        """Test updating a document."""
        doc = Document(name="Original", path="/path")
        temp_db.save(doc)

        doc.name = "Updated"
        temp_db.save(doc)

        retrieved = temp_db.get(Document, doc.id)
        assert retrieved.name == "Updated"

    def test_delete(self, temp_db):
        """Test deleting a document."""
        doc = Document(name="To Delete", path="/path")
        temp_db.save(doc)

        temp_db.delete(doc)

        result = temp_db.get(Document, doc.id)
        assert result is None

    def test_all(self, temp_db):
        """Test getting all documents."""
        d1 = Document(name="First", path="/first")
        d2 = Document(name="Second", path="/second")
        temp_db.save(d1)
        temp_db.save(d2)

        all_docs = temp_db.all(Document)
        assert len(all_docs) == 2
        names = {d.name for d in all_docs}
        assert names == {"First", "Second"}

    def test_count(self, temp_db):
        """Test counting documents."""
        assert temp_db.count(Document) == 0

        temp_db.save(Document(name="One", path="/one"))
        temp_db.save(Document(name="Two", path="/two"))

        assert temp_db.count(Document) == 2

    def test_document_with_status(self, temp_db):
        """Test saving document with enum status."""
        doc = Document(
            name="doc.pdf",
            path="/docs/doc.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            status=Status.processing
        )
        temp_db.save(doc)

        retrieved = temp_db.get(Document, doc.id)
        assert retrieved.status == Status.processing
        assert retrieved.file_type == FileType.pdf

    def test_document_hierarchy(self, temp_db):
        """Test document parent-child relationships."""
        # Create collection
        collection = Document(name="Archive", doc_type=DocType.folder)
        temp_db.save(collection)

        # Create folder in collection
        folder = Document(
            name="Box 1",
            parent_id=collection.id,
            doc_type=DocType.folder
        )
        temp_db.save(folder)

        # Create file in folder
        file = Document(
            name="document.pdf",
            path="/archive/box1/document.pdf",
            parent_id=folder.id,
            doc_type=DocType.file,
            file_type=FileType.pdf
        )
        temp_db.save(file)

        # Query children
        children = temp_db.query(Document, parent_id=folder.id)
        assert len(children) == 1
        assert children[0].name == "document.pdf"

    def test_document_with_metadata(self, temp_db):
        """Test document with metadata dict."""
        doc = Document(
            name="image.jpg",
            path="/images/image.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            metadata={"width": 1920, "height": 1080, "format": "JPEG"}
        )
        temp_db.save(doc)

        retrieved = temp_db.get(Document, doc.id)
        assert retrieved.metadata["width"] == 1920
        assert retrieved.metadata["format"] == "JPEG"
        # Test typed accessor
        assert retrieved.width == 1920
        assert retrieved.height == 1080

    def test_document_page(self, temp_db):
        """Test document page with sequence and content."""
        pdf = Document(
            name="report.pdf",
            path="/docs/report.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf
        )
        temp_db.save(pdf)

        page = Document(
            name="Page 1",
            parent_id=pdf.id,
            doc_type=DocType.page,
            sequence=1,
            page_content="This is the text content of page 1."
        )
        temp_db.save(page)

        retrieved = temp_db.get(Document, page.id)
        assert retrieved.sequence == 1
        assert retrieved.page_content == "This is the text content of page 1."

    def test_document_group(self, temp_db):
        """Test document group (logical document spanning multiple pages)."""
        folder = Document(name="Box 1", doc_type=DocType.folder)
        temp_db.save(folder)

        # Create a group (letter spanning 3 pages)
        group = Document(
            name="Letter from John",
            parent_id=folder.id,
            doc_type=DocType.group
        )
        temp_db.save(group)

        # Add pages to group
        for i in range(3):
            page = Document(
                name=f"page_{i+1}.jpg",
                parent_id=group.id,
                doc_type=DocType.file,
                file_type=FileType.image,
                sequence=i+1
            )
            temp_db.save(page)

        # Query pages in group
        pages = temp_db.query(Document, parent_id=group.id)
        assert len(pages) == 3

    def test_document_iiif_metadata(self, temp_db):
        """Test document with IIIF metadata."""
        doc = Document(
            name="Manuscript Page 42",
            doc_type=DocType.file,
            file_type=FileType.image,
            metadata={
                "source_type": "iiif",
                "source_url": "https://example.org/iiif/canvas/42",
                "iiif_manifest": "https://example.org/iiif/manifest.json",
                "iiif_canvas_id": "canvas_42",
                "width": 4000,
                "height": 6000
            }
        )
        temp_db.save(doc)

        retrieved = temp_db.get(Document, doc.id)
        assert retrieved.source_type == "iiif"
        assert retrieved.iiif_manifest == "https://example.org/iiif/manifest.json"


class TestArtifactCRUD:
    """Test Artifact CRUD operations."""

    def test_save_and_get_artifact(self, temp_db):
        """Test saving and retrieving an artifact."""
        doc = Document(name="test.jpg", path="/test.jpg")
        temp_db.save(doc)

        artifact = Artifact(
            document_id=doc.id,
            artifact_type="transcription",
            content="This is the transcribed text.",
            provider="qwen",
            model="qwen-vl-max"
        )
        temp_db.save(artifact)

        retrieved = temp_db.get(Artifact, artifact.id)
        assert retrieved is not None
        assert retrieved.artifact_type == "transcription"
        assert retrieved.content == "This is the transcribed text."
        assert retrieved.provider == "qwen"

    def test_artifact_chaining(self, temp_db):
        """Test artifact chaining (one artifact derived from another)."""
        doc = Document(name="test.jpg", path="/test.jpg")
        temp_db.save(doc)

        # First artifact: raw transcription
        raw = Artifact(
            document_id=doc.id,
            artifact_type="transcription",
            content="Raw OCR output with errors",
            provider="qwen"
        )
        temp_db.save(raw)

        # Second artifact: cleaned text derived from first
        cleaned = Artifact(
            document_id=doc.id,
            source_artifact_id=raw.id,
            artifact_type="transcription",
            content="Cleaned text without errors",
            provider="human",
            version=2
        )
        temp_db.save(cleaned)

        retrieved = temp_db.get(Artifact, cleaned.id)
        assert retrieved.source_artifact_id == raw.id
        assert retrieved.version == 2

    def test_artifact_with_structured_data(self, temp_db):
        """Test artifact with structured data dict."""
        doc = Document(name="test.jpg", path="/test.jpg")
        temp_db.save(doc)

        artifact = Artifact(
            document_id=doc.id,
            artifact_type="entities",
            data={
                "people": ["John Smith", "Jane Doe"],
                "places": ["London", "Paris"],
                "dates": ["1920-05-15", "1925-12-01"]
            }
        )
        temp_db.save(artifact)

        retrieved = temp_db.get(Artifact, artifact.id)
        assert retrieved.data["people"] == ["John Smith", "Jane Doe"]
        assert len(retrieved.data["places"]) == 2
        # Test typed accessor
        entities = retrieved.get_entities()
        assert entities["people"] == ["John Smith", "Jane Doe"]

    def test_artifact_segmentation(self, temp_db):
        """Test segmentation artifact."""
        doc = Document(name="page.jpg", path="/page.jpg")
        temp_db.save(doc)

        artifact = Artifact(
            document_id=doc.id,
            artifact_type="segmentation",
            provider="openai",
            data={
                "segments": [
                    {"name": "Header", "bbox": [0, 0, 1000, 150], "segment_type": "header"},
                    {"name": "Body", "bbox": [50, 200, 950, 800], "segment_type": "body"},
                    {"name": "Signature", "bbox": [600, 850, 900, 950], "segment_type": "signature"}
                ]
            }
        )
        temp_db.save(artifact)

        retrieved = temp_db.get(Artifact, artifact.id)
        segments = retrieved.get_segments()
        assert len(segments) == 3
        assert segments[0]["name"] == "Header"

    def test_artifact_grouping(self, temp_db):
        """Test grouping artifact."""
        folder = Document(name="Box 1", doc_type=DocType.folder)
        temp_db.save(folder)

        artifact = Artifact(
            document_id=folder.id,
            artifact_type="grouping",
            provider="openai",
            data={
                "groups": [
                    {"name": "Letter 1", "document_ids": ["p1", "p2", "p3"], "confidence": 0.92},
                    {"name": "Receipt", "document_ids": ["p4"], "confidence": 0.88}
                ]
            }
        )
        temp_db.save(artifact)

        retrieved = temp_db.get(Artifact, artifact.id)
        groups = retrieved.get_groups()
        assert len(groups) == 2
        assert groups[0]["name"] == "Letter 1"


class TestWorkflowCRUD:
    """Test Workflow CRUD operations."""

    def test_workflow_with_steps(self, temp_db):
        """Test workflow with steps list."""
        workflow = Workflow(
            name="Full Analysis",
            description="OCR then extract entities",
            steps=[
                {"name": "transcribe", "tool": "transcribe", "provider": "qwen"},
                {"name": "extract_entities", "tool": "extract_entities", "provider": "openai"}
            ],
            config={"batch_size": 10}
        )
        temp_db.save(workflow)

        retrieved = temp_db.get(Workflow, workflow.id)
        assert retrieved.name == "Full Analysis"
        assert len(retrieved.steps) == 2
        assert retrieved.steps[0]["provider"] == "qwen"
        assert retrieved.config["batch_size"] == 10


class TestRunCRUD:
    """Test Run CRUD operations."""

    def test_run_lifecycle(self, temp_db):
        """Test run status lifecycle."""
        workflow = Workflow(name="Test Workflow")
        temp_db.save(workflow)

        doc = Document(name="test.jpg", path="/test.jpg")
        temp_db.save(doc)

        run = Run(
            workflow_id=workflow.id,
            document_ids=[doc.id],
            status=RunStatus.queued
        )
        temp_db.save(run)

        # Update to running
        run.status = RunStatus.running
        run.current_step = "transcribe"
        run.progress = 0.5
        temp_db.save(run)

        retrieved = temp_db.get(Run, run.id)
        assert retrieved.status == RunStatus.running
        assert retrieved.progress == 0.5

    def test_run_with_cost_tracking(self, temp_db):
        """Test run with cost tracking."""
        workflow = Workflow(name="Test")
        temp_db.save(workflow)

        run = Run(
            workflow_id=workflow.id,
            tokens_used=5000,
            cost_usd=0.15
        )
        temp_db.save(run)

        retrieved = temp_db.get(Run, run.id)
        assert retrieved.tokens_used == 5000
        assert retrieved.cost_usd == 0.15


class TestTraceCRUD:
    """Test Trace CRUD operations."""

    def test_save_and_get_trace(self, temp_db):
        """Test saving and retrieving a trace."""
        run = Run(workflow_id="wf_123")
        temp_db.save(run)

        trace = Trace(
            run_id=run.id,
            name="transcribe",
            trace_type="llm",
            model="qwen-vl-max",
            status="completed",
            latency_ms=3200,
            tokens_in=150,
            tokens_out=800,
            cost_usd=0.003
        )
        temp_db.save(trace)

        retrieved = temp_db.get(Trace, trace.id)
        assert retrieved.name == "transcribe"
        assert retrieved.latency_ms == 3200
        assert retrieved.tokens_in == 150

    def test_trace_with_io(self, temp_db):
        """Test trace with inputs and outputs."""
        run = Run(workflow_id="wf_123")
        temp_db.save(run)

        trace = Trace(
            run_id=run.id,
            name="transcribe",
            trace_type="llm",
            inputs={"image": "/path/to/image.jpg", "prompt": "Transcribe this"},
            outputs={"text": "Dear Mary, I am writing..."}
        )
        temp_db.save(trace)

        retrieved = temp_db.get(Trace, trace.id)
        assert retrieved.inputs["image"] == "/path/to/image.jpg"
        assert retrieved.outputs["text"] == "Dear Mary, I am writing..."


class TestNoteCRUD:
    """Test Note CRUD operations."""

    def test_save_and_get_note(self, temp_db):
        """Test saving and retrieving a note."""
        doc = Document(name="test.jpg", path="/test.jpg")
        temp_db.save(doc)

        note = Note(
            target_type="Document",
            target_id=doc.id,
            content="This handwriting is hard to read",
            note_type="comment"
        )
        temp_db.save(note)

        retrieved = temp_db.get(Note, note.id)
        assert retrieved.content == "This handwriting is hard to read"
        assert retrieved.note_type == "comment"

    def test_note_with_position(self, temp_db):
        """Test note with bbox position."""
        doc = Document(name="test.jpg", path="/test.jpg")
        temp_db.save(doc)

        note = Note(
            target_type="Document",
            target_id=doc.id,
            content="Check this signature",
            note_type="flag",
            bbox=(600, 850, 300, 100)
        )
        temp_db.save(note)

        retrieved = temp_db.get(Note, note.id)
        assert retrieved.bbox == (600, 850, 300, 100)


class TestEventCRUD:
    """Test Event CRUD operations."""

    def test_save_and_get_event(self, temp_db):
        """Test saving and retrieving an event."""
        event = Event(
            event_type="document.update",
            target_type="Document",
            target_id="doc_123",
            before={"name": "old_name.jpg"},
            after={"name": "new_name.jpg"},
            source="user"
        )
        temp_db.save(event)

        retrieved = temp_db.get(Event, event.id)
        assert retrieved.event_type == "document.update"
        assert retrieved.before["name"] == "old_name.jpg"
        assert retrieved.after["name"] == "new_name.jpg"


class TestQuery:
    """Test query operations."""

    def test_query_by_single_field(self, temp_db):
        """Test querying by a single field."""
        parent_id = "test_parent"
        temp_db.save(Document(name="a.txt", path="/a.txt", parent_id=parent_id))
        temp_db.save(Document(name="b.txt", path="/b.txt", parent_id=parent_id))
        temp_db.save(Document(name="c.txt", path="/c.txt", parent_id="other"))

        docs = temp_db.query(Document, parent_id=parent_id)
        assert len(docs) == 2

    def test_query_by_multiple_fields(self, temp_db):
        """Test querying by multiple fields."""
        temp_db.save(Document(
            name="done.txt",
            path="/done.txt",
            doc_type=DocType.file,
            status=Status.completed
        ))
        temp_db.save(Document(
            name="pending.txt",
            path="/pending.txt",
            doc_type=DocType.file,
            status=Status.pending
        ))

        docs = temp_db.query(
            Document,
            doc_type=DocType.file,
            status=Status.completed
        )
        assert len(docs) == 1
        assert docs[0].name == "done.txt"

    def test_query_empty_result(self, temp_db):
        """Test query with no results."""
        docs = temp_db.query(Document, parent_id="nonexistent")
        assert docs == []

    def test_count_with_filter(self, temp_db):
        """Test count with filter."""
        temp_db.save(Document(name="a.txt", path="/a.txt", status=Status.completed))
        temp_db.save(Document(name="b.txt", path="/b.txt", status=Status.pending))

        assert temp_db.count(Document, status=Status.completed) == 1
        assert temp_db.count(Document, status=Status.pending) == 1


class TestLanceDB:
    """Test LanceDB vector operations."""

    def test_lance_lazy_init(self, temp_db):
        """Test that LanceDB is lazily initialized."""
        assert temp_db._lance_db is None
        _ = temp_db.lance
        assert temp_db._lance_db is not None

    def test_save_and_search_vectors(self, temp_db):
        """Test saving and searching vectors."""
        data = [
            {"id": "1", "text": "hello world", "vector": [0.1, 0.2, 0.3]},
            {"id": "2", "text": "goodbye world", "vector": [0.4, 0.5, 0.6]},
        ]
        temp_db.save_vectors("embeddings", data)

        results = temp_db.search_vectors("embeddings", [0.1, 0.2, 0.3], limit=1)
        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_search_nonexistent_table(self, temp_db):
        """Test searching nonexistent table."""
        results = temp_db.search_vectors("nonexistent", [0.1, 0.2])
        assert results == []


class TestProviderCRUD:
    """Test Provider CRUD operations."""

    def test_save_and_get_provider(self, temp_db):
        """Test saving and retrieving a provider."""
        from fichero.models import Provider, ProviderType

        provider = Provider(
            name="OpenAI",
            provider_type=ProviderType.openai,
            api_base="https://api.openai.com/v1",
            enabled=True,
        )
        temp_db.save(provider)

        retrieved = temp_db.get(Provider, provider.id)
        assert retrieved.name == "OpenAI"
        assert retrieved.provider_type == ProviderType.openai
        assert retrieved.enabled is True

    def test_query_providers_by_type(self, temp_db):
        """Test querying providers by type."""
        from fichero.models import Provider, ProviderType

        temp_db.save(Provider(name="OpenAI", provider_type=ProviderType.openai))
        temp_db.save(Provider(name="Qwen", provider_type=ProviderType.dashscope))
        temp_db.save(Provider(name="Ollama", provider_type=ProviderType.ollama))

        providers = temp_db.query(Provider, provider_type=ProviderType.openai)
        assert len(providers) == 1
        assert providers[0].name == "OpenAI"


class TestModelCRUD:
    """Test Model CRUD operations."""

    def test_save_and_get_model(self, temp_db):
        """Test saving and retrieving a model."""
        from fichero.models import Provider, Model, ProviderType

        provider = Provider(name="OpenAI", provider_type=ProviderType.openai)
        temp_db.save(provider)

        model = Model(
            provider_id=provider.id,
            name="GPT-4o",
            model_id="gpt-4o",
            capabilities=["vision", "chat"],
            is_default=True,
            input_cost=5.0,
            output_cost=15.0,
        )
        temp_db.save(model)

        retrieved = temp_db.get(Model, model.id)
        assert retrieved.name == "GPT-4o"
        assert retrieved.capabilities == ["vision", "chat"]
        assert retrieved.is_default is True
        assert retrieved.input_cost == 5.0


class TestToolCRUD:
    """Test Tool CRUD operations."""

    def test_save_and_get_tool(self, temp_db):
        """Test saving and retrieving a tool."""
        from fichero.models import Tool

        tool = Tool(
            name="Transcribe",
            description="Extract text from images using OCR",
            icon="doc.text.viewfinder",
            module_path="fichero.tools.transcribe",
            config={"provider": "dashscope", "model": "qwen-vl-max"},
        )
        temp_db.save(tool)

        retrieved = temp_db.get(Tool, tool.id)
        assert retrieved.name == "Transcribe"
        assert retrieved.module_path == "fichero.tools.transcribe"
        assert retrieved.config["provider"] == "dashscope"


class TestSavedSearchCRUD:
    """Test SavedSearch CRUD operations."""

    def test_save_and_get_saved_search(self, temp_db):
        """Test saving and retrieving a saved search."""
        from fichero.models import SavedSearch

        search = SavedSearch(
            query="unprocessed images",
            is_smart_search=True,
            filters={
                "file_type": "image",
                "status": "pending",
            },
        )
        temp_db.save(search)

        retrieved = temp_db.get(SavedSearch, search.id)
        assert retrieved.query == "unprocessed images"
        assert retrieved.filters["status"] == "pending"

    def test_query_saved_searches(self, temp_db):
        """Test getting all saved searches."""
        from fichero.models import SavedSearch

        temp_db.save(SavedSearch(query="recent documents"))
        temp_db.save(SavedSearch(query="flagged items"))

        all_searches = temp_db.all(SavedSearch)
        assert len(all_searches) == 2


class TestTraceJSONL:
    """Test Trace JSONL export/import."""

    def test_export_traces_jsonl(self, temp_db):
        """Test exporting traces to JSONL."""
        run = Run(workflow_id="wf_123")
        temp_db.save(run)

        # Create some traces
        for i in range(3):
            trace = Trace(
                run_id=run.id,
                name=f"step_{i}",
                trace_type="llm",
                status="completed",
                latency_ms=100 * i,
            )
            temp_db.save(trace)

        # Export
        path = temp_db.export_traces_jsonl(run.id)

        assert path.exists()
        lines = path.read_text().strip().split('\n')
        assert len(lines) == 3

    def test_export_traces_custom_path(self, temp_db):
        """Test exporting to custom path."""
        run = Run(workflow_id="wf_123")
        temp_db.save(run)

        trace = Trace(run_id=run.id, name="test", trace_type="llm")
        temp_db.save(trace)

        custom_path = temp_db.path.parent / "custom" / "traces.jsonl"
        result = temp_db.export_traces_jsonl(run.id, custom_path)

        assert result == custom_path
        assert custom_path.exists()

    def test_import_traces_jsonl(self, temp_db):
        """Test importing traces from JSONL."""
        # Create JSONL file manually
        run_id = "run_for_import"
        jsonl_path = temp_db.path.parent / "import_traces.jsonl"

        traces_data = [
            {"id": "t1", "run_id": run_id, "name": "step1", "trace_type": "llm"},
            {"id": "t2", "run_id": run_id, "name": "step2", "trace_type": "tool"},
        ]

        with open(jsonl_path, 'w') as f:
            for t in traces_data:
                from fichero.models import Trace
                trace = Trace(**t)
                f.write(trace.model_dump_json() + '\n')

        # Import
        count = temp_db.import_traces_jsonl(jsonl_path)

        assert count == 2
        imported = temp_db.query(Trace, run_id=run_id)
        assert len(imported) == 2

    def test_import_traces_file_not_found(self, temp_db):
        """Test import raises for missing file."""
        with pytest.raises(FileNotFoundError):
            temp_db.import_traces_jsonl("/nonexistent/traces.jsonl")


class TestParquet:
    """Test Parquet export/import."""

    def test_export_import_roundtrip(self, temp_db):
        """Test exporting and importing via Parquet."""
        temp_db.save(Document(name="A", path="/a", doc_type=DocType.folder))
        temp_db.save(Document(name="B", path="/b", doc_type=DocType.folder))

        parquet_path = temp_db.path.parent / "documents.parquet"
        temp_db.export_parquet(Document, parquet_path)
        assert parquet_path.exists()

        db2_path = temp_db.path.parent / "test2.duckdb"
        db2 = Database(db2_path)

        imported = db2.import_parquet(Document, parquet_path)
        assert imported == 2

        all_docs = db2.all(Document)
        assert len(all_docs) == 2

        db2.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
