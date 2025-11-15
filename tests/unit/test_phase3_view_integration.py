"""
Unit tests for Phase 3: View SelectionManager Integration

Tests that views correctly update SelectionManager when selections change.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))


class TestLibraryViewSelectionIntegration(unittest.TestCase):
    """Test LibraryView SelectionManager integration"""

    def setUp(self):
        """Set up test fixtures"""
        self.app = Mock()
        self.app.selection_manager = Mock()

    def test_library_view_updates_selection_manager_on_collection_select(self):
        """Test that LibraryView updates SelectionManager when collection is selected"""
        from fichero.windows.main.views.library.library_view import LibraryView

        # Create mock widget with selection
        widget = Mock()
        widget.selection = Mock()
        widget.selection.collection_data = {
            'id': 'collection-123',
            'name': 'Test Collection',
            'item_count': 42,
            'type': 'external',
            'source': '/test/path'
        }

        # Create view
        with patch('fichero.windows.main.views.library.library_view.BaseView.__init__'):
            view = LibraryView.__new__(LibraryView)
            view.app = self.app
            view.on_click = None
            view.on_collection_selected = None
            view.selected_collection = None

            # Call selection handler
            view._on_collection_selected(widget)

            # Verify SelectionManager was updated
            self.app.selection_manager.set_selection.assert_called_once()
            call_args = self.app.selection_manager.set_selection.call_args

            self.assertEqual(call_args[1]['view_id'], 'library')
            self.assertEqual(call_args[1]['item_ids'], ['collection-123'])
            self.assertEqual(len(call_args[1]['metadata']), 1)
            self.assertEqual(call_args[1]['metadata'][0]['collection_name'], 'Test Collection')

    def test_library_view_clears_selection_manager_on_deselect(self):
        """Test that LibraryView clears SelectionManager when selection is cleared"""
        from fichero.windows.main.views.library.library_view import LibraryView

        # Create mock widget with no selection
        widget = Mock()
        widget.selection = None

        # Create view
        with patch('fichero.windows.main.views.library.library_view.BaseView.__init__'):
            view = LibraryView.__new__(LibraryView)
            view.app = self.app
            view.on_click = None

            # Call selection handler
            view._on_collection_selected(widget)

            # Verify SelectionManager was cleared
            self.app.selection_manager.clear_selection.assert_called_once_with('library')


class TestCollectionViewSelectionIntegration(unittest.TestCase):
    """Test CollectionView SelectionManager integration"""

    def setUp(self):
        """Set up test fixtures"""
        self.app = Mock()
        self.app.selection_manager = Mock()

    def test_extract_item_data_from_node_with_collection_data(self):
        """Test extracting item data from Node object with _collection_data"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Create mock node with _collection_data (use spec to avoid .selection attribute)
        node = Mock(spec=['_collection_data'])
        node._collection_data = {
            'id': 'item-123',
            'title': 'Test Item',
            'name': 'test.jpg',
            'type': 'image',
            'is_folder': False,
            'path': 'folder/test.jpg',
            'file_path': '/full/path/test.jpg'
        }

        # Create view
        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)

            # Extract data
            data = view._extract_item_data(node)

            self.assertEqual(data['id'], 'item-123')
            self.assertEqual(data['title'], 'Test Item')
            self.assertEqual(data['type'], 'image')
            self.assertFalse(data['is_folder'])

    def test_extract_item_data_from_row_object(self):
        """Test extracting item data from Row object"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Create mock row object (use spec to avoid .selection attribute)
        row = Mock(spec=['id', 'title', 'name', 'type', 'is_folder', 'path', 'file_path'])
        row.id = 'item-456'
        row.title = 'Test Row'
        row.name = 'test_row.pdf'
        row.type = 'document'
        row.is_folder = True
        row.path = 'folder/test_row.pdf'
        row.file_path = '/full/path/test_row.pdf'

        # Create view
        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)

            # Extract data
            data = view._extract_item_data(row)

            self.assertEqual(data['id'], 'item-456')
            self.assertEqual(data['title'], 'Test Row')
            self.assertEqual(data['type'], 'document')
            self.assertTrue(data['is_folder'])

    def test_extract_item_data_from_dict(self):
        """Test extracting item data from dict"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Create dict
        item_dict = {
            'id': 'item-789',
            'title': 'Test Dict',
            'name': 'test_dict.txt',
            'type': 'text',
            'is_folder': False,
            'path': 'test_dict.txt',
            'file_path': '/full/path/test_dict.txt'
        }

        # Create view
        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)

            # Extract data
            data = view._extract_item_data(item_dict)

            self.assertEqual(data['id'], 'item-789')
            self.assertEqual(data['title'], 'Test Dict')
            self.assertEqual(data['type'], 'text')

    def test_collection_view_handles_multi_selection(self):
        """Test that CollectionView extracts ALL item IDs from multi-selection"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Create mock items (use spec to avoid .selection attribute)
        item1 = Mock(spec=['_collection_data'])
        item1._collection_data = {
            'id': 'item-1',
            'title': 'Item 1',
            'name': 'item1.jpg',
            'type': 'image',
            'is_folder': False,
            'path': 'item1.jpg',
            'file_path': '/path/item1.jpg'
        }

        item2 = Mock(spec=['_collection_data'])
        item2._collection_data = {
            'id': 'item-2',
            'title': 'Item 2',
            'name': 'item2.jpg',
            'type': 'image',
            'is_folder': False,
            'path': 'item2.jpg',
            'file_path': '/path/item2.jpg'
        }

        item3 = Mock(spec=['_collection_data'])
        item3._collection_data = {
            'id': 'item-3',
            'title': 'Item 3',
            'name': 'item3.jpg',
            'type': 'image',
            'is_folder': True,
            'path': 'item3',
            'file_path': '/path/item3'
        }

        # Create view
        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)
            view.app = self.app
            view.app.inspector_window = None
            view.app.main_window_wrapper = None
            view.current_path = None  # Add missing attribute

            # Call selection handler with list (multi-selection)
            with patch.object(view, '_update_inspector_async'):
                with patch.object(view, '_load_item_outputs'):
                    view._on_item_selected([item1, item2, item3])

            # Verify SelectionManager was updated with ALL items
            self.app.selection_manager.set_selection.assert_called_once()
            call_args = self.app.selection_manager.set_selection.call_args

            self.assertEqual(call_args[1]['view_id'], 'collection')
            self.assertEqual(call_args[1]['item_ids'], ['item-1', 'item-2', 'item-3'])
            self.assertEqual(len(call_args[1]['metadata']), 3)

            # Verify metadata includes is_folder flag
            self.assertFalse(call_args[1]['metadata'][0]['is_folder'])
            self.assertFalse(call_args[1]['metadata'][1]['is_folder'])
            self.assertTrue(call_args[1]['metadata'][2]['is_folder'])


class TestStepBrowserSelectionIntegration(unittest.TestCase):
    """Test StepBrowser SelectionManager integration"""

    def setUp(self):
        """Set up test fixtures"""
        self.app = Mock()
        self.app.selection_manager = Mock()

    def test_step_browser_accepts_app_parameter(self):
        """Test that StepBrowser accepts and stores app parameter"""
        from fichero.windows.main.views.output.step_browser import StepBrowser

        browser = StepBrowser(app=self.app)

        self.assertEqual(browser.app, self.app)

    def test_step_browser_updates_selection_manager_on_step_select(self):
        """Test that StepBrowser updates SelectionManager when step is selected"""
        from fichero.windows.main.views.output.step_browser import StepBrowser

        # Create browser with app
        browser = StepBrowser(app=self.app)

        # Create mock steps
        step1 = Mock()
        step1.step_name = "Original"
        step1.file_type = "image"
        step1.tool_name = ""

        step2 = Mock()
        step2.step_name = "Transcribe"
        step2.file_type = "text"
        step2.tool_name = "transcribe"

        browser.steps = [step1, step2]

        # Simulate step selection
        widget = Mock()
        kwargs = {
            'selected_data': {
                '_item_id': 1,
                'text': 'Transcribe'
            }
        }

        browser._on_step_selected(widget, **kwargs)

        # Verify SelectionManager was updated
        self.app.selection_manager.set_selection.assert_called_once()
        call_args = self.app.selection_manager.set_selection.call_args

        self.assertEqual(call_args[1]['view_id'], 'steps')
        self.assertEqual(call_args[1]['item_ids'], ['step_1'])
        self.assertEqual(len(call_args[1]['metadata']), 1)
        self.assertEqual(call_args[1]['metadata'][0]['step_name'], 'Transcribe')

    def test_step_browser_clears_selection_manager_on_deselect(self):
        """Test that StepBrowser clears SelectionManager when selection is cleared"""
        from fichero.windows.main.views.output.step_browser import StepBrowser

        # Create browser with app
        browser = StepBrowser(app=self.app)

        # Simulate deselection (no selected_data)
        widget = Mock()
        kwargs = {}

        browser._on_step_selected(widget, **kwargs)

        # Verify SelectionManager was cleared
        self.app.selection_manager.clear_selection.assert_called_once_with('steps')


class TestMetadataStructures(unittest.TestCase):
    """Test metadata structure correctness"""

    def test_library_metadata_has_required_fields(self):
        """Test that library metadata includes all required fields"""
        from fichero.windows.main.views.library.library_view import LibraryView

        app = Mock()
        app.selection_manager = Mock()

        widget = Mock()
        widget.selection = Mock()
        widget.selection.collection_data = {
            'id': 'coll-123',
            'name': 'Test',
            'item_count': 10,
            'type': 'external',
            'source': '/test'
        }

        with patch('fichero.windows.main.views.library.library_view.BaseView.__init__'):
            view = LibraryView.__new__(LibraryView)
            view.app = app
            view.on_click = None
            view.on_collection_selected = None
            view.selected_collection = None

            view._on_collection_selected(widget)

            metadata = app.selection_manager.set_selection.call_args[1]['metadata'][0]

            # Verify required fields
            self.assertIn('collection_id', metadata)
            self.assertIn('collection_name', metadata)
            self.assertIn('item_count', metadata)
            self.assertIn('type', metadata)
            self.assertIn('source', metadata)

    def test_collection_metadata_has_required_fields(self):
        """Test that collection metadata includes all required fields"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        app = Mock()
        app.selection_manager = Mock()
        app.inspector_window = None

        item = Mock(spec=['_collection_data'])
        item._collection_data = {
            'id': 'item-123',
            'title': 'Test',
            'name': 'test.jpg',
            'type': 'image',
            'is_folder': False,
            'path': 'test.jpg',
            'file_path': '/full/test.jpg'
        }

        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)
            view.app = app
            view.app.main_window_wrapper = None
            view.current_path = None  # Add missing attribute

            with patch.object(view, '_update_inspector_async'):
                with patch.object(view, '_load_item_outputs'):
                    view._on_item_selected(item)

            metadata = app.selection_manager.set_selection.call_args[1]['metadata'][0]

            # Verify required fields
            self.assertIn('item_id', metadata)
            self.assertIn('item_name', metadata)
            self.assertIn('is_folder', metadata)
            self.assertIn('type', metadata)
            self.assertIn('file_path', metadata)
            self.assertIn('path', metadata)


if __name__ == '__main__':
    unittest.main()
