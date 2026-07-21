"""
Tests for the db.py data layer.

Tests the simple Pythonic interface for:
- DuckDB storage (documents, artifacts, workflows, runs, traces, notes, events)
- LanceDB vector storage
- Parquet export/import
"""

import asyncio

import pytest
import tempfile
import shutil
import threading
import time
from pathlib import Path
from uuid import uuid4

import duckdb
from pydantic import BaseModel, Field

from fichero import db as db_module
from fichero.models import (
    Document, Artifact, Workflow, Run, Trace, Note as LegacyNote, Event,
    DocType, FileType, Status, RunStatus, SavedSearch
)
from fichero.db import Database
from fichero.research_models import (
    ResearchPlan,
    ResearchProject,
    ResearchStep,
    ResearchTask,
    StepTool,
)
from fichero.canvas_models import (
    CanvasItem,
    CanvasItemKind,
    CanvasLayout,
    ConnectionType,
    NodeType,
    RoomType,
    SpatialConnection,
    SpatialNode,
    SpatialRoom,
    SpatialViewport,
)
from fichero.knowledge_models import (
    ClaimRelationType,
    ClassificationDimension,
    ClassificationValue,
    EntityType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    LibraryItemLink,
    Milestone,
    Note,
    NoteKind,
)
from fichero.node_prototypes import (
    PrototypeResolutionError,
    resolve_prototype_attributes,
)


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

    def test_default_path(self, monkeypatch):
        """Default Database() path should be in Application Support — when
        FICHERO_BASE_PATH isn't set. Conftest sets it for test isolation,
        so clear it here and reload `fichero.db.storage` so its module-level
        `settings = StorageSettings()` re-reads the (now-empty) env.
        """
        class FakeConn:
            description = []

            def execute(self, _sql, _params=None):
                return self

            def fetchall(self):
                return []

            def fetchone(self):
                return None

            def close(self):
                return None

        monkeypatch.delenv("FICHERO_BASE_PATH", raising=False)
        monkeypatch.setattr(duckdb, "connect", lambda _path: FakeConn())
        import fichero.db_migrations as _db_migrations
        monkeypatch.setattr(_db_migrations, "migrate_document_table", lambda _conn: None)
        monkeypatch.setattr(_db_migrations, "migrate_workflow_table", lambda _conn: None)
        monkeypatch.setattr(_db_migrations, "migrate_saved_search_table", lambda _conn: None)
        monkeypatch.setattr(_db_migrations, "migrate_provider_refs_table", lambda _conn: None)
        monkeypatch.setattr(_db_migrations, "migrate_known_libraries_table", lambda _conn: None)
        monkeypatch.setattr(_db_migrations, "migrate_library_entity_types_table", lambda _conn: None)
        monkeypatch.setattr(_db_migrations, "migrate_canvas_layout_table", lambda _conn: None)
        monkeypatch.setattr(_db_migrations, "migrate_spatial_node_layout_fields", lambda _conn: None)
        monkeypatch.setattr(_db_migrations, "migrate_references_table", lambda _conn: None)
        monkeypatch.setattr(_db_migrations, "migrate_reference_provenance_table", lambda _conn: None)
        import fichero.db.storage as _storage_mod
        from importlib import reload as _reload
        _reload(_storage_mod)
        from fichero.db import Database as _Database
        db = _Database()
        expected = Path.home() / "Library/Application Support/Fichero/library.duckdb"
        assert db.path == expected
        db.close()


class TestDatabaseConcurrencySafety:
    """Regression coverage for two-writer data-layer hardening."""

    def test_execute_retries_duckdb_write_conflict(self, temp_db, monkeypatch):
        """DuckDB write conflicts are retried with bounded backoff."""

        class ConflictThenSuccess:
            def __init__(self):
                self.calls = 0

            def close(self):
                # temp_db fixture teardown calls db.close() -> self.conn.close();
                # this fake conn replaces temp_db.conn, so it needs close() too.
                pass

            def execute(self, sql, params=None):
                self.calls += 1
                if self.calls < 3:
                    raise duckdb.TransactionException(
                        "TransactionContext Error: Conflict on update!"
                    )
                return {"sql": sql, "params": params}

        fake_conn = ConflictThenSuccess()
        sleeps: list[float] = []
        monkeypatch.setattr(temp_db, "conn", fake_conn)
        monkeypatch.setattr(db_module.time, "sleep", sleeps.append)

        result = temp_db._execute("UPDATE documents SET name = ? WHERE id = ?", ["b", "a"])

        assert result == {
            "sql": "UPDATE documents SET name = ? WHERE id = ?",
            "params": ["b", "a"],
        }
        assert fake_conn.calls == 3
        assert sleeps == [0.01, 0.02]

    def test_async_route_offload_keeps_write_conflict_backoff_off_event_loop(
        self, temp_db, monkeypatch
    ):
        """Route-level to_thread offload keeps DuckDB retry sleeps off the loop."""

        class ConflictThenSuccess:
            def __init__(self):
                self.calls = 0

            def close(self):
                # temp_db fixture teardown calls db.close() -> self.conn.close();
                # this fake conn replaces temp_db.conn, so it needs close() too.
                pass

            def execute(self, sql, params=None):
                self.calls += 1
                if self.calls < 2:
                    raise duckdb.TransactionException(
                        "TransactionContext Error: Conflict on update!"
                    )
                return {"sql": sql, "params": params}

        fake_conn = ConflictThenSuccess()
        sleeps: list[tuple[float, int]] = []
        monkeypatch.setattr(temp_db, "conn", fake_conn)

        async def run_write():
            event_loop_thread_id = threading.get_ident()

            def fake_sleep(delay: float) -> None:
                sleeps.append((delay, threading.get_ident()))

            monkeypatch.setattr(db_module.time, "sleep", fake_sleep)
            result = await asyncio.to_thread(
                temp_db._execute,
                "UPDATE documents SET name = ? WHERE id = ?",
                ["b", "a"],
            )
            return event_loop_thread_id, result

        event_loop_thread_id, result = asyncio.run(run_write())

        assert result == {
            "sql": "UPDATE documents SET name = ? WHERE id = ?",
            "params": ["b", "a"],
        }
        assert fake_conn.calls == 2
        assert sleeps == [(0.01, sleeps[0][1])]
        assert sleeps[0][1] != event_loop_thread_id

    def test_execute_raises_clear_error_after_retry_bound(self, temp_db, monkeypatch):
        """Unresolved write conflicts fail with an actionable message."""

        class AlwaysConflict:
            def __init__(self):
                self.calls = 0

            def close(self):
                # temp_db fixture teardown calls db.close() -> self.conn.close();
                # this fake conn replaces temp_db.conn, so it needs close() too.
                pass

            def execute(self, sql, params=None):
                self.calls += 1
                raise duckdb.TransactionException(
                    "TransactionContext Error: Conflict on update!"
                )

        fake_conn = AlwaysConflict()
        monkeypatch.setattr(temp_db, "conn", fake_conn)
        monkeypatch.setattr(db_module.time, "sleep", lambda _delay: None)

        with pytest.raises(RuntimeError, match="write conflict did not resolve"):
            temp_db._execute("UPDATE documents SET name = 'blocked'")

        assert fake_conn.calls == 4

    def test_execute_does_not_swallow_non_conflict_duckdb_error(
        self, temp_db, monkeypatch
    ):
        """Non-transient DuckDB errors still surface unchanged."""

        class BrokenConn:
            def __init__(self):
                self.calls = 0

            def close(self):
                # temp_db fixture teardown calls db.close() -> self.conn.close();
                # this fake conn replaces temp_db.conn, so it needs close() too.
                pass

            def execute(self, sql, params=None):
                self.calls += 1
                raise duckdb.Error("Parser Error: syntax error at or near nope")

        fake_conn = BrokenConn()
        monkeypatch.setattr(temp_db, "conn", fake_conn)

        with pytest.raises(duckdb.Error, match="Parser Error"):
            temp_db._execute("nope")

        assert fake_conn.calls == 1

    def test_connect_reports_actionable_library_lock_error(self, monkeypatch, tmp_path):
        """Read-write lock failures should not leak a raw DuckDB stack."""

        def locked_connect(_path):
            raise duckdb.IOException(
                "IO Error: Could not set lock on file "
                f'"{tmp_path / "locked.duckdb"}": Conflicting lock is held'
            )

        db = object.__new__(Database)
        db.path = tmp_path / "locked.duckdb"
        monkeypatch.setattr(db_module.duckdb, "connect", locked_connect)

        with pytest.raises(RuntimeError) as exc_info:
            db._connect()

        message = str(exc_info.value)
        assert "Library already open by another Fichero engine process" in message
        assert "Only one engine may hold a library read-write" in message


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

    def test_query_skips_null_primary_key_ghost_rows(self, temp_db):
        """Malformed NULL-id rows must not poison typed table scans (#2012)."""
        doc = Document(name="Real", path="/real")
        entity = KnowledgeEntity(
            canonical_name="Ada Mock",
            entity_type=EntityType.person,
        )
        temp_db.save(doc)
        temp_db.save(entity)

        assert [d.id for d in temp_db.all(Document)] == [doc.id]
        assert [d.id for d in temp_db.query(Document)] == [doc.id]
        assert temp_db.query(Document, parent_id=None) == [doc]
        assert [e.id for e in temp_db.all(KnowledgeEntity)] == [entity.id]
        assert [e.id for e in temp_db.query(KnowledgeEntity)] == [entity.id]
        assert temp_db._hydrate_row(
            Document,
            ["id", "name", "created_at", "updated_at"],
            [None, None, None, None],
        ) is None
        assert temp_db._hydrate_row(
            KnowledgeEntity,
            ["id", "canonical_name", "created_at", "updated_at"],
            [None, None, None, None],
        ) is None

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

    def test_document_page_label_round_trips(self, temp_db):
        """Named PDF page labels must persist without a dedicated migration."""
        doc = Document(
            name="page-1",
            doc_type=DocType.page,
            sequence=1,
            page_label="i",
        )
        temp_db.save(doc)

        retrieved = temp_db.get(Document, doc.id)
        assert retrieved is not None
        assert retrieved.page_label == "i"

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

        note = LegacyNote(
            target_type="Document",
            target_id=doc.id,
            content="This handwriting is hard to read",
            note_type="comment"
        )
        temp_db.save(note)

        retrieved = temp_db.get(LegacyNote, note.id)
        assert retrieved.content == "This handwriting is hard to read"
        assert retrieved.note_type == "comment"

    def test_note_with_position(self, temp_db):
        """Test note with bbox position."""
        doc = Document(name="test.jpg", path="/test.jpg")
        temp_db.save(doc)

        note = LegacyNote(
            target_type="Document",
            target_id=doc.id,
            content="Check this signature",
            note_type="flag",
            bbox=(600, 850, 300, 100)
        )
        temp_db.save(note)

        retrieved = temp_db.get(LegacyNote, note.id)
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

    def test_query_none_filter_matches_root_documents(self, temp_db):
        """None filters must compile to IS NULL instead of = NULL."""
        root = Document(name="root.txt", path="/root.txt", parent_id=None)
        child = Document(name="child.txt", path="/child.txt", parent_id="parent-1")
        temp_db.save(root)
        temp_db.save(child)

        docs = temp_db.query(Document, parent_id=None)

        assert [doc.id for doc in docs] == [root.id]
        assert docs[0].parent_id is None

    def test_query_in_deduplicates_values_and_returns_each_match_once(self, temp_db):
        """query_in should tolerate duplicate ids without duplicating rows."""
        first = Document(name="first.txt", path="/first.txt")
        second = Document(name="second.txt", path="/second.txt")
        temp_db.save(first)
        temp_db.save(second)

        docs = temp_db.query_in(Document, "id", [first.id, second.id, first.id])

        assert {doc.id for doc in docs} == {first.id, second.id}
        assert len(docs) == 2

    def test_query_in_empty_values_returns_without_querying_rows(self, temp_db):
        temp_db.save(Document(name="first.txt", path="/first.txt"))

        assert temp_db.query_in(Document, "id", []) == []

    def test_query_in_rejects_untrusted_column_name(self, temp_db):
        with pytest.raises(ValueError, match="Invalid column name"):
            temp_db.query_in(Document, "id; DROP TABLE documents", ["doc-1"])


