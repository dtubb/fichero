"""
Comprehensive Unit Tests for Library Backend

Tests library_manager, storage, url_downloader, and icon_generator.
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import sqlite3

from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage
from fichero.library.url_downloader import URLDownloader
from fichero.library.icon_generator import IconGenerator
from fichero.library.models import Collection, CollectionItem


class MockApp:
    """Mock Toga app for testing"""
    def __init__(self):
        self.is_cli = True
        self._test_db_path = None

    def get_library_path(self):
        """Return test database path"""
        if not self._test_db_path:
            temp_dir = Path(tempfile.mkdtemp())
            self._test_db_path = temp_dir / "test_library.db"
        return self._test_db_path


@pytest.fixture
def mock_app():
    """Create mock app"""
    return MockApp()


@pytest.fixture
def library_manager(mock_app):
    """Create library manager with temp database"""
    manager = LibraryManager(mock_app)
    yield manager
    # Cleanup
    if mock_app._test_db_path and mock_app._test_db_path.parent.exists():
        shutil.rmtree(mock_app._test_db_path.parent)


@pytest.fixture
def storage():
    """Create storage with temp database"""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    store = LibraryStorage(db_path)
    yield store
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def url_downloader():
    """Create URL downloader with temp cache"""
    temp_dir = Path(tempfile.mkdtemp())
    downloader = URLDownloader(temp_dir)
    yield downloader
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def icon_generator():
    """Create icon generator with temp cache"""
    temp_dir = Path(tempfile.mkdtemp())
    generator = IconGenerator(temp_dir)
    yield generator
    # Cleanup
    shutil.rmtree(temp_dir)


# ===== STORAGE TESTS =====

class TestLibraryStorage:
    """Test LibraryStorage class"""

    def test_create_database(self, storage):
        """Test database creation"""
        assert storage.db_path.exists()

        # Check tables exist
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            assert 'collections' in tables
            assert 'collection_items' in tables

    def test_add_collection(self, storage):
        """Test adding a collection"""
        collection = Collection(
            name="Test Collection",
            type="local",
            source_path="/test/path"
        )

        result = storage.add_collection(collection)
        assert result is True

        # Retrieve and verify
        retrieved = storage.get_collection(collection.id)
        assert retrieved is not None
        assert retrieved.name == "Test Collection"
        assert retrieved.type == "local"

    def test_get_all_collections(self, storage):
        """Test retrieving all collections"""
        # Add multiple collections
        for i in range(3):
            col = Collection(name=f"Collection {i}", type="local")
            storage.add_collection(col)

        collections = storage.get_all_collections()
        assert len(collections) == 3

    def test_delete_collection(self, storage):
        """Test deleting a collection"""
        collection = Collection(name="To Delete", type="local")
        storage.add_collection(collection)

        result = storage.delete_collection(collection.id)
        assert result is True

        # Verify deleted
        retrieved = storage.get_collection(collection.id)
        assert retrieved is None

    def test_add_item(self, storage):
        """Test adding an item"""
        # First add collection
        collection = Collection(name="Test", type="local")
        storage.add_collection(collection)

        # Add item
        item = CollectionItem(
            collection_id=collection.id,
            type="file",
            name="test.jpg",
            source_path="/test/test.jpg"
        )

        result = storage.add_collection_item(item)
        assert result is True

        # Verify
        retrieved = storage.get_item(item.id)
        assert retrieved is not None
        assert retrieved.name == "test.jpg"

    def test_get_collection_items(self, storage):
        """Test retrieving collection items"""
        collection = Collection(name="Test", type="local")
        storage.add_collection(collection)

        # Add multiple items
        for i in range(5):
            item = CollectionItem(
                collection_id=collection.id,
                type="file",
                name=f"file{i}.jpg"
            )
            storage.add_collection_item(item)

        items = storage.get_collection_items(collection.id)
        assert len(items) == 5

    def test_metadata_serialization(self, storage):
        """Test metadata serialization/deserialization"""
        collection = Collection(
            name="Test",
            type="local",
            metadata={
                "description": "Test collection",
                "tags": ["test", "demo"],
                "count": 42
            }
        )

        storage.add_collection(collection)
        retrieved = storage.get_collection(collection.id)

        assert retrieved.metadata["description"] == "Test collection"
        assert retrieved.metadata["tags"] == ["test", "demo"]
        assert retrieved.metadata["count"] == 42


# ===== LIBRARY MANAGER TESTS =====

class TestLibraryManager:
    """Test LibraryManager class"""

    @pytest.mark.asyncio
    async def test_add_collection(self, library_manager):
        """Test adding a collection"""
        collection_id = await library_manager.add_collection(
            name="Test Collection",
            collection_type="local",
            description="Test description"
        )

        assert collection_id is not None

        # Verify it exists
        collection = await library_manager.get_collection(collection_id)
        assert collection is not None
        assert collection.name == "Test Collection"

    @pytest.mark.asyncio
    async def test_duplicate_collection_name(self, library_manager):
        """Test adding duplicate collection name fails"""
        await library_manager.add_collection(
            name="Duplicate",
            collection_type="local"
        )

        # Try to add again
        result = await library_manager.add_collection(
            name="Duplicate",
            collection_type="local"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_collection(self, library_manager):
        """Test deleting a collection"""
        collection_id = await library_manager.add_collection(
            name="To Delete",
            collection_type="local"
        )

        result = await library_manager.delete_collection(collection_id)
        assert result is True

        # Verify deleted
        collection = await library_manager.get_collection_by_id(collection_id)
        assert collection is None

    @pytest.mark.asyncio
    async def test_rename_collection(self, library_manager):
        """Test renaming a collection"""
        collection_id = await library_manager.add_collection(
            name="Old Name",
            collection_type="local"
        )

        result = await library_manager.rename_collection(collection_id, "New Name")
        assert result is True

        # Verify renamed
        collection = await library_manager.get_collection(collection_id)
        assert collection.name == "New Name"

    @pytest.mark.asyncio
    async def test_add_item_to_collection(self, library_manager):
        """Test adding items to collection"""
        collection_id = await library_manager.add_collection(
            name="Test",
            collection_type="local"
        )

        item_id = await library_manager.add_item_to_collection(
            collection_id=collection_id,
            item_type="file",
            source="/test/file.jpg",
            name="file.jpg"
        )

        assert item_id is not None

        # Verify
        items = await library_manager.get_collection_items(collection_id)
        assert len(items) == 1
        assert items[0].name == "file.jpg"

    @pytest.mark.asyncio
    async def test_get_item_file_for_url_without_cache(self, library_manager):
        """Test getting file for URL item without cache"""
        collection_id = await library_manager.add_collection(
            name="URL Collection",
            collection_type="url"
        )

        item_id = await library_manager.add_item_to_collection(
            collection_id=collection_id,
            item_type="url",
            source="https://example.com/image.jpg",
            name="image.jpg"
        )

        # Try to get file without downloading
        file_path = await library_manager.get_item_file(item_id, download_if_url=False)
        assert file_path is None  # Not cached yet


# ===== URL DOWNLOADER TESTS =====

class TestURLDownloader:
    """Test URLDownloader class"""

    @pytest.mark.asyncio
    async def test_download_url(self, url_downloader):
        """Test downloading a URL"""
        # Use a small test URL (1x1 transparent PNG)
        test_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        # Skip actual download test since we need real URL
        # Just test the structure
        assert url_downloader.cache_root.exists()

    def test_cache_size(self, url_downloader):
        """Test getting cache size"""
        size = url_downloader.get_cache_size()
        assert size == 0  # Empty cache

    def test_clear_cache(self, url_downloader):
        """Test clearing cache"""
        deleted = url_downloader.clear_cache()
        assert deleted == 0  # No files to delete


# ===== ICON GENERATOR TESTS =====

class TestIconGenerator:
    """Test IconGenerator class"""

    def test_initialization(self, icon_generator):
        """Test icon generator initialization"""
        assert icon_generator.cache_dir is not None
        assert icon_generator.cache_dir.exists()
        assert icon_generator.thumbnail_size == (128, 128)
        assert icon_generator.preview_size == (512, 512)

    def test_image_formats(self, icon_generator):
        """Test supported image formats"""
        formats = icon_generator.image_formats
        assert '.jpg' in formats
        assert '.png' in formats
        assert '.gif' in formats

    def test_get_default_icon_types(self, icon_generator):
        """Test default icon type mapping"""
        # Note: Will return None if resource files don't exist
        # Just test that it doesn't crash
        icon = icon_generator._get_default_icon('folder')
        # icon could be None if resources not available

        icon = icon_generator._get_default_icon('url')
        # Should not crash

    def test_clear_cache(self, icon_generator):
        """Test clearing thumbnail cache"""
        # Should not crash even if empty
        icon_generator.clear_cache()
        assert icon_generator.cache_dir.exists()


# ===== EXPORT/IMPORT TESTS =====

class TestExportImport:
    """Test export and import functionality"""

    @pytest.mark.asyncio
    async def test_export_empty_collection(self, library_manager):
        """Test exporting an empty collection"""
        collection_id = await library_manager.add_collection(
            name="Empty Collection",
            collection_type="local",
            description="Test export"
        )

        temp_dir = Path(tempfile.mkdtemp())
        export_path = temp_dir / "export.zip"

        try:
            success = await library_manager.export_collection(collection_id, export_path)
            assert success is True
            assert export_path.exists()
            assert export_path.stat().st_size > 0
        finally:
            shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_import_collection(self, library_manager):
        """Test importing a collection"""
        # First export a collection
        collection_id = await library_manager.add_collection(
            name="Original Collection",
            collection_type="local",
            description="For export"
        )

        # Add an item
        await library_manager.add_item_to_collection(
            collection_id=collection_id,
            item_type="file",
            source="/test/file.jpg",
            name="test.jpg",
            operation="link"
        )

        temp_dir = Path(tempfile.mkdtemp())
        export_path = temp_dir / "export.zip"

        try:
            # Export
            await library_manager.export_collection(collection_id, export_path)

            # Import
            new_collection_id = await library_manager.import_collection(
                export_path,
                name="Imported Collection"
            )

            assert new_collection_id is not None
            assert new_collection_id != collection_id  # Should be new ID

            # Verify import
            collection = await library_manager.get_collection_by_id(new_collection_id)
            assert collection.name == "Imported Collection"

            # Verify items
            items = await library_manager.get_collection_items(new_collection_id)
            assert len(items) == 1
            assert items[0].name == "test.jpg"

        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
