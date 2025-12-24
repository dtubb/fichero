"""Integration tests for native window data flow.

Tests the data flow from database → sidebar → browser → editor → inspector.
Verifies that Document models flow through the system without duplication.
"""
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Skip all tests on non-macOS platforms
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="Native window components require macOS"
)

# Check if ObjC classes are available (requires running GUI environment)
def _objc_available():
    try:
        from rubicon.objc import ObjCClass
        ObjCClass("NSView")
        return True
    except (ImportError, NameError):
        return False

OBJC_AVAILABLE = _objc_available()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    from fichero.db import Database
    from fichero.models import Document, DocType, FileType, Status, Artifact

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.duckdb")

        # Create test data
        # Collection
        collection = Document(
            name="Test Archive",
            doc_type=DocType.collection,
            status=Status.completed,
        )
        db.save(collection)

        # Folder
        folder = Document(
            name="Box 1",
            parent_id=collection.id,
            doc_type=DocType.folder,
        )
        db.save(folder)

        # Files
        for i in range(5):
            doc = Document(
                name=f"letter_{i:03d}.jpg",
                parent_id=folder.id,
                doc_type=DocType.file,
                file_type=FileType.image,
                path=f"/archive/box1/letter_{i:03d}.jpg",
                metadata={
                    "thumbnail_path": f"/cache/thumb_{i:03d}.jpg",
                    "width": 800,
                    "height": 600,
                    "file_size": 102400,
                }
            )
            db.save(doc)

            # Add transcription artifact
            artifact = Artifact(
                document_id=doc.id,
                artifact_type="transcription",
                content=f"This is the transcription for document {i}.",
                provider="qwen",
            )
            db.save(artifact)

        yield db, collection, folder
        db.close()


class TestDatabaseToSidebar:
    """Test data flow from db.query() to sidebar items."""

    def test_query_returns_documents(self, temp_db):
        """db.query() should return Document models."""
        db, collection, folder = temp_db
        from fichero.models import Document, DocType

        collections = db.query(Document, doc_type=DocType.collection)

        assert len(collections) == 1
        assert collections[0].name == "Test Archive"
        assert collections[0].doc_type == DocType.collection

    @pytest.mark.skipif(not OBJC_AVAILABLE, reason="ObjC classes require GUI environment")
    def test_documents_to_sidebar_items(self, temp_db):
        """documents_to_sidebar_items should convert Documents to SourceListItems."""
        db, collection, folder = temp_db
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        collections = db.query(Document, doc_type=DocType.collection)
        items = documents_to_sidebar_items(collections)

        # Should create section with collection
        assert len(items) > 0
        # Section should have children
        section = items[0]
        assert hasattr(section, 'children')
        assert len(section.children) > 0
        # Child should have data pointing to Document
        child = section.children[0]
        assert child.data is not None
        assert child.data.id == collection.id
        assert child.data.name == "Test Archive"


class TestSidebarToBrowser:
    """Test data flow from sidebar selection to browser."""

    def test_query_children(self, temp_db):
        """Selecting a collection should query its children."""
        db, collection, folder = temp_db
        from fichero.models import Document

        # Simulate sidebar selection - query children of folder
        children = db.query(Document, parent_id=folder.id)

        assert len(children) == 5
        for child in children:
            assert child.name.startswith("letter_")

    def test_documents_have_display_properties(self, temp_db):
        """Documents should have properties needed by browser display."""
        db, collection, folder = temp_db
        from fichero.models import Document

        docs = db.query(Document, parent_id=folder.id)

        for doc in docs:
            # Properties needed by browser
            assert doc.name is not None
            assert doc.thumbnail_path is not None  # From metadata
            assert doc.id is not None