class TestJsonFieldParsing:
    """Test JSON/default coercion for DB rows loaded into Pydantic models."""

    def test_parse_json_fields_uses_defaults_for_null_new_columns(self, temp_db):
        class ExampleModel(BaseModel):
            id: str
            items: list[str] = Field(default_factory=list)
            flags: dict[str, bool] = Field(default_factory=dict)
            status: str = "pending"

        parsed = temp_db._parse_json_fields(
            ExampleModel,
            {"id": "row-1", "items": None, "flags": None, "status": None},
        )

        assert parsed["items"] == []
        assert parsed["flags"] == {}
        assert parsed["status"] == "pending"

    def test_parse_json_fields_decodes_json_strings(self, temp_db):
        class ExampleModel(BaseModel):
            id: str
            items: list[str] = Field(default_factory=list)
            metadata: dict[str, str] = Field(default_factory=dict)

        parsed = temp_db._parse_json_fields(
            ExampleModel,
            {
                "id": "row-1",
                "items": '["alpha", "beta"]',
                "metadata": '{"role": "source"}',
            },
        )

        assert parsed["items"] == ["alpha", "beta"]
        assert parsed["metadata"] == {"role": "source"}


class TestLanceDB:
    """Test LanceDB vector operations."""

    def test_lance_lazy_init(self, temp_db):
        """Test that LanceDB is lazily initialized."""
        assert temp_db._lance_db is None
        _ = temp_db.lance
        assert temp_db._lance_db is not None

    def test_close_releases_lance_handle(self, temp_db):
        _ = temp_db.lance
        temp_db.close()
        assert temp_db._lance_db is None

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

    def test_save_vectors_serializes_delete_add_mutations(self, temp_db):
        """Concurrent LanceDB replace writes must not interleave delete/add."""

        class FakeTable:
            def __init__(self):
                self.events: list[tuple[str, str]] = []

            def delete(self, predicate: str) -> None:
                key = predicate.split("'")[1]
                self.events.append(("delete", key))
                time.sleep(0.01)

            def add(self, data: list[dict]) -> None:
                key = data[0]["id"]
                self.events.append(("add", key))
                time.sleep(0.01)

        class FakeLance:
            def __init__(self, table: FakeTable):
                self.table = table

            def list_tables(self):
                return ["embeddings"]

            def open_table(self, _name: str):
                return self.table

        table = FakeTable()
        temp_db._lance_db = FakeLance(table)
        start = threading.Barrier(3)

        def worker(key: str) -> None:
            start.wait()
            temp_db.save_vectors(
                "embeddings",
                [{"id": key, "text": key, "vector": [0.1, 0.2, 0.3]}],
                replace=True,
            )

        threads = [
            threading.Thread(target=worker, args=("a",)),
            threading.Thread(target=worker, args=("b",)),
        ]
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join()

        assert table.events in (
            [("delete", "a"), ("add", "a"), ("delete", "b"), ("add", "b")],
            [("delete", "b"), ("add", "b"), ("delete", "a"), ("add", "a")],
        )

    def test_save_embedding_serializes_delete_add_sequence(self, temp_db, monkeypatch):
        """save_embedding keeps its delete+add pair in one lock scope."""

        events: list[tuple[str, str]] = []
        start = threading.Barrier(3)

        def fake_delete(_field: str, value: str) -> None:
            events.append(("delete", value))
            time.sleep(0.01)

        def fake_save_vectors(_table_name: str, data: list[dict], **_kwargs) -> None:
            events.append(("add", data[0]["document_id"]))
            time.sleep(0.01)

        monkeypatch.setattr(temp_db, "_delete_embedding_rows", fake_delete)
        monkeypatch.setattr(temp_db, "save_vectors", fake_save_vectors)

        def worker(doc_id: str) -> None:
            start.wait()
            doc = Document(id=doc_id, name=f"{doc_id}.txt", page_content="hello world")
            temp_db.save_embedding(doc, [0.1, 0.2, 0.3])

        threads = [
            threading.Thread(target=worker, args=("doc-a",)),
            threading.Thread(target=worker, args=("doc-b",)),
        ]
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join()

        assert events in (
            [("delete", "doc-a"), ("add", "doc-a"), ("delete", "doc-b"), ("add", "doc-b")],
            [("delete", "doc-b"), ("add", "doc-b"), ("delete", "doc-a"), ("add", "doc-a")],
        )

    def test_save_passage_embeddings_returns_zero_without_records(self, temp_db, monkeypatch):
        monkeypatch.setattr(temp_db, "passage_embedding_records", lambda *_args, **_kwargs: [])
        delete_calls: list[tuple[str, str]] = []
        save_calls: list[tuple[str, list[dict]]] = []
        monkeypatch.setattr(
            temp_db, "_delete_embedding_rows", lambda field, value: delete_calls.append((field, value))
        )
        monkeypatch.setattr(
            temp_db, "save_vectors", lambda table_name, data: save_calls.append((table_name, data))
        )

        count = temp_db.save_passage_embeddings(Document(id="doc-1", name="Doc 1"), text="body")

        assert count == 0
        assert delete_calls == []
        assert save_calls == []

    def test_save_passage_embeddings_replaces_rows_for_same_document(self, temp_db, monkeypatch):
        records = [
            {"id": "passage-1", "document_id": "doc-1", "text": "first", "vector": [0.1, 0.2, 0.3]},
            {"id": "passage-2", "document_id": "doc-1", "text": "second", "vector": [0.4, 0.5, 0.6]},
        ]
        monkeypatch.setattr(temp_db, "passage_embedding_records", lambda *_args, **_kwargs: records)
        delete_calls: list[tuple[str, str]] = []
        saved_payloads: list[tuple[str, list[dict]]] = []
        monkeypatch.setattr(
            temp_db, "_delete_embedding_rows", lambda field, value: delete_calls.append((field, value))
        )
        monkeypatch.setattr(
            temp_db, "save_vectors", lambda table_name, data: saved_payloads.append((table_name, data))
        )

        count = temp_db.save_passage_embeddings(Document(id="doc-1", name="Doc 1"), text="body")

        assert count == 2
        assert delete_calls == [("document_id", "doc-1")]
        assert saved_payloads == [("embeddings", records)]

    def test_embed_page_mode_uses_single_embedding_path(self, temp_db, monkeypatch):
        doc = Document(id="doc-page", name="Page Doc", page_content="embedded body")
        save_calls: list[tuple[str, list[float], str]] = []

        monkeypatch.setattr(temp_db, "_embedding_text_for_document", lambda _doc: "embedded body")
        monkeypatch.setattr(temp_db, "_embed_text", lambda text, role="passage": [0.1, 0.2, 0.3])
        monkeypatch.setattr(
            temp_db,
            "save_embedding",
            lambda saved_doc, vector, text=None: save_calls.append((saved_doc.id, vector, text or "")),
        )

        result = temp_db.embed(doc, mode="page")

        assert result is True
        assert save_calls == [("doc-page", [0.1, 0.2, 0.3], "embedded body")]

    def test_embed_passage_mode_returns_false_when_no_passages_saved(self, temp_db, monkeypatch):
        doc = Document(id="doc-passages", name="Passage Doc", page_content="embedded body")
        monkeypatch.setattr(temp_db, "_embedding_text_for_document", lambda _doc: "embedded body")
        monkeypatch.setattr(temp_db, "save_passage_embeddings", lambda *_args, **_kwargs: 0)

        result = temp_db.embed(doc)

        assert result is False


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

        mirrored = temp_db.get(Document, search.id)
        assert mirrored is not None
        assert mirrored.node_kind == "saved_search"
        assert mirrored.doc_type == DocType.folder
        assert mirrored.prototype_key == "saved_search"
        assert mirrored.attributes["query"] == "unprocessed images"
        assert mirrored.attributes["filters"]["status"] == "pending"
        assert mirrored.curated_items[0]["query"] == "unprocessed images"
        assert mirrored.metadata["node_class"] == "smart_folder"
        assert mirrored.metadata["saved_search_query"] == "unprocessed images"

    def test_query_saved_searches(self, temp_db):
        """Test getting all saved searches."""
        temp_db.save(SavedSearch(query="recent documents"))
        temp_db.save(SavedSearch(query="flagged items"))

        all_searches = temp_db.all(SavedSearch)
        assert len(all_searches) == 2

    def test_saved_search_reads_from_folded_document_node(self, temp_db):
        """SavedSearch reads hydrate from the folded document node, not the table row."""
        doc = Document(
            id="saved-doc-1",
            name="Saved Search Node",
            node_kind="saved_search",
            prototype_key="saved_search",
            doc_type=DocType.folder,
            sort_order=4,
            attributes={
                "query": "node-owned query",
                "folder_path": "/saved",
                "search_type": "fulltext",
                "sort_by": "name",
                "sort_direction": "asc",
                "is_smart_search": False,
                "filters": {"tag": "letters"},
            },
            curated_items=[
                {
                    "id": "saved-search-query",
                    "kind": "saved_search_query",
                    "query": "node-owned query",
                }
            ],
        )
        temp_db.save(doc)

        saved = temp_db.get(SavedSearch, doc.id)
        assert saved is not None
        assert saved.query == "node-owned query"
        assert saved.folder_path == "/saved"
        assert saved.sort_order == 4
        assert saved.filters == {"tag": "letters"}

    def test_saved_search_round_trips_odd_but_valid_payloads(self, temp_db):
        search = SavedSearch(
            query="name:odd payload",
            filters={},
            folder_path="",
            sort_order=9,
        )
        temp_db.save(search)

        mirrored = temp_db.get(Document, search.id)
        assert mirrored.attributes["folder_path"] == ""
        assert mirrored.attributes["filters"] == {}

        retrieved = temp_db.get(SavedSearch, search.id)
        assert retrieved.folder_path == ""
        assert retrieved.filters == {}
        assert retrieved.sort_order == 9

    def test_saved_search_missing_query_payload_raises(self, temp_db):
        doc = Document(
            id="saved-doc-bad",
            name="Bad Saved Search",
            node_kind="saved_search",
            prototype_key="saved_search",
            doc_type=DocType.folder,
            attributes={"filters": {"tag": "letters"}},
            curated_items=[],
        )
        temp_db.save(doc)

        with pytest.raises(ValueError, match="missing its query payload"):
            temp_db.get(SavedSearch, doc.id)


