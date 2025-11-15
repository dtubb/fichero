"""
Integration tests for Phase 3: Full Selection Flow

Tests the complete flow from user interaction to SelectionManager to StatusBar.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))


class TestPhase3FullFlow(unittest.TestCase):
    """Test complete selection flow through all components"""

    def test_library_to_status_bar_flow(self):
        """Test: User selects collection -> SelectionManager -> StatusBar updates"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.windows.main.views.library.library_view import LibraryView

        # Create real SelectionManager
        selection_manager = SelectionManager()

        # Track events
        events_received = []

        def event_listener(event):
            events_received.append(event)

        # Subscribe to events
        from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
        subscribe_to_navigation("SELECTION_CHANGED", event_listener)

        # Create app mock
        app = Mock()
        app.selection_manager = selection_manager

        # Create mock widget with selection
        widget = Mock()
        widget.selection = Mock()
        widget.selection.collection_data = {
            'id': 'coll-abc',
            'name': 'My Collection',
            'item_count': 50,
            'type': 'external',
            'source': '/test/path'
        }

        # Create view and trigger selection
        with patch('fichero.windows.main.views.library.library_view.BaseView.__init__'):
            view = LibraryView.__new__(LibraryView)
            view.app = app
            view.on_click = None
            view.on_collection_selected = None
            view.selected_collection = None

            view._on_collection_selected(widget)

        # Verify SelectionManager state
        selected_ids = selection_manager.get_selection('library')
        self.assertEqual(selected_ids, ['coll-abc'])
        self.assertEqual(selection_manager.get_selection_count('library'), 1)

        # Get metadata
        metadata = selection_manager.get_selection_metadata('library')
        self.assertEqual(metadata[0]['collection_name'], 'My Collection')

        # Verify event was emitted
        self.assertEqual(len(events_received), 1)
        event = events_received[0]
        self.assertEqual(event.event_type, 'SELECTION_CHANGED')
        self.assertEqual(event.data['view_id'], 'library')
        self.assertEqual(event.data['count'], 1)

    def test_collection_multi_selection_flow(self):
        """Test: User selects 3 items -> SelectionManager has all 3 -> StatusBar shows count"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Create real SelectionManager
        selection_manager = SelectionManager()

        # Track events
        events_received = []

        def event_listener(event):
            events_received.append(event)

        from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
        subscribe_to_navigation("SELECTION_CHANGED", event_listener)

        # Create app mock
        app = Mock()
        app.selection_manager = selection_manager
        app.inspector_window = None
        app.main_window_wrapper = None

        # Create 3 mock items
        items = []
        for i in range(1, 4):
            item = Mock(spec=['_collection_data'])
            item._collection_data = {
                'id': f'item-{i}',
                'title': f'Item {i}',
                'name': f'item{i}.jpg',
                'type': 'image',
                'is_folder': i == 2,  # Item 2 is a folder
                'path': f'item{i}.jpg',
                'file_path': f'/path/item{i}.jpg'
            }
            items.append(item)

        # Create view and trigger multi-selection
        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)
            view.app = app
            view.current_path = None

            with patch.object(view, '_update_inspector_async'):
                with patch.object(view, '_load_item_outputs'):
                    view._on_item_selected(items)

        # Verify SelectionManager has all 3 items
        selected_ids = selection_manager.get_selection('collection')
        self.assertEqual(selection_manager.get_selection_count('collection'), 3)
        self.assertEqual(set(selected_ids), {'item-1', 'item-2', 'item-3'})

        # Verify metadata includes folder flag
        metadata = selection_manager.get_selection_metadata('collection')
        self.assertEqual(len(metadata), 3)
        self.assertFalse(metadata[0]['is_folder'])  # Item 1
        self.assertTrue(metadata[1]['is_folder'])   # Item 2 is folder
        self.assertFalse(metadata[2]['is_folder'])  # Item 3

        # Verify event was emitted with correct count
        self.assertEqual(len(events_received), 1)
        event = events_received[0]
        self.assertEqual(event.data['count'], 3)

    def test_step_browser_selection_flow(self):
        """Test: User selects step -> SelectionManager -> StatusBar shows step info"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.windows.main.views.output.step_browser import StepBrowser

        # Create real SelectionManager
        selection_manager = SelectionManager()

        # Track events
        events_received = []

        def event_listener(event):
            events_received.append(event)

        from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
        subscribe_to_navigation("SELECTION_CHANGED", event_listener)

        # Create app mock
        app = Mock()
        app.selection_manager = selection_manager

        # Create browser with steps
        browser = StepBrowser(app=app)
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

        # Verify SelectionManager state
        selected_ids = selection_manager.get_selection('steps')
        self.assertEqual(selected_ids, ['step_1'])
        self.assertEqual(selection_manager.get_selection_count('steps'), 1)

        metadata = selection_manager.get_selection_metadata('steps')
        self.assertEqual(metadata[0]['step_name'], 'Transcribe')

        # Verify event was emitted
        self.assertEqual(len(events_received), 1)
        event = events_received[0]
        self.assertEqual(event.data['view_id'], 'steps')

    def test_deselection_clears_selection(self):
        """Test: User deselects -> SelectionManager clears -> StatusBar shows total count"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.windows.main.views.library.library_view import LibraryView

        # Create real SelectionManager with existing selection
        selection_manager = SelectionManager()
        selection_manager.set_selection('library', ['coll-1'], [{'collection_name': 'Test'}])

        # Verify initial state
        self.assertEqual(selection_manager.get_selection_count('library'), 1)

        # Track events
        events_received = []

        def event_listener(event):
            events_received.append(event)

        from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
        subscribe_to_navigation("SELECTION_CHANGED", event_listener)

        # Create app mock
        app = Mock()
        app.selection_manager = selection_manager
        app.main_window_wrapper = None

        # Create widget with no selection
        widget = Mock()
        widget.selection = None

        # Create view and trigger deselection
        with patch('fichero.windows.main.views.library.library_view.BaseView.__init__'):
            view = LibraryView.__new__(LibraryView)
            view.app = app
            view.on_click = None

            view._on_collection_selected(widget)

        # Verify SelectionManager is cleared
        selected_ids = selection_manager.get_selection('library')
        self.assertEqual(selection_manager.get_selection_count('library'), 0)
        self.assertEqual(selected_ids, [])

        # Verify event was emitted
        self.assertEqual(len(events_received), 1)
        event = events_received[0]
        self.assertEqual(event.data['count'], 0)


class TestPhase3Regressions(unittest.TestCase):
    """Test that existing functionality still works"""

    def test_inspector_still_updates_with_collection(self):
        """Regression: Inspector should still update when collection is selected"""
        from fichero.windows.main.views.library.library_view import LibraryView

        # Create mocks
        app = Mock()
        app.selection_manager = Mock()
        app.inspector_window = Mock()

        widget = Mock()
        widget.selection = Mock()
        widget.selection.collection_data = {
            'id': 'coll-1',
            'name': 'Test',
            'item_count': 10,
            'type': 'external',
            'source': '/test'
        }

        # Create view and trigger selection
        with patch('fichero.windows.main.views.library.library_view.BaseView.__init__'):
            view = LibraryView.__new__(LibraryView)
            view.app = app
            view.on_click = None
            view.on_collection_selected = None
            view.selected_collection = None

            view._on_collection_selected(widget)

        # Verify inspector was updated (existing behavior)
        app.inspector_window.update_metadata.assert_called_once()
        call_args = app.inspector_window.update_metadata.call_args
        self.assertEqual(call_args[1]['selection_type'], 'COLLECTION')

    def test_inspector_still_updates_with_item(self):
        """Regression: Inspector should still update when item is selected"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Create mocks
        app = Mock()
        app.selection_manager = Mock()
        app.inspector_window = Mock()
        app.main_window_wrapper = None

        item = Mock(spec=['_collection_data'])
        item._collection_data = {
            'id': 'item-1',
            'title': 'Test',
            'name': 'test.jpg',
            'type': 'image',
            'is_folder': False,
            'path': 'test.jpg',
            'file_path': '/full/test.jpg'
        }

        # Create view and trigger selection
        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)
            view.app = app
            view.current_path = None

            with patch.object(view, '_update_inspector_async') as mock_inspector:
                with patch.object(view, '_load_item_outputs'):
                    view._on_item_selected(item)

            # Verify inspector update was called
            mock_inspector.assert_called_once()
            # Get the item_data that was passed
            item_data = mock_inspector.call_args[0][0]
            self.assertEqual(item_data['id'], 'item-1')

    def test_preview_still_loads_for_non_folder_items(self):
        """Regression: Preview should still load when non-folder item is selected"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        # Create mocks
        app = Mock()
        app.selection_manager = Mock()
        app.inspector_window = None
        app.main_window_wrapper = None

        item = Mock(spec=['_collection_data'])
        item._collection_data = {
            'id': 'item-1',
            'title': 'Test',
            'name': 'test.jpg',
            'type': 'image',
            'is_folder': False,
            'path': 'test.jpg',
            'file_path': '/full/test.jpg'
        }

        # Create view and trigger selection
        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)
            view.app = app
            view.current_path = None

            with patch.object(view, '_update_inspector_async'):
                with patch.object(view, '_load_item_outputs') as mock_load:
                    view._on_item_selected(item)

            # Verify preview load was called
            mock_load.assert_called_once()
            # Verify it was called with correct file path
            call_args = mock_load.call_args[0]
            self.assertEqual(call_args[1], '/full/test.jpg')

    def test_navigation_callback_still_fires(self):
        """Regression: Navigation callback should still fire when collection is selected"""
        from fichero.windows.main.views.library.library_view import LibraryView

        # Create mocks
        app = Mock()
        app.selection_manager = Mock()
        app.inspector_window = None

        navigation_callback = Mock()

        widget = Mock()
        widget.selection = Mock()
        widget.selection.collection_data = {
            'id': 'coll-1',
            'name': 'Test',
            'item_count': 10,
            'type': 'external',
            'source': '/test'
        }

        # Create view and trigger selection
        with patch('fichero.windows.main.views.library.library_view.BaseView.__init__'):
            view = LibraryView.__new__(LibraryView)
            view.app = app
            view.on_click = None
            view.on_collection_selected = navigation_callback
            view.selected_collection = None

            view._on_collection_selected(widget)

        # Verify navigation callback was called
        navigation_callback.assert_called_once_with('coll-1', 'Test')


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""

    def test_selection_manager_not_available(self):
        """Test graceful handling when SelectionManager is not available"""
        from fichero.windows.main.views.library.library_view import LibraryView

        # Create app without selection_manager
        app = Mock()
        app.selection_manager = None

        widget = Mock()
        widget.selection = Mock()
        widget.selection.collection_data = {
            'id': 'coll-1',
            'name': 'Test',
            'item_count': 10,
            'type': 'external',
            'source': '/test'
        }

        # Create view and trigger selection
        with patch('fichero.windows.main.views.library.library_view.BaseView.__init__'):
            view = LibraryView.__new__(LibraryView)
            view.app = app
            view.on_click = None
            view.on_collection_selected = None
            view.selected_collection = None

            # Should not raise exception
            try:
                view._on_collection_selected(widget)
            except Exception as e:
                self.fail(f"Should not raise exception when SelectionManager is None: {e}")

    def test_empty_selection_list(self):
        """Test handling of empty selection list"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.windows.main.views.collection.collection_view import CollectionView

        selection_manager = SelectionManager()
        app = Mock()
        app.selection_manager = selection_manager
        app.inspector_window = None
        app.main_window_wrapper = None

        # Create view and trigger selection with empty list
        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)
            view.app = app
            view.current_path = None

            view._on_item_selected([])

        # Verify SelectionManager has empty selection
        self.assertEqual(selection_manager.get_selection_count('collection'), 0)

    def test_item_without_id_is_skipped(self):
        """Test that items without ID are skipped gracefully"""
        from fichero.shared.selection.selection_manager import SelectionManager
        from fichero.windows.main.views.collection.collection_view import CollectionView

        selection_manager = SelectionManager()
        app = Mock()
        app.selection_manager = selection_manager
        app.inspector_window = None
        app.main_window_wrapper = None

        # Create item without ID
        item = Mock(spec=['_collection_data'])
        item._collection_data = {
            'title': 'No ID Item',
            'name': 'no_id.jpg',
            'type': 'image',
            'is_folder': False
        }

        # Create view and trigger selection
        with patch('fichero.windows.main.views.collection.collection_view.BaseView.__init__'):
            view = CollectionView.__new__(CollectionView)
            view.app = app
            view.current_path = None

            with patch.object(view, '_update_inspector_async'):
                view._on_item_selected(item)

        # Verify SelectionManager has no items (ID was missing)
        self.assertEqual(selection_manager.get_selection_count('collection'), 0)


if __name__ == '__main__':
    unittest.main()