class TestBrowserToEditor:
    """Test data flow from browser selection to editor."""

    def test_document_has_path(self, temp_db):
        """Document should have path for editor to load."""
        db, collection, folder = temp_db
        from fichero.models import Document

        docs = db.query(Document, parent_id=folder.id)
        doc = docs[0]

        # Editor needs path to load image
        assert doc.path is not None
        assert doc.path.endswith(".jpg")

    def test_document_file_type_determines_editor(self, temp_db):
        """Document file_type should determine which editor to use."""
        db, collection, folder = temp_db
        from fichero.models import Document, FileType

        docs = db.query(Document, parent_id=folder.id)
        doc = docs[0]

        # Editor selection logic
        assert doc.file_type == FileType.image
        # ImageViewer would be selected for this


class TestBrowserToInspector:
    """Test data flow from browser selection to inspector."""

    def test_document_metadata_for_inspector(self, temp_db):
        """Document should have metadata for inspector display."""
        db, collection, folder = temp_db
        from fichero.models import Document

        docs = db.query(Document, parent_id=folder.id)
        doc = docs[0]

        # Inspector needs these
        assert doc.name is not None
        assert doc.doc_type is not None
        assert doc.status is not None
        assert doc.created_at is not None
        assert doc.width is not None
        assert doc.height is not None
        assert doc.file_size is not None

    def test_artifacts_for_inspector(self, temp_db):
        """Inspector should load artifacts for the document."""
        db, collection, folder = temp_db
        from fichero.models import Document, Artifact

        docs = db.query(Document, parent_id=folder.id)
        doc = docs[0]

        # Query artifacts for this document
        artifacts = db.query(Artifact, document_id=doc.id)

        assert len(artifacts) == 1
        assert artifacts[0].artifact_type == "transcription"
        assert artifacts[0].content is not None


class TestNoObjectDuplication:
    """Verify that we don't duplicate objects in memory."""

    def test_query_returns_independent_objects(self, temp_db):
        """Each query should return new Pydantic instances (expected behavior)."""
        db, collection, folder = temp_db
        from fichero.models import Document

        # Query twice
        docs1 = db.query(Document, parent_id=folder.id)
        docs2 = db.query(Document, parent_id=folder.id)

        # Should be equal but not the same object
        assert docs1[0].id == docs2[0].id
        assert docs1[0].name == docs2[0].name
        assert docs1[0] is not docs2[0]  # Different Pydantic instances

    @pytest.mark.skipif(not OBJC_AVAILABLE, reason="ObjC classes require GUI environment")
    def test_document_stored_in_item_data(self, temp_db):
        """Document should be stored in sidebar item's data field."""
        db, collection, folder = temp_db
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        collections = db.query(Document, doc_type=DocType.collection)
        items = documents_to_sidebar_items(collections)

        section = items[0]
        child = section.children[0]

        # The Document object is stored in item.data
        # This is the same object, not a copy
        assert isinstance(child.data, Document)
        assert child.data.id == collections[0].id


@pytest.mark.skipif(not OBJC_AVAILABLE, reason="ObjC classes require GUI environment")
class TestMainWindowControllerIntegration:
    """Test MainWindowController wiring (requires GUI environment)."""

    def test_controller_imports(self, temp_db):
        """MainWindowController and components should import without errors."""
        # This tests the import and basic structure
        # Full GUI testing requires macOS event loop
        db, collection, folder = temp_db

        # Just verify imports work
        from fichero.app.main_window.window import MainWindowController
        from fichero.app.main_window.sidebar import SourceList
        from fichero.app.main_window.browser import Browser
        from fichero.app.main_window.editor import EditorContainer
        from fichero.app.main_window.inspector import Inspector

        assert MainWindowController is not None
        assert SourceList is not None
        assert Browser is not None
        assert EditorContainer is not None
        assert Inspector is not None

    def test_commands_import(self):
        """Commands module should import and have expected handlers."""
        from fichero.app.main_window.commands import Commands

        # Commands class exists
        assert Commands is not None

        # Should have expected methods
        assert hasattr(Commands, 'zoom_in')
        assert hasattr(Commands, 'toggle_library')
        assert hasattr(Commands, 'import_file')
