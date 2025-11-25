"""
Tests for PreviewMetadataPane - UI component for displaying transcriptions and catalog metadata
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import toga
from fichero.windows.main.views.preview.preview_metadata_pane import PreviewMetadataPane


class TestPreviewMetadataPane:
    """Test PreviewMetadataPane component"""

    @pytest.fixture
    def mock_app(self):
        """Create a mock Toga app"""
        app = Mock()
        app.paths = Mock()
        app.paths.app = "/fake/app/path"
        return app

    @pytest.fixture
    def mock_library_manager(self):
        """Create a mock library manager"""
        manager = Mock()
        # Mock async methods
        manager.get_item = AsyncMock()
        manager.get_item_transcriptions = AsyncMock()
        manager.get_item_catalog_data = AsyncMock()
        return manager

    @pytest.fixture
    def metadata_pane(self, mock_app, mock_library_manager):
        """Create a PreviewMetadataPane instance"""
        return PreviewMetadataPane(
            app=mock_app,
            is_mobile=False,
            library_manager=mock_library_manager
        )

    def test_initialization(self, metadata_pane, mock_library_manager):
        """Test that metadata pane initializes correctly"""
        assert metadata_pane.library_manager == mock_library_manager
        assert metadata_pane.is_mobile is False
        assert metadata_pane.current_item_id is None
        assert hasattr(metadata_pane, 'content_container')

    def test_clear_metadata_pane(self, metadata_pane):
        """Test clearing the metadata pane"""
        metadata_pane.current_item_id = "test-item"

        metadata_pane.clear()

        assert metadata_pane.current_item_id is None
        # Should have placeholder text
        assert len(metadata_pane.content_container.children) == 1
        placeholder = metadata_pane.content_container.children[0]
        assert isinstance(placeholder, toga.Label)
        assert "No item selected" in placeholder.text

    @pytest.mark.asyncio
    async def test_load_item_success(self, metadata_pane, mock_library_manager):
        """Test successfully loading item metadata"""
        # Setup mock data
        item_data = Mock()
        item_data.name = "Test Item"
        item_data.type = "folder"
        item_data.original_path = "/test/path/file.jpg"

        mock_library_manager.get_item.return_value = item_data
        mock_library_manager.get_item_transcriptions.return_value = ["Test transcription text"]
        mock_library_manager.get_item_catalog_data.return_value = {"title": "Test Document"}

        # Load item
        await metadata_pane.load_item("test-item-id")

        # Verify library manager calls
        mock_library_manager.get_item.assert_called_once_with("test-item-id")
        mock_library_manager.get_item_transcriptions.assert_called_once_with("test-item-id")
        mock_library_manager.get_item_catalog_data.assert_called_once_with("test-item-id")

        # Verify current item is set
        assert metadata_pane.current_item_id == "test-item-id"

        # Verify content was added (header + sections)
        assert len(metadata_pane.content_container.children) > 1

    @pytest.mark.asyncio
    async def test_load_item_no_library_manager(self, metadata_pane):
        """Test loading item when no library manager is available"""
        metadata_pane.library_manager = None

        await metadata_pane.load_item("test-item-id")

        # Should show error
        assert len(metadata_pane.content_container.children) == 1
        error_label = metadata_pane.content_container.children[0]
        assert isinstance(error_label, toga.Label)
        assert "Error:" in error_label.text

    @pytest.mark.asyncio
    async def test_load_item_not_found(self, metadata_pane, mock_library_manager):
        """Test loading item that doesn't exist"""
        mock_library_manager.get_item.return_value = None

        await metadata_pane.load_item("nonexistent-item")

        # Should show error
        assert len(metadata_pane.content_container.children) == 1
        error_label = metadata_pane.content_container.children[0]
        assert isinstance(error_label, toga.Label)
        assert "Error:" in error_label.text

    @pytest.mark.asyncio
    async def test_add_library_transcriptions(self, metadata_pane, mock_library_manager):
        """Test adding transcriptions from library"""
        mock_library_manager.get_item_transcriptions.return_value = [
            "First transcription text",
            "Second transcription text"
        ]

        await metadata_pane._add_library_transcriptions("test-item")

        # Should have header + transcription inputs
        children = metadata_pane.content_container.children
        assert len(children) >= 3  # header + 2 transcriptions

        # Check for transcription header
        header_found = any(
            isinstance(child, toga.Label) and "Transcriptions" in child.text
            for child in children
        )
        assert header_found

        # Check for transcription inputs
        text_inputs = [child for child in children if isinstance(child, toga.MultilineTextInput)]
        assert len(text_inputs) == 2
        assert text_inputs[0].value == "First transcription text"
        assert text_inputs[1].value == "Second transcription text"

    @pytest.mark.asyncio
    async def test_add_library_catalog_data(self, metadata_pane, mock_library_manager):
        """Test adding catalog data from library"""
        catalog_data = {
            "title": "Test Document",
            "date": "2024-01-01",
            "author": "Test Author"
        }
        mock_library_manager.get_item_catalog_data.return_value = catalog_data

        await metadata_pane._add_library_catalog_data("test-item")

        # Should have header + catalog display
        children = metadata_pane.content_container.children
        assert len(children) >= 2

        # Check for catalog header
        header_found = any(
            isinstance(child, toga.Label) and "Catalog Data" in child.text
            for child in children
        )
        assert header_found

        # Check for catalog text input
        text_inputs = [child for child in children if isinstance(child, toga.MultilineTextInput)]
        assert len(text_inputs) == 1
        # Should contain formatted JSON
        assert "title" in text_inputs[0].value
        assert "Test Document" in text_inputs[0].value

    def test_add_library_metadata(self, metadata_pane):
        """Test adding item metadata"""
        item_data = Mock()
        item_data.name = "Test Item"
        item_data.type = "folder"
        item_data.original_path = "/test/path/document.pdf"

        metadata_pane._add_library_metadata(item_data)

        # Should have header + metadata display
        children = metadata_pane.content_container.children
        assert len(children) >= 2

        # Check for metadata header
        header_found = any(
            isinstance(child, toga.Label) and "Item Metadata" in child.text
            for child in children
        )
        assert header_found

        # Check for metadata text input
        text_inputs = [child for child in children if isinstance(child, toga.MultilineTextInput)]
        assert len(text_inputs) == 1
        metadata_text = text_inputs[0].value
        assert "Name: Test Item" in metadata_text
        assert "Type: folder" in metadata_text
        assert "File: document.pdf" in metadata_text

    def test_fonts_applied(self, metadata_pane):
        """Test that SF Pro Display font is applied to labels"""
        metadata_pane.clear()

        # Check placeholder uses system font (returned as list by Toga)
        placeholder = metadata_pane.content_container.children[0]
        assert 'system' in placeholder.style.font_family

    @pytest.mark.asyncio
    async def test_no_emojis_in_text(self, metadata_pane, mock_library_manager):
        """Test that emojis are removed from all text content"""
        # Setup mock data
        item_data = Mock()
        item_data.name = "Test Item"

        mock_library_manager.get_item.return_value = item_data
        mock_library_manager.get_item_transcriptions.return_value = ["Test transcription"]
        mock_library_manager.get_item_catalog_data.return_value = {"title": "Test"}

        await metadata_pane.load_item("test-item")

        # Check all labels for emojis
        for child in metadata_pane.content_container.children:
            if isinstance(child, toga.Label):
                # Common emojis that were in the original code
                assert "📄" not in child.text
                assert "📁" not in child.text
                assert "📝" not in child.text
                assert "📊" not in child.text
                assert "❌" not in child.text