class TestNoteAndMilestoneFold:
    def test_note_round_trip_mirrors_to_document_node(self, temp_db):
        folder = Document(name="Notes", doc_type=DocType.folder)
        temp_db.save(folder)
        note = Note(
            title="Bridge note",
            body="Atomic thought",
            kind=NoteKind.hub,
            tags=["zettel"],
            folder_id=folder.id,
        )

        temp_db.save(note)

        retrieved = temp_db.get(Note, note.id)
        assert retrieved is not None
        assert retrieved.title == "Bridge note"
        assert retrieved.folder_id == folder.id

        mirrored = temp_db.get(Document, note.id)
        assert mirrored is not None
        assert mirrored.parent_id == folder.id
        assert mirrored.node_kind == "note"
        assert mirrored.prototype_key == "note"
        assert mirrored.attributes["body"] == "Atomic thought"
        assert mirrored.attributes["kind"] == "hub"
        assert mirrored.attributes["tags"] == ["zettel"]

    def test_page_scoped_note_is_contained_under_page_node(self, temp_db):
        page = Document(name="Page 1", doc_type=DocType.page)
        temp_db.save(page)
        note = Note(title="Margin note", body="Page scoped", page_id=page.id)

        temp_db.save(note)

        retrieved = temp_db.get(Note, note.id)
        assert retrieved is not None
        assert retrieved.page_id == page.id

        mirrored = temp_db.get(Document, note.id)
        assert mirrored is not None
        assert mirrored.parent_id == page.id
        children = temp_db.query(Document, parent_id=page.id)
        assert [child.id for child in children if child.id == note.id] == [note.id]

    def test_note_parent_validation_prefers_raise(self, temp_db):
        bad_parent = Document(name="Not a folder", doc_type=DocType.file)
        temp_db.save(bad_parent)

        with pytest.raises(ValueError, match="invalid doc_type"):
            temp_db.save(Note(title="Bad note", body="broken", folder_id=bad_parent.id))

        with pytest.raises(ValueError, match="cannot target both"):
            temp_db.save(
                Note(
                    title="Conflicted note",
                    body="broken",
                    folder_id="folder-a",
                    page_id="page-b",
                )
            )

    def test_milestone_round_trip_and_move_updates_containment(self, temp_db):
        backlog = Document(name="Backlog", doc_type=DocType.folder)
        archive = Document(name="Archive", doc_type=DocType.folder)
        temp_db.save(backlog)
        temp_db.save(archive)
        milestone = Milestone(
            title="Milestone A",
            description="Ship the bridge",
            parent_id=backlog.id,
            status="active",
            metadata={"lane": "engine"},
        )

        temp_db.save(milestone)
        milestone.parent_id = archive.id
        milestone.status = "done"
        temp_db.save(milestone)

        retrieved = temp_db.get(Milestone, milestone.id)
        assert retrieved is not None
        assert retrieved.parent_id == archive.id
        assert retrieved.status == "done"

        mirrored = temp_db.get(Document, milestone.id)
        assert mirrored is not None
        assert mirrored.parent_id == archive.id
        assert mirrored.node_kind == "milestone"
        assert mirrored.prototype_key == "milestone"
        assert mirrored.attributes["description"] == "Ship the bridge"
        assert mirrored.attributes["status"] == "done"

        effective = temp_db._effective_prototype_attributes(mirrored)
        assert effective["description"] == "Ship the bridge"

    def test_milestone_missing_or_non_folder_parent_raises(self, temp_db):
        with pytest.raises(ValueError, match="parent not found"):
            temp_db.save(Milestone(title="Broken", parent_id="missing-parent"))

        bad_parent = Document(name="Plain file", doc_type=DocType.file)
        temp_db.save(bad_parent)

        with pytest.raises(ValueError, match="invalid doc_type"):
            temp_db.save(Milestone(title="Broken Again", parent_id=bad_parent.id))


