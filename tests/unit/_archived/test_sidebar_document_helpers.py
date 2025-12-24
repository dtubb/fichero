"""Tests for sidebar Document helper functions.

Verifies documents_to_sidebar_items and document_to_sidebar_item work correctly.
"""
import pytest
import sys
import tempfile
from pathlib import Path

# Skip GUI-dependent tests on non-macOS
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="Sidebar helpers require macOS"
)


@pytest.fixture
def test_db():
    """Create a temporary database for testing."""
    from fichero.db import Database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        db = Database(db_path)

        # Patch the global db for the duration of the test
        import fichero.db
        old_db = fichero.db.db
        fichero.db.db = db

        yield db

        # Restore
        fichero.db.db = old_db
        db.close()


class TestDocumentsToSidebarItems:
    """Test documents_to_sidebar_items conversion."""

    def test_empty_list(self, test_db):
        """Empty input should return empty output."""
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        items = documents_to_sidebar_items([])
        assert items == []

    def test_single_collection(self, test_db):
        """Single collection should create one section."""
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        collection = Document(
            name="My Archive",
            doc_type=DocType.collection,
            metadata={"source_type": "local"}
        )
        test_db.save(collection)

        items = documents_to_sidebar_items([collection])

        assert len(items) == 1
        assert items[0].is_header
        assert items[0].text == "COLLECTIONS"
        assert len(items[0].children) == 1
        assert items[0].children[0].text == "My Archive"

    def test_external_collection(self, test_db):
        """External collection should go in EXTERNAL section."""
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        collection = Document(
            name="External Folder",
            doc_type=DocType.collection,
            metadata={"source_type": "external"}
        )
        test_db.save(collection)

        items = documents_to_sidebar_items([collection])

        assert len(items) == 1
        assert items[0].text == "EXTERNAL"
        assert len(items[0].children) == 1
        assert items[0].children[0].text == "External Folder"
        assert items[0].children[0].icon == "link"

    def test_mixed_collections(self, test_db):
        """Mix of local and external creates two sections."""
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        local = Document(
            name="Local Archive",
            doc_type=DocType.collection,
            metadata={"source_type": "local"}
        )
        external = Document(
            name="External Folder",
            doc_type=DocType.collection,
            metadata={"source_type": "external"}
        )
        test_db.save(local)
        test_db.save(external)

        items = documents_to_sidebar_items([local, external])

        assert len(items) == 2
        section_names = {item.text for item in items}
        assert section_names == {"COLLECTIONS", "EXTERNAL"}

    def test_collection_with_children(self, test_db):
        """Collection with folders should have children."""
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        collection = Document(
            name="Archive",
            doc_type=DocType.collection,
            metadata={"source_type": "local"}
        )
        test_db.save(collection)

        # Add folder children
        folder1 = Document(
            name="1920s",
            doc_type=DocType.folder,
            parent_id=collection.id
        )
        folder2 = Document(
            name="1930s",
            doc_type=DocType.folder,
            parent_id=collection.id
        )
        test_db.save(folder1)
        test_db.save(folder2)

        items = documents_to_sidebar_items([collection])

        # Should have section with one collection
        assert len(items) == 1
        collection_item = items[0].children[0]

        # Collection should have folder children
        assert len(collection_item.children) == 2
        child_names = {c.text for c in collection_item.children}
        assert child_names == {"1920s", "1930s"}

    def test_badge_count(self, test_db):
        """Collection badge should show child count."""
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        collection = Document(
            name="Archive",
            doc_type=DocType.collection,
            metadata={"source_type": "local"}
        )
        test_db.save(collection)

        # Add files (not folders)
        for i in range(5):
            doc = Document(
                name=f"doc{i}.jpg",
                doc_type=DocType.file,
                parent_id=collection.id
            )
            test_db.save(doc)

        items = documents_to_sidebar_items([collection])
        collection_item = items[0].children[0]

        # Badge should show "5"
        assert collection_item.badge == "5"

    def test_flat_list_no_grouping(self, test_db):
        """group_by_type=False should return flat list."""
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        collections = [
            Document(name="Col1", doc_type=DocType.collection, metadata={"source_type": "local"}),
            Document(name="Col2", doc_type=DocType.collection, metadata={"source_type": "external"}),
        ]
        for c in collections:
            test_db.save(c)

        items = documents_to_sidebar_items(collections, group_by_type=False)

        # No section headers, just items
        assert len(items) == 2
        assert not any(item.is_header for item in items)
        names = {item.text for item in items}
        assert names == {"Col1", "Col2"}

    def test_document_stored_in_data(self, test_db):
        """Original Document should be stored in item.data."""
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import documents_to_sidebar_items

        collection = Document(
            name="Archive",
            doc_type=DocType.collection,
        )
        test_db.save(collection)

        items = documents_to_sidebar_items([collection])
        collection_item = items[0].children[0]

        # data should be the original Document
        assert collection_item.data is not None
        assert collection_item.data.id == collection.id
        assert collection_item.data.name == "Archive"


class TestDocumentToSidebarItem:
    """Test single document conversion."""

    def test_basic_conversion(self, test_db):
        """Single document should convert correctly."""
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import document_to_sidebar_item

        doc = Document(
            name="My Collection",
            doc_type=DocType.collection,
        )
        test_db.save(doc)

        item = document_to_sidebar_item(doc)

        assert item.id == doc.id
        assert item.text == "My Collection"
        assert item.data.id == doc.id

    def test_external_icon(self, test_db):
        """External collection should have link icon."""
        from fichero.models import Document, DocType
        from fichero.app.main_window.sidebar import document_to_sidebar_item

        doc = Document(
            name="External",
            doc_type=DocType.collection,
            metadata={"source_type": "external"}
        )
        test_db.save(doc)

        item = document_to_sidebar_item(doc)
        assert item.icon == "link"