class TestWorkflowFold:
    """#11 Phase 1: workflows mirror into the document tree as folded nodes.

    This is a MIRROR, not a full fold like SavedSearch: the ``workflows``
    table stays authoritative and ``get``/``all``/``query`` for ``Workflow``
    still read the real table. Only a same-id ``Document`` shadow is kept in
    sync for sidebar tree placement (same pattern as Note/Milestone).
    """

    def test_no_default_workflows_container_when_no_system_workflows(self, temp_db):
        """A library that never seeds/saves an is_system workflow gets no
        container node — no permanent empty "Default Workflows" folder
        cluttering the tree, and raw Document counts stay predictable for
        libraries that never touch workflows."""
        from fichero import db as db_module

        assert temp_db.get(Document, db_module._DEFAULT_WORKFLOWS_CONTAINER_ID) is None

    def test_default_workflows_container_created_lazily_on_first_system_save(
        self, temp_db
    ):
        """The locked global container is created the first time an
        is_system=True workflow is saved — not eagerly on every db open."""
        from fichero import db as db_module

        assert temp_db.get(Document, db_module._DEFAULT_WORKFLOWS_CONTAINER_ID) is None

        temp_db.save(Workflow(name="First Preset", is_system=True))

        container = temp_db.get(Document, db_module._DEFAULT_WORKFLOWS_CONTAINER_ID)
        assert container is not None
        assert container.name == "Default Workflows"
        assert container.doc_type == DocType.folder
        assert container.attributes["scope"] == "global"
        assert container.attributes["read_only"] is True

    def test_save_workflow_mirrors_to_document_node(self, temp_db):
        workflow = Workflow(
            name="Transcribe Letters",
            provider="openai",
            tags=["ocr"],
            folder_path="/archive",
        )

        temp_db.save(workflow)

        # Real table stays authoritative — Workflow reads are not redirected.
        retrieved = temp_db.get(Workflow, workflow.id)
        assert retrieved is not None
        assert retrieved.name == "Transcribe Letters"
        assert retrieved.provider == "openai"

        mirrored = temp_db.get(Document, workflow.id)
        assert mirrored is not None
        assert mirrored.node_kind == "workflow"
        assert mirrored.prototype_key == "workflow"
        assert mirrored.name == "Transcribe Letters"
        assert mirrored.attributes["provider"] == "openai"
        assert mirrored.attributes["tags"] == ["ocr"]
        assert mirrored.attributes["scope"] == "library"
        assert mirrored.attributes["read_only"] is False
        # Regular (non-system) workflows sit at tree root, not nested
        # under the locked container.
        assert mirrored.parent_id is None

    def test_update_workflow_updates_mirror(self, temp_db):
        workflow = Workflow(name="Original Name")
        temp_db.save(workflow)

        workflow.name = "Renamed"
        workflow.provider = "anthropic"
        temp_db.save(workflow)

        mirrored = temp_db.get(Document, workflow.id)
        assert mirrored.name == "Renamed"
        assert mirrored.attributes["provider"] == "anthropic"

    def test_delete_workflow_removes_mirror_no_orphan(self, temp_db):
        workflow = Workflow(name="Ephemeral")
        temp_db.save(workflow)
        assert temp_db.get(Document, workflow.id) is not None

        temp_db.delete(workflow)

        assert temp_db.get(Workflow, workflow.id) is None
        assert temp_db.get(Document, workflow.id) is None

    def test_system_workflow_nests_under_locked_container(self, temp_db):
        from fichero import db as db_module

        preset = Workflow(name="Catalogue", is_system=True, is_template=True)
        temp_db.save(preset)

        mirrored = temp_db.get(Document, preset.id)
        assert mirrored is not None
        assert mirrored.parent_id == db_module._DEFAULT_WORKFLOWS_CONTAINER_ID
        assert mirrored.attributes["scope"] == "global"
        assert mirrored.attributes["read_only"] is True

        # Container itself is untouched/still singular.
        containers = temp_db.query(Document, id=db_module._DEFAULT_WORKFLOWS_CONTAINER_ID)
        assert len(containers) == 1

    def test_delete_system_workflow_does_not_delete_container(self, temp_db):
        from fichero import db as db_module

        preset = Workflow(name="Catalogue", is_system=True)
        temp_db.save(preset)
        temp_db.delete(preset)

        assert temp_db.get(Document, preset.id) is None
        container = temp_db.get(Document, db_module._DEFAULT_WORKFLOWS_CONTAINER_ID)
        assert container is not None, "deleting a system workflow must not remove the locked container"

    def test_all_folded_workflows_returns_mirror_nodes_not_duplicated(self, temp_db):
        w1 = Workflow(name="A")
        w2 = Workflow(name="B", is_system=True)
        temp_db.save(w1)
        temp_db.save(w2)

        folded = temp_db._all_folded_workflows()
        assert {d.id for d in folded} == {w1.id, w2.id}
        assert len(folded) == 2  # no double-mirroring on repeated save()

        temp_db.save(w1)  # re-save should upsert, not duplicate
        folded_again = temp_db._all_folded_workflows()
        assert len(folded_again) == 2

    def test_saved_search_and_workflow_mirrors_do_not_leak_across_kinds(self, temp_db):
        """No-leak test: saved-searches and workflows never double-appear
        or bleed into each other's node_kind bucket."""
        from fichero.models import SavedSearch

        temp_db.save(SavedSearch(query="unprocessed images"))
        temp_db.save(Workflow(name="Some Workflow"))

        workflow_docs = temp_db.query(Document, node_kind="workflow")
        saved_search_docs = temp_db.query(Document, node_kind="saved_search")

        assert len(workflow_docs) == 1
        assert len(saved_search_docs) == 1
        assert workflow_docs[0].id != saved_search_docs[0].id

        # SavedSearch.all() still only returns the one saved search — the
        # workflow mirror doesn't leak into the fully-folded SavedSearch read.
        assert len(temp_db.all(SavedSearch)) == 1
        # Workflow.all() still only returns the one real workflow row.
        assert len(temp_db.all(Workflow)) == 1

    def test_duplicate_global_workflow_drops_read_only(self, temp_db):
        """Duplicating a locked system preset must land as a normal,
        writable, library-scoped copy — never inherit is_system/read_only.
        """
        from fichero.api.routes.workflows import duplicate_workflow_impl

        preset = Workflow(name="Catalogue", is_system=True, is_template=True)
        temp_db.save(preset)

        duplicate = duplicate_workflow_impl(temp_db, preset.id)

        assert duplicate.id != preset.id
        assert duplicate.is_system is False

        mirrored = temp_db.get(Document, duplicate.id)
        assert mirrored is not None
        assert mirrored.attributes["scope"] == "library"
        assert mirrored.attributes["read_only"] is False
        assert mirrored.parent_id is None

        # The original preset is untouched — still locked under the container.
        original_mirror = temp_db.get(Document, preset.id)
        assert original_mirror.attributes["read_only"] is True

    # -- Read-only enforcement (Daniel: "yes, enforce") -----------------

    def test_update_is_system_workflow_rejected_403(self, temp_db):
        from fastapi import HTTPException

        from fichero.api.routes.workflows import update_workflow_impl
        from fichero.workflows.types import WorkflowDef

        preset = Workflow(name="Locked", is_system=True)
        temp_db.save(preset)

        with pytest.raises(HTTPException) as exc_info:
            update_workflow_impl(
                temp_db, preset.id, WorkflowDef(name="Hacked", nodes=[], edges=[])
            )
        assert exc_info.value.status_code == 403
        assert "read-only" in exc_info.value.detail

        # Untouched.
        assert temp_db.get(Workflow, preset.id).name == "Locked"

    def test_patch_is_system_workflow_rejected_403(self, temp_db):
        from fastapi import HTTPException

        from fichero.api.routes.workflows import (
            WorkflowPatchRequest,
            patch_workflow_impl,
        )

        preset = Workflow(name="Locked", is_system=True)
        temp_db.save(preset)

        with pytest.raises(HTTPException) as exc_info:
            patch_workflow_impl(temp_db, preset.id, WorkflowPatchRequest(name="Hacked"))
        assert exc_info.value.status_code == 403

    def test_delete_is_system_workflow_rejected_403(self, temp_db):
        from fastapi import HTTPException

        from fichero.api.routes.workflows import delete_workflow_impl

        preset = Workflow(name="Locked", is_system=True)
        temp_db.save(preset)

        with pytest.raises(HTTPException) as exc_info:
            delete_workflow_impl(temp_db, preset.id)
        assert exc_info.value.status_code == 403

        # Still there — the delete never happened.
        assert temp_db.get(Workflow, preset.id) is not None
        assert temp_db.get(Document, preset.id) is not None

    def test_reorder_is_system_workflow_rejected_403(self, temp_db):
        from fastapi import HTTPException

        from fichero.api.routes.workflows import reorder_workflows_impl

        preset = Workflow(name="Locked", is_system=True, sort_order=0)
        temp_db.save(preset)

        with pytest.raises(HTTPException) as exc_info:
            reorder_workflows_impl(temp_db, [preset.id])
        assert exc_info.value.status_code == 403

    def test_update_regular_workflow_still_allowed(self, temp_db):
        """The 403 guard is scoped to is_system=True only — ordinary
        library workflows (including user-editable is_template ones) are
        unaffected."""
        from fichero.api.routes.workflows import update_workflow_impl
        from fichero.workflows.types import WorkflowDef

        regular = Workflow(name="Mine", is_template=True, is_system=False)
        temp_db.save(regular)

        updated = update_workflow_impl(
            temp_db, regular.id, WorkflowDef(name="Renamed", nodes=[], edges=[])
        )
        assert updated.name == "Renamed"

    # -- Default-workflow subfolder seeding (38 presets, Daniel: "in sub
    # folders") -------------------------------------------------------

    def test_seed_default_workflows_creates_subfolders_under_container(self, temp_db):
        from fichero import db as db_module
        from fichero.workflows.default_workflows import seed_default_workflows

        seeded = seed_default_workflows(temp_db)
        assert seeded > 0

        container = temp_db.get(Document, db_module._DEFAULT_WORKFLOWS_CONTAINER_ID)
        assert container is not None

        subfolders = temp_db.query(Document, parent_id=container.id)
        assert len(subfolders) > 0
        names = {s.name for s in subfolders}
        # From the shipped preset folder_paths (resources/default_workflows/*.json).
        assert "Convert" in names
        assert "Transcribe" in names
        for subfolder in subfolders:
            assert subfolder.node_kind == db_module._WORKFLOW_CONTAINER_NODE_KIND
            assert subfolder.attributes["scope"] == "global"
            assert subfolder.attributes["read_only"] is True

    def test_seed_default_workflows_nests_presets_under_their_subfolder(self, temp_db):
        from fichero import db as db_module
        from fichero.workflows.default_workflows import seed_default_workflows

        seed_default_workflows(temp_db)

        container = temp_db.get(Document, db_module._DEFAULT_WORKFLOWS_CONTAINER_ID)
        subfolders = {s.name: s for s in temp_db.query(Document, parent_id=container.id)}
        assert "Convert" in subfolders

        convert_children = temp_db.query(Document, parent_id=subfolders["Convert"].id)
        assert len(convert_children) > 0
        for child in convert_children:
            assert child.node_kind == "workflow"
            assert child.attributes["scope"] == "global"
            assert child.attributes["read_only"] is True
            assert child.attributes["folder_path"] == "/Convert"

        # Folder-view path: the container's OWN direct children are only
        # subfolders (+ any root "/" presets) — Convert presets are not
        # flattened directly under the container.
        container_children = temp_db.query(Document, parent_id=container.id)
        assert subfolders["Convert"].id in {d.id for d in container_children}
        assert not any(
            d.node_kind == "workflow" and d.attributes.get("folder_path") == "/Convert"
            for d in container_children
        )

    def test_seed_default_workflows_idempotent_no_duplicate_subfolders(self, temp_db):
        from fichero import db as db_module
        from fichero.workflows.default_workflows import seed_default_workflows

        first = seed_default_workflows(temp_db)
        assert first > 0
        container = temp_db.get(Document, db_module._DEFAULT_WORKFLOWS_CONTAINER_ID)
        subfolder_count_1 = len(temp_db.query(Document, parent_id=container.id))
        preset_mirror_count_1 = len(temp_db._all_folded_workflows())

        second = seed_default_workflows(temp_db)
        assert second == 0  # names already exist — nothing new seeded

        subfolder_count_2 = len(temp_db.query(Document, parent_id=container.id))
        preset_mirror_count_2 = len(temp_db._all_folded_workflows())

        assert subfolder_count_2 == subfolder_count_1
        assert preset_mirror_count_2 == preset_mirror_count_1

    def test_workflow_store_duplicate_also_drops_is_system(self, temp_db):
        from fichero.workflows.workflow_store import WorkflowStore

        store = WorkflowStore(temp_db)
        preset = Workflow(name="Preset", is_system=True)
        # Seeding an is_system row goes through Database.save directly, same
        # as default_workflows.seed_default_workflows — WorkflowStore.save
        # itself now REJECTS is_system rows (read-only enforcement below).
        temp_db.save(preset)

        duplicate = store.duplicate(preset.id)

        assert duplicate.is_system is False
        mirrored = temp_db.get(Document, duplicate.id)
        assert mirrored.attributes["scope"] == "library"

    def test_workflow_store_save_rejects_is_system(self, temp_db):
        """WorkflowStore write path mirrors the route-level 403 (#11 Phase 1
        read-only enforcement) so nothing outside the routes can sneak past
        it either."""
        from fichero.workflows.workflow_store import WorkflowStore

        store = WorkflowStore(temp_db)
        preset = Workflow(name="Locked", is_system=True)

        with pytest.raises(PermissionError, match="read-only"):
            store.save(preset)

    def test_workflow_store_delete_rejects_is_system(self, temp_db):
        from fichero.workflows.workflow_store import WorkflowStore

        store = WorkflowStore(temp_db)
        preset = Workflow(name="Locked", is_system=True)
        temp_db.save(preset)  # seed directly, bypassing the store's guard

        with pytest.raises(PermissionError, match="read-only"):
            store.delete(preset.id)

        # Still there — the delete never happened.
        assert temp_db.get(Workflow, preset.id) is not None


class TestResearchWorkspaceFold:
    def test_workspace_prototype_inherits_folder_attributes(self, temp_db):
        folder_proto = next(
            value
            for value in temp_db.query(
                ClassificationValue,
                dimension=ClassificationDimension.document_prototype,
            )
            if value.key == "folder"
        )
        workspace_proto = next(
            value
            for value in temp_db.query(
                ClassificationValue,
                dimension=ClassificationDimension.document_prototype,
            )
            if value.key == "research_workspace"
        )
        room_proto = next(
            value
            for value in temp_db.query(
                ClassificationValue,
                dimension=ClassificationDimension.document_prototype,
            )
            if value.key == "room"
        )

        assert workspace_proto.parent_key == folder_proto.key
        assert room_proto.parent_key == folder_proto.key

        effective = resolve_prototype_attributes(temp_db, "research_workspace")
        assert effective["container_kind"] == "folder"
        assert effective["supports_children"] is True
        assert effective["workspace_kind"] == "research"
        assert effective["carries_tasks"] is True

    def test_save_and_get_research_project(self, temp_db):
        project = ResearchProject(
            name="Archive Hunt",
            description="Primary-source workspace",
            created_by="agent",
            library_destination_folder_id="folder-42",
            metadata={"topic": "mining"},
        )
        temp_db.save(project)

        retrieved = temp_db.get(ResearchProject, project.id)
        assert retrieved is not None
        assert retrieved.name == "Archive Hunt"
        assert retrieved.library_destination_folder_id == "folder-42"
        assert retrieved.metadata == {"topic": "mining"}

        mirrored = temp_db.get(Document, project.id)
        assert mirrored is not None
        assert mirrored.node_kind == "workspace"
        assert mirrored.prototype_key == "research_workspace"
        assert mirrored.is_workspace is True
        assert mirrored.attributes["description"] == "Primary-source workspace"
        assert mirrored.attributes["status"] == "active"
        assert mirrored.attributes["created_by"] == "agent"
        assert mirrored.attributes["library_destination_folder_id"] == "folder-42"
        assert mirrored.attributes["metadata"] == {"topic": "mining"}

    def test_research_project_reads_from_folded_document_node(self, temp_db):
        doc = Document(
            id="ws-doc-1",
            name="Workspace Node",
            node_kind="workspace",
            prototype_key="research_workspace",
            doc_type=DocType.folder,
            is_workspace=True,
            attributes={
                "description": "Node-owned workspace",
                "status": "paused",
                "created_by": "human",
                "library_destination_folder_id": "dest-1",
                "metadata": {"topic": "archives"},
            },
        )
        temp_db.save(doc)

        project = temp_db.get(ResearchProject, doc.id)
        assert project is not None
        assert project.description == "Node-owned workspace"
        assert project.status.value == "paused"
        assert project.library_destination_folder_id == "dest-1"
        assert project.metadata == {"topic": "archives"}

    def test_research_project_uses_prototype_defaults_when_node_omits_them(self, temp_db):
        doc = Document(
            id="ws-doc-defaults",
            name="Workspace Defaults",
            node_kind="workspace",
            prototype_key="research_workspace",
            doc_type=DocType.folder,
            is_workspace=True,
            attributes={
                "description": "Needs inherited defaults",
                "metadata": {"topic": "archives"},
            },
        )
        temp_db.save(doc)

        project = temp_db.get(ResearchProject, doc.id)
        assert project is not None
        assert project.description == "Needs inherited defaults"
        assert project.status.value == "active"
        assert project.created_by == "human"
        assert project.metadata == {"topic": "archives"}

    def test_research_project_invalid_created_by_payload_raises(self, temp_db):
        doc = Document(
            id="ws-doc-bad-created-by",
            name="Broken Workspace",
            node_kind="workspace",
            prototype_key="research_workspace",
            doc_type=DocType.folder,
            is_workspace=True,
            attributes={
                "description": "broken",
                "status": "active",
                "created_by": ["not", "a", "string"],
                "metadata": {},
            },
        )
        temp_db.save(doc)

        with pytest.raises(ValueError, match="invalid created_by payload"):
            temp_db.get(ResearchProject, doc.id)

    def test_research_project_raises_when_workspace_prototype_definition_missing(self, temp_db):
        doc = Document(
            id="ws-doc-missing-proto",
            name="Broken Workspace",
            node_kind="workspace",
            prototype_key="research_workspace",
            doc_type=DocType.folder,
            is_workspace=True,
            attributes={"description": "broken"},
        )
        temp_db.save(doc)

        workspace_proto = next(
            value
            for value in temp_db.query(
                ClassificationValue,
                dimension=ClassificationDimension.document_prototype,
            )
            if value.key == "research_workspace"
        )
        temp_db.delete(workspace_proto)

        with pytest.raises(PrototypeResolutionError):
            temp_db.get(ResearchProject, doc.id)


class TestSpatialRoomFold:
    def test_save_and_get_spatial_room(self, temp_db):
        room = SpatialRoom(
            name="Archive Room",
            description="A room for sources",
            room_type=RoomType.synthesis,
            owner_id="agent",
            metadata={"theme": "blue"},
        )
        temp_db.save(room)

        retrieved = temp_db.get(SpatialRoom, room.id)
        assert retrieved is not None
        assert retrieved.name == "Archive Room"
        assert retrieved.room_type == RoomType.synthesis
        assert retrieved.owner_id == "agent"
        assert retrieved.metadata == {"theme": "blue"}

        mirrored = temp_db.get(Document, room.id)
        assert mirrored is not None
        assert mirrored.node_kind == "room"
        assert mirrored.doc_type == DocType.folder
        assert mirrored.prototype_key == "room"
        assert mirrored.attributes["description"] == "A room for sources"
        assert mirrored.attributes["room_type"] == "synthesis"
        assert mirrored.attributes["owner_id"] == "agent"

    def test_spatial_room_reads_from_folded_document_node(self, temp_db):
        doc = Document(
            id="room-doc-1",
            name="Room Node",
            node_kind="room",
            prototype_key="room",
            doc_type=DocType.folder,
            attributes={
                "description": "Node-owned room",
                "room_type": "presentation",
                "owner_id": "human",
                "metadata": {"theme": "gold"},
            },
        )
        temp_db.save(doc)

        room = temp_db.get(SpatialRoom, doc.id)
        assert room is not None
        assert room.description == "Node-owned room"
        assert room.room_type == RoomType.presentation
        assert room.owner_id == "human"
        assert room.metadata == {"theme": "gold"}

    def test_spatial_room_inherits_folder_prototype_attributes(self, temp_db):
        room = SpatialRoom(name="Inherited Room")
        temp_db.save(room)

        effective = resolve_prototype_attributes(temp_db, "room")
        assert effective["container_kind"] == "folder"
        assert effective["supports_children"] is True
        assert effective["workspace_kind"] == "room"

        mirrored = temp_db.get(Document, room.id)
        assert mirrored is not None
        child = Document(
            id="room-child",
            name="Room Child",
            doc_type=DocType.file,
            parent_id=room.id,
        )
        temp_db.save(child)
        children = temp_db.query(Document, parent_id=mirrored.id)
        assert [item.id for item in children] == ["room-child"]

    def test_spatial_room_fold_preserves_parent_edge_across_round_trip(self, temp_db):
        room_doc = Document(
            id="room-parented",
            parent_id="workspace-root",
            name="Parented Room",
            node_kind="room",
            prototype_key="room",
            doc_type=DocType.folder,
            attributes={
                "description": "Nested room",
                "room_type": "research",
                "owner_id": "human",
                "metadata": {"theme": "amber"},
            },
        )
        temp_db.save(room_doc)

        room = temp_db.get(SpatialRoom, room_doc.id)
        assert room is not None
        assert room.name == "Parented Room"
        assert room.description == "Nested room"
        assert room.metadata == {"theme": "amber"}

        room.description = "Updated nested room"
        room.metadata = {"theme": "teal"}
        temp_db.save(room)

        mirrored = temp_db.get(Document, room.id)
        assert mirrored is not None
        assert mirrored.parent_id == "workspace-root"
        assert mirrored.prototype_key == "room"
        assert mirrored.attributes["description"] == "Updated nested room"
        assert mirrored.attributes["metadata"] == {"theme": "teal"}

    def test_spatial_room_raises_when_document_is_not_room_prototype(self, temp_db):
        doc = Document(
            id="bad-room",
            name="Bad Room",
            node_kind="room",
            prototype_key="letter",
            doc_type=DocType.folder,
        )
        temp_db.save(doc)

        with pytest.raises(ValueError, match="room node"):
            temp_db.get(SpatialRoom, doc.id)

    def test_spatial_room_invalid_room_type_payload_raises(self, temp_db):
        doc = Document(
            id="bad-room-type",
            name="Bad Room Type",
            node_kind="room",
            prototype_key="room",
            doc_type=DocType.folder,
            attributes={
                "description": "",
                "room_type": "war-room",
                "owner_id": "user",
                "metadata": {},
            },
        )
        temp_db.save(doc)

        with pytest.raises(ValueError, match="invalid room_type payload"):
            temp_db.get(SpatialRoom, doc.id)

    def test_spatial_room_invalid_metadata_payload_raises(self, temp_db):
        doc = Document(
            id="bad-room-metadata",
            name="Bad Room Metadata",
            node_kind="room",
            prototype_key="room",
            doc_type=DocType.folder,
            attributes={
                "description": "",
                "room_type": "research",
                "owner_id": "user",
                "metadata": "not-a-dict",
            },
        )
        temp_db.save(doc)

        with pytest.raises(ValueError, match="invalid metadata payload"):
            temp_db.get(SpatialRoom, doc.id)

    def test_spatial_room_raises_when_room_prototype_definition_missing(self, temp_db):
        doc = Document(
            id="missing-room-proto",
            name="Broken Room",
            node_kind="room",
            prototype_key="room",
            doc_type=DocType.folder,
            attributes={"description": "broken"},
        )
        temp_db.save(doc)

        room_proto = next(
            value
            for value in temp_db.query(
                ClassificationValue,
                dimension=ClassificationDimension.document_prototype,
            )
            if value.key == "room"
        )
        temp_db.delete(room_proto)

        with pytest.raises(PrototypeResolutionError):
            temp_db.get(SpatialRoom, doc.id)


class TestKeptCanvasModels:
    def test_kept_canvas_models_round_trip(self, temp_db):
        layout = CanvasLayout(folder_id="scope-1", item_id="item-1", x=12.0, y=34.0)
        item = CanvasItem(
            folder_id="scope-1",
            kind=CanvasItemKind.note,
            text="Canvas note",
        )
        node = SpatialNode(
            room_id="room-1",
            node_type=NodeType.note,
            label="Node",
        )
        connection = SpatialConnection(
            room_id="room-1",
            source_node_id="a",
            target_node_id="b",
            connection_type=ConnectionType.semantic,
        )
        viewport = SpatialViewport(room_id="room-1", user_id="user-1")

        for obj in (layout, item, node, connection, viewport):
            temp_db.save(obj)

        assert temp_db.get(CanvasLayout, layout.id) is not None
        assert temp_db.get(CanvasItem, item.id) is not None
        assert temp_db.get(SpatialNode, node.id) is not None
        assert temp_db.get(SpatialConnection, connection.id) is not None
        assert temp_db.get(SpatialViewport, viewport.id) is not None


class TestFiledEntityFold:
    def test_save_filed_entity_creates_document_node(self, temp_db):
        folder = Document(id="folder-a", name="Folder A", doc_type=DocType.folder)
        temp_db.save(folder)
        entity = KnowledgeEntity(
            canonical_name="Louise Livingstone",
            entity_type=EntityType.person,
            parent_id=folder.id,
            aliases=["L. Livingstone"],
            metadata={"topic": "archives"},
        )

        temp_db.save(entity)

        mirrored = temp_db.get(Document, entity.id)
        assert mirrored is not None
        assert mirrored.parent_id == folder.id
        assert mirrored.node_kind == "entity"
        assert mirrored.name == "Louise Livingstone"
        assert mirrored.attributes["entity_type"] == "person"
        retrieved = temp_db.get(KnowledgeEntity, entity.id)
        assert retrieved is not None
        assert retrieved.parent_id == folder.id
        assert retrieved.canonical_name == "Louise Livingstone"

    def test_refile_entity_moves_document_node(self, temp_db):
        first = Document(id="folder-1", name="Folder 1", doc_type=DocType.folder)
        second = Document(id="folder-2", name="Folder 2", doc_type=DocType.folder)
        temp_db.save(first)
        temp_db.save(second)
        entity = KnowledgeEntity(
            id="entity-move",
            canonical_name="Deloro",
            entity_type=EntityType.location,
            parent_id=first.id,
        )
        temp_db.save(entity)

        entity.parent_id = second.id
        temp_db.save(entity)

        mirrored = temp_db.get(Document, entity.id)
        assert mirrored is not None
        assert mirrored.parent_id == second.id
        retrieved = temp_db.get(KnowledgeEntity, entity.id)
        assert retrieved is not None
        assert retrieved.parent_id == second.id

    def test_unfiled_entity_has_no_document_node(self, temp_db):
        entity = KnowledgeEntity(canonical_name="Mining", entity_type=EntityType.concept)
        temp_db.save(entity)

        assert temp_db.get(Document, entity.id) is None

    def test_filed_entity_parent_missing_raises(self, temp_db):
        entity = KnowledgeEntity(
            canonical_name="Orphaned",
            entity_type=EntityType.other,
            parent_id="missing-folder",
        )

        with pytest.raises(ValueError, match="Parent not found"):
            temp_db.save(entity)

    def test_filed_entity_non_folder_parent_raises(self, temp_db):
        page = Document(id="page-parent", name="Page", doc_type=DocType.page)
        temp_db.save(page)
        entity = KnowledgeEntity(
            canonical_name="Bad Parent",
            entity_type=EntityType.other,
            parent_id=page.id,
        )

        with pytest.raises(ValueError, match="Parent is not a folder"):
            temp_db.save(entity)


class TestResearchContentFold:
    def test_save_and_get_plan_task_step(self, temp_db):
        project = ResearchProject(name="Workspace Root")
        temp_db.save(project)
        plan = ResearchPlan(
            project_id=project.id,
            name="Plan A",
            description="Outline",
            order_index=2,
            metadata={"term": "gold"},
        )
        temp_db.save(plan)
        task = ResearchTask(
            plan_id=plan.id,
            name="Task A",
            description="Search archive",
            priority=3,
            assigned_to="agent",
            metadata={"lane": "research"},
        )
        temp_db.save(task)
        step = ResearchStep(
            task_id=task.id,
            tool=StepTool.web_search,
            label="Search Web",
            description="Do search",
            config={"query": "gold archive"},
            result={"hits": 3},
            order_index=1,
        )
        temp_db.save(step)

        assert temp_db.get(ResearchPlan, plan.id).project_id == project.id
        assert temp_db.get(ResearchTask, task.id).plan_id == plan.id
        assert temp_db.get(ResearchStep, step.id).task_id == task.id

        plan_doc = temp_db.get(Document, plan.id)
        assert plan_doc is not None
        assert plan_doc.parent_id == project.id
        assert plan_doc.prototype_key == "research_plan"
        assert plan_doc.node_kind == "plan"

        task_doc = temp_db.get(Document, task.id)
        assert task_doc is not None
        assert task_doc.parent_id == plan.id
        assert task_doc.prototype_key == "research_task"
        assert task_doc.node_kind == "task"

        step_doc = temp_db.get(Document, step.id)
        assert step_doc is not None
        assert step_doc.parent_id == task.id
        assert step_doc.prototype_key == "research_step"
        assert step_doc.node_kind == "step"
        assert step_doc.attributes["tool"] == "web_search"

    def test_research_content_reads_from_folded_document_nodes(self, temp_db):
        project_doc = Document(
            id="ws-root",
            name="Workspace Root",
            node_kind="workspace",
            prototype_key="research_workspace",
            doc_type=DocType.folder,
            is_workspace=True,
            attributes={
                "description": "",
                "status": "active",
                "created_by": "human",
                "library_destination_folder_id": None,
                "metadata": {},
            },
        )
        plan_doc = Document(
            id="plan-doc",
            parent_id="ws-root",
            name="Plan Node",
            node_kind="plan",
            prototype_key="research_plan",
            doc_type=DocType.folder,
            attributes={
                "description": "node plan",
                "status": "active",
                "order_index": 7,
                "metadata": {"topic": "letters"},
            },
        )
        task_doc = Document(
            id="task-doc",
            parent_id="plan-doc",
            name="Task Node",
            node_kind="task",
            prototype_key="research_task",
            doc_type=DocType.folder,
            attributes={
                "description": "node task",
                "status": "in_progress",
                "priority": 4,
                "assigned_to": "agent",
                "metadata": {"role": "search"},
                "completed_at": None,
            },
        )
        step_doc = Document(
            id="step-doc",
            parent_id="task-doc",
            name="Step Node",
            node_kind="step",
            prototype_key="research_step",
            doc_type=DocType.file,
            attributes={
                "tool": "web_search",
                "description": "node step",
                "config": {"query": "letters"},
                "status": "completed",
                "result": {"hits": 2},
                "error": None,
                "order_index": 1,
                "completed_at": None,
            },
        )
        temp_db.save(project_doc)
        temp_db.save(plan_doc)
        temp_db.save(task_doc)
        temp_db.save(step_doc)

        assert temp_db.get(ResearchPlan, "plan-doc").project_id == "ws-root"
        assert temp_db.get(ResearchTask, "task-doc").plan_id == "plan-doc"
        assert temp_db.get(ResearchStep, "step-doc").task_id == "task-doc"

    def test_research_plan_round_trips_with_preserved_parent_edge(self, temp_db):
        plan = ResearchPlan(
            project_id="missing-workspace-parent",
            name="Detached Plan",
            description="still mirrored",
            metadata={"odd": []},
        )
        temp_db.save(plan)

        mirrored = temp_db.get(Document, plan.id)
        assert mirrored.parent_id == "missing-workspace-parent"

        retrieved = temp_db.get(ResearchPlan, plan.id)
        assert retrieved.project_id == "missing-workspace-parent"
        assert retrieved.metadata == {"odd": []}

    def test_research_plan_missing_parent_id_raises(self, temp_db):
        doc = Document(
            id="plan-missing-parent",
            name="Plan Node",
            node_kind="plan",
            prototype_key="research_plan",
            doc_type=DocType.folder,
            attributes={"description": "", "status": "draft", "order_index": 0, "metadata": {}},
        )
        temp_db.save(doc)

        with pytest.raises(ValueError, match="missing project parent_id"):
            temp_db.get(ResearchPlan, doc.id)

    def test_research_task_invalid_completed_at_payload_raises(self, temp_db):
        doc = Document(
            id="task-bad-completed-at",
            parent_id="plan-1",
            name="Task Node",
            node_kind="task",
            prototype_key="research_task",
            doc_type=DocType.folder,
            attributes={
                "description": "",
                "status": "pending",
                "priority": 0,
                "assigned_to": None,
                "metadata": {},
                "completed_at": "not-a-datetime",
            },
        )
        temp_db.save(doc)

        with pytest.raises(ValueError, match="invalid completed_at payload"):
            temp_db.get(ResearchTask, doc.id)

    def test_research_step_invalid_tool_payload_raises(self, temp_db):
        doc = Document(
            id="step-bad-tool",
            parent_id="task-1",
            name="Step Node",
            node_kind="step",
            prototype_key="research_step",
            doc_type=DocType.file,
            attributes={
                "tool": "unknown_tool",
                "description": "",
                "config": {},
                "status": "pending",
                "result": {},
                "error": None,
                "order_index": 0,
            },
        )
        temp_db.save(doc)

        with pytest.raises(ValueError, match="invalid tool payload"):
            temp_db.get(ResearchStep, doc.id)


class TestRoomRoundTrips:
    def test_spatial_room_round_trips_odd_metadata_payload(self, temp_db):
        room = SpatialRoom(
            name="Odd Room",
            description="",
            metadata={"nested": {"items": []}, "flag": False},
        )
        temp_db.save(room)

        retrieved = temp_db.get(SpatialRoom, room.id)
        assert retrieved is not None
        assert retrieved.description == ""
        assert retrieved.metadata == {"nested": {"items": []}, "flag": False}


class TestLibraryLinkBackfill:
    def test_reopen_backfills_claim_links_into_library_links(self):
        """Legacy claim-link rows should appear in the generic library-link table."""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.duckdb"
        db = Database(db_path)
        try:
            doc = Document(name="Doc", doc_type=DocType.file)
            db.save(doc)
            first = KnowledgeClaim(
                id="claim-a",
                text="First",
                source_document_id=doc.id,
                entity_ids=[],
            )
            second = KnowledgeClaim(
                id="claim-b",
                text="Second",
                source_document_id=doc.id,
                entity_ids=[],
            )
            db.save(first)
            db.save(second)
            db.save(KnowledgeClaimLink(
                id="claim-link-1",
                claim_id=first.id,
                related_claim_id=second.id,
                relation_type=ClaimRelationType.supports,
            ))
            db._execute("DELETE FROM libraryitemlinks WHERE id = $id", {"id": "claim-link-1"})
            assert db.get(LibraryItemLink, "claim-link-1") is None
            db.close()

            reopened = Database(db_path)
            try:
                mirrored = reopened.get(LibraryItemLink, "claim-link-1")
                assert mirrored is not None
                assert mirrored.source_id == first.id
                assert mirrored.source_type.value == "claim"
                assert mirrored.target_id == second.id
                assert mirrored.target_type.value == "claim"
            finally:
                reopened.close()
        finally:
            shutil.rmtree(tmpdir)

    def test_reopen_backfills_saved_search_document(self):
        """Existing saved-search rows are backfilled into document nodes on open."""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.duckdb"
        db = Database(db_path)
        try:
            saved = SavedSearch(query="reopen me")
            db.save(saved)
            db._execute("DELETE FROM documents WHERE id = $id", {"id": saved.id})
            assert db.get(Document, saved.id) is None
            db.close()

            reopened = Database(db_path)
            try:
                mirrored = reopened.get(Document, saved.id)
                assert mirrored is not None
                assert mirrored.node_kind == "saved_search"
                assert mirrored.prototype_key == "saved_search"
                assert mirrored.attributes["query"] == "reopen me"
                assert mirrored.metadata["saved_search_query"] == "reopen me"
            finally:
                reopened.close()
        finally:
            shutil.rmtree(tmpdir)

    def test_reopen_backfills_workflow_document(self):
        """Existing workflow rows are backfilled into mirrored document nodes on
        open (#11 Phase 1), same as the saved-search/milestone/note mirrors."""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.duckdb"
        db = Database(db_path)
        try:
            workflow = Workflow(name="Reopen Me", provider="openai", is_system=True)
            db.save(workflow)
            db._execute("DELETE FROM documents WHERE id = $id", {"id": workflow.id})
            assert db.get(Document, workflow.id) is None
            db.close()

            reopened = Database(db_path)
            try:
                mirrored = reopened.get(Document, workflow.id)
                assert mirrored is not None
                assert mirrored.node_kind == "workflow"
                assert mirrored.prototype_key == "workflow"
                assert mirrored.attributes["provider"] == "openai"
                assert mirrored.attributes["scope"] == "global"
                from fichero import db as db_module
                assert mirrored.parent_id == db_module._DEFAULT_WORKFLOWS_CONTAINER_ID

                # The workflow row itself is untouched — mirror is a shadow.
                retrieved = reopened.get(Workflow, workflow.id)
                assert retrieved is not None
                assert retrieved.name == "Reopen Me"
            finally:
                reopened.close()
        finally:
            shutil.rmtree(tmpdir)

    def test_reopen_backfills_research_workspace_document(self):
        """Existing research-project rows are backfilled into workspace nodes on open."""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.duckdb"
        db = Database(db_path)
        try:
            project = ResearchProject(name="Reopen Workspace")
            db.save(project)
            db._execute("DELETE FROM documents WHERE id = $id", {"id": project.id})
            assert db.get(Document, project.id) is None
            db.close()

            reopened = Database(db_path)
            try:
                mirrored = reopened.get(Document, project.id)
                assert mirrored is not None
                assert mirrored.node_kind == "workspace"
                assert mirrored.prototype_key == "research_workspace"
                assert mirrored.is_workspace is True
                assert mirrored.attributes["description"] == ""
            finally:
                reopened.close()
        finally:
            shutil.rmtree(tmpdir)

    def test_reopen_backfills_spatial_room_document(self):
        """Existing SpatialRoom rows are backfilled into room document nodes on open."""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.duckdb"
        db = Database(db_path)
        try:
            room = SpatialRoom(
                name="Reopen Room",
                description="Node me",
                room_type=RoomType.presentation,
                owner_id="human",
                metadata={"theme": "gold"},
            )
            db.save(room)
            db._execute("DELETE FROM documents WHERE id = $id", {"id": room.id})
            assert db.get(Document, room.id) is None
            db.close()

            reopened = Database(db_path)
            try:
                mirrored = reopened.get(Document, room.id)
                assert mirrored is not None
                assert mirrored.node_kind == "room"
                assert mirrored.prototype_key == "room"
                assert mirrored.doc_type == "folder"
                assert mirrored.attributes["description"] == "Node me"
                assert mirrored.attributes["room_type"] == "presentation"
                assert mirrored.attributes["owner_id"] == "human"
                assert mirrored.attributes["metadata"] == {"theme": "gold"}
            finally:
                reopened.close()
        finally:
            shutil.rmtree(tmpdir)

    def test_reopen_backfills_research_content_documents(self):
        """Existing research plan/task/step rows are backfilled into document nodes on open."""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test.duckdb"
        db = Database(db_path)
        try:
            project = ResearchProject(name="Workspace Root")
            db.save(project)
            plan = ResearchPlan(project_id=project.id, name="Plan Backfill")
            task = ResearchTask(plan_id=plan.id, name="Task Backfill")
            step = ResearchStep(
                task_id=task.id,
                tool=StepTool.web_search,
                label="Step Backfill",
            )
            db.save(plan)
            db.save(task)
            db.save(step)
            db._execute(
                "DELETE FROM documents WHERE id IN ($plan_id, $task_id, $step_id)",
                {
                    "plan_id": plan.id,
                    "task_id": task.id,
                    "step_id": step.id,
                },
            )
            db.close()

            reopened = Database(db_path)
            try:
                assert reopened.get(Document, plan.id).prototype_key == "research_plan"
                assert reopened.get(Document, task.id).prototype_key == "research_task"
                assert reopened.get(Document, step.id).prototype_key == "research_step"
            finally:
                reopened.close()
        finally:
            shutil.rmtree(tmpdir)


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

    def test_import_parquet_rejects_parent_traversal_path(self, temp_db):
        """Parquet imports must stay confined to the library package."""
        outside = temp_db.path.parent.parent / f"escaped-{uuid4().hex}.parquet"
        conn = duckdb.connect()
        try:
            conn.execute(f"COPY (SELECT 1 AS ok) TO '{outside}' (FORMAT PARQUET)")
        finally:
            conn.close()
        try:
            with pytest.raises(ValueError, match="must stay inside the library package"):
                temp_db.import_parquet(Document, Path("..") / outside.name)
        finally:
            outside.unlink(missing_ok=True)

    def test_import_parquet_rejects_malicious_column_name(self, temp_db):
        """Column names with SQL metacharacters are rejected before import."""
        bad_path = temp_db.path.parent / "bad-columns.parquet"
        conn = duckdb.connect()
        try:
            conn.execute(
                f"""COPY (
                    SELECT 1 AS "bad;drop table documents;--"
                ) TO '{bad_path}' (FORMAT PARQUET)"""
            )
        finally:
            conn.close()

        with pytest.raises(ValueError, match="Invalid Parquet column name"):
            temp_db.import_parquet(Document, bad_path)


class TestEmbeddingsModelLoading:
    """Test embedding model loading/caching behavior."""

    def test_embedder_uses_managed_cache_dir(self, temp_db, monkeypatch):
        """Embedding model should use app-managed cache dir and the pinned alias."""
        import sys
        import types
        import fichero.db_embeddings as db_embeddings_module
        from fichero.local_models import MODELS_BASE

        calls: list[dict] = []

        class FakeTextEmbedding:
            def __init__(self, *, model_name: str, cache_dir: str):
                calls.append({"model_name": model_name, "cache_dir": cache_dir})

            def embed(self, texts):
                for _ in texts:
                    yield [0.1, 0.2]

        fake_fastembed = types.SimpleNamespace(TextEmbedding=FakeTextEmbedding)
        monkeypatch.setitem(sys.modules, "fastembed", fake_fastembed)
        # _ensure_embedder registers the model via _register_fastembed_model_for_space
        # (the embedding-space refactor, #2542); stub THAT — the previously-patched
        # _register_pinned_fastembed_model is no longer on the call path, so the real
        # `from fastembed.common.model_description import ...` ran against the fake
        # fastembed namespace and raised (masked as "fastembed not installed").
        monkeypatch.setattr(
            db_embeddings_module,
            "_register_fastembed_model_for_space",
            lambda _space: None,
        )
        monkeypatch.delenv("FICHERO_EMBED_MODEL", raising=False)
        db_embeddings_module._EMBEDDER_CACHE.clear()

        temp_db._embedder = None
        temp_db._ensure_embedder()

        assert len(calls) == 1
        assert calls[0]["model_name"] == "fichero-pinned/multilingual-e5-large-mean-v1"
        assert calls[0]["cache_dir"] == str(MODELS_BASE / "embeddings")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ---------------------------------------------------------------------------
# use_fuzzy_match — typo-tolerant full-text search
# ---------------------------------------------------------------------------

class TestFuzzyMatch:
    """_fuzzy_contains_any_term matches terms with 1-2 char differences."""

    def test_exact_match_still_works(self):
        import pandas as pd
        from fichero.db import _fuzzy_contains_any_term, _fold_for_search

        series = pd.Series(["hello world", "foo bar", "baz"])
        terms = [_fold_for_search("hello")]
        mask = _fuzzy_contains_any_term(series, terms)
        assert mask.tolist() == [True, False, False]

    def test_typo_matches_with_cutoff(self):
        import pandas as pd
        from fichero.db import _fuzzy_contains_any_term, _fold_for_search

        series = pd.Series(["quibdo choco", "medellin", "bogota"])
        # "quibdo" vs "quibdó" — after folding both are "quibdo"
        terms = [_fold_for_search("quibdo")]
        mask = _fuzzy_contains_any_term(series, terms)
        assert mask.tolist() == [True, False, False]

    def test_near_miss_catches_typo(self):
        import pandas as pd
        from fichero.db import _fuzzy_contains_any_term, _fold_for_search

        # "asprilla" is a typo for "asprilla" (one character different)
        series = pd.Series(["jose antonio asprilla garcia"])
        terms = [_fold_for_search("asprilla")]
        # SequenceMatcher("asprilla", "asprilla").ratio() = 0.9375 >= 0.6
        mask = _fuzzy_contains_any_term(series, terms)
        assert mask.tolist() == [True]

    def test_substring_fallback(self):
        import pandas as pd
        from fichero.db import _fuzzy_contains_any_term

        # Multi-word term present as substring
        series = pd.Series(["the colombian coffee federation"])
        terms = ["colombian coffee"]
        mask = _fuzzy_contains_any_term(series, terms)
        assert mask.tolist() == [True]

    def test_empty_terms_returns_false_mask(self):
        import pandas as pd
        from fichero.db import _fuzzy_contains_any_term

        series = pd.Series(["hello", "world"])
        mask = _fuzzy_contains_any_term(series, [])
        assert mask.tolist() == [False, False]

    def test_no_match_returns_false(self):
        import pandas as pd
        from fichero.db import _fuzzy_contains_any_term

        series = pd.Series(["hello world", "foo bar"])
        terms = ["xyzzy"]
        mask = _fuzzy_contains_any_term(series, terms, cutoff=0.6)
        assert mask.tolist() == [False, False]
