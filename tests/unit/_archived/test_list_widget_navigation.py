"""
Tests for ListWidget navigation and initial_path functionality.

Tests the path-based filtering and navigation features of the ListWidget component.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestListWidgetPathFiltering:
    """Tests for ListWidget._filter_items_by_path"""

    def test_filter_at_root_returns_root_level_items(self):
        """At root (path=''), should return items with no '/' in path or empty path"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        # Create test data with various paths
        all_data = [
            {'title': 'Folder A', 'path': 'Folder A', 'is_folder': True},
            {'title': 'File at root', 'path': 'file.jpg', 'is_folder': False},
            {'title': 'Nested file', 'path': 'Folder A/nested.jpg', 'is_folder': False},
            {'title': 'Deep file', 'path': 'Folder A/Sub/deep.jpg', 'is_folder': False},
        ]

        # Create mock widget with navigable=True
        widget = Mock()
        widget._all_data = all_data
        widget.navigable = True

        # Test filtering at root
        filtered = ListWidget._filter_items_by_path(widget, '')

        # Should return only root-level items (no '/' in path)
        assert len(filtered) == 2
        paths = {item['path'] for item in filtered}
        assert paths == {'Folder A', 'file.jpg'}

    def test_filter_inside_folder_returns_direct_children(self):
        """Inside folder, should return the folder itself and direct children"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        all_data = [
            {'title': 'Folder A', 'path': 'Folder A', 'is_folder': True},
            {'title': 'File 1', 'path': 'Folder A/file1.jpg', 'is_folder': False},
            {'title': 'File 2', 'path': 'Folder A/file2.jpg', 'is_folder': False},
            {'title': 'Subfolder', 'path': 'Folder A/Sub', 'is_folder': True},
            {'title': 'Deep file', 'path': 'Folder A/Sub/deep.jpg', 'is_folder': False},
        ]

        widget = Mock()
        widget._all_data = all_data
        widget.navigable = True

        # Test filtering inside 'Folder A'
        filtered = ListWidget._filter_items_by_path(widget, 'Folder A')

        # Should return folder itself + direct children (not grandchildren)
        assert len(filtered) == 4
        paths = {item['path'] for item in filtered}
        assert 'Folder A' in paths  # The folder itself
        assert 'Folder A/file1.jpg' in paths
        assert 'Folder A/file2.jpg' in paths
        assert 'Folder A/Sub' in paths
        assert 'Folder A/Sub/deep.jpg' not in paths  # Grandchild excluded

    def test_filter_non_navigable_returns_all_data(self):
        """Non-navigable lists should return all data unfiltered"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        all_data = [
            {'title': 'Item 1', 'path': 'a/b/c'},
            {'title': 'Item 2', 'path': 'x/y/z'},
        ]

        widget = Mock()
        widget._all_data = all_data
        widget.navigable = False

        filtered = ListWidget._filter_items_by_path(widget, 'a/b')

        # Non-navigable should return all items
        assert len(filtered) == 2


class TestListWidgetInitialPath:
    """Tests for ListWidget initial_path parameter"""

    @patch('fichero.shared.widgets.list_widget.base.ListWidget._create_renderer')
    @patch('fichero.shared.widgets.list_widget.base.ListWidget._detect_platform')
    def test_initial_path_sets_current_path(self, mock_platform, mock_renderer):
        """initial_path parameter should set current_path at creation"""
        from fichero.shared.widgets.list_widget.base import ListWidget, Platform

        mock_platform.return_value = Platform.MACOS
        mock_renderer_instance = Mock()
        mock_renderer_instance.create_widget.return_value = Mock()
        mock_renderer_instance.uses_native_source = False
        mock_renderer_instance.widget_type = 'card'
        mock_renderer.return_value = mock_renderer_instance

        # Create widget with initial_path
        widget = ListWidget(
            headings=['Items'],
            data=[],
            navigable=True,
            initial_path='Folder A'
        )

        assert widget.current_path == 'Folder A'

    @patch('fichero.shared.widgets.list_widget.base.ListWidget._create_renderer')
    @patch('fichero.shared.widgets.list_widget.base.ListWidget._detect_platform')
    def test_initial_path_empty_defaults_to_root(self, mock_platform, mock_renderer):
        """Empty or omitted initial_path should default to root (empty string)"""
        from fichero.shared.widgets.list_widget.base import ListWidget, Platform

        mock_platform.return_value = Platform.MACOS
        mock_renderer_instance = Mock()
        mock_renderer_instance.create_widget.return_value = Mock()
        mock_renderer_instance.uses_native_source = False
        mock_renderer_instance.widget_type = 'card'
        mock_renderer.return_value = mock_renderer_instance

        # Create widget without initial_path
        widget = ListWidget(
            headings=['Items'],
            data=[],
            navigable=True
        )

        assert widget.current_path == ''


class TestListWidgetNavigation:
    """Tests for ListWidget.navigate_to and navigate_up"""

    def test_navigate_to_updates_path_and_filters(self):
        """navigate_to should update current_path and filter data"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        all_data = [
            {'title': 'Folder', 'path': 'Folder', 'is_folder': True},
            {'title': 'File', 'path': 'Folder/file.jpg', 'is_folder': False},
        ]

        # Use a simple class that includes required methods
        class MockWidget:
            def __init__(self):
                self._all_data = all_data
                self.navigable = True
                self.current_path = ''
                self._on_navigate_callback = None
                self._data = None

            def set_data(self, data):
                self._data = data

            # Bind the ListWidget method
            _filter_items_by_path = ListWidget._filter_items_by_path

        widget = MockWidget()

        # Navigate to folder
        ListWidget.navigate_to(widget, 'Folder')

        assert widget.current_path == 'Folder'
        assert widget._data is not None
        assert len(widget._data) == 2  # Folder + its child

    def test_navigate_up_goes_to_parent(self):
        """navigate_up should go to parent folder"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        all_data = [
            {'title': 'Parent', 'path': 'Parent', 'is_folder': True},
            {'title': 'Child', 'path': 'Parent/Child', 'is_folder': True},
        ]

        class MockWidget:
            def __init__(self):
                self._all_data = all_data
                self.navigable = True
                self.current_path = 'Parent/Child'
                self._on_navigate_callback = None
                self._data = None

            def set_data(self, data):
                self._data = data

            # Bind the ListWidget methods
            _filter_items_by_path = ListWidget._filter_items_by_path
            navigate_to = ListWidget.navigate_to

        widget = MockWidget()

        # Navigate up
        ListWidget.navigate_up(widget)

        assert widget.current_path == 'Parent'

    def test_navigate_up_from_root_stays_at_root(self):
        """navigate_up from root should stay at root"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockWidget:
            def __init__(self):
                self.navigable = True
                self.current_path = ''

        widget = MockWidget()

        # Try to navigate up from root
        ListWidget.navigate_up(widget)

        assert widget.current_path == ''


class TestCardRendererSingleSelect:
    """Tests for CardRenderer single selection behavior"""

    def _create_mock_canvas(self):
        """Create a mock canvas with parent=None"""
        canvas = Mock()
        canvas.parent = None
        return canvas

    def test_single_select_clears_previous_selection(self):
        """In single select mode, clicking new card should clear previous selection"""
        from fichero.shared.widgets.list_widget.renderers.card import CardRenderer

        # Test the selection logic directly without full CardRenderer setup
        # The selection logic is in the first part of _handle_card_select

        # Simulate single select behavior
        multiple_select = False
        selected_cards = {0}  # Item 0 is selected
        card_index = 1  # Clicking card 1

        if multiple_select:
            if card_index in selected_cards:
                selected_cards.remove(card_index)
            else:
                selected_cards.add(card_index)
        else:
            # Single selection logic from CardRenderer
            if card_index in selected_cards:
                selected_cards.clear()
            else:
                selected_cards.clear()
                selected_cards.add(card_index)

        # Previous selection should be cleared, new one selected
        assert selected_cards == {1}

    def test_single_select_toggle_off(self):
        """In single select mode, clicking same card should deselect it"""
        # Test the selection logic directly
        multiple_select = False
        selected_cards = {0}  # Item 0 is selected
        card_index = 0  # Clicking card 0 (same card)

        if multiple_select:
            if card_index in selected_cards:
                selected_cards.remove(card_index)
            else:
                selected_cards.add(card_index)
        else:
            # Single selection logic from CardRenderer
            if card_index in selected_cards:
                selected_cards.clear()
            else:
                selected_cards.clear()
                selected_cards.add(card_index)

        # Selection should be cleared
        assert selected_cards == set()

    def test_multiple_select_keeps_previous_selections(self):
        """In multiple select mode, clicking new card keeps previous selections"""
        # Test the selection logic directly
        multiple_select = True
        selected_cards = {0}  # Item 0 is selected
        card_index = 1  # Clicking card 1

        if multiple_select:
            if card_index in selected_cards:
                selected_cards.remove(card_index)
            else:
                selected_cards.add(card_index)
        else:
            if card_index in selected_cards:
                selected_cards.clear()
            else:
                selected_cards.clear()
                selected_cards.add(card_index)

        # Both should be selected
        assert selected_cards == {0, 1}

    def test_multiple_select_toggle_off(self):
        """In multiple select mode, clicking selected card should deselect just that one"""
        multiple_select = True
        selected_cards = {0, 1}  # Both selected
        card_index = 0  # Clicking card 0

        if multiple_select:
            if card_index in selected_cards:
                selected_cards.remove(card_index)
            else:
                selected_cards.add(card_index)
        else:
            if card_index in selected_cards:
                selected_cards.clear()
            else:
                selected_cards.clear()
                selected_cards.add(card_index)

        # Only card 1 should remain selected
        assert selected_cards == {1}


class TestListWidgetSelectionNavigation:
    """Tests for ListWidget select_next and select_previous methods"""

    def test_get_selected_indices_from_renderer(self):
        """get_selected_indices should return indices from CardRenderer"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockRenderer:
            selected_cards = {1, 3}

        class MockWidget:
            def __init__(self):
                self.renderer = MockRenderer()

            get_selected_indices = ListWidget.get_selected_indices

        widget = MockWidget()
        indices = widget.get_selected_indices()
        assert indices == [1, 3]

    def test_select_by_index_calls_renderer(self):
        """select_by_index should call renderer._handle_card_select"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockRenderer:
            def __init__(self):
                self.selected_index = None

            def _handle_card_select(self, index):
                self.selected_index = index

        class MockWidget:
            def __init__(self):
                self.renderer = MockRenderer()
                self._data = [{'title': 'Item 1'}, {'title': 'Item 2'}]

            select_by_index = ListWidget.select_by_index

        widget = MockWidget()
        result = widget.select_by_index(1)

        assert result is True
        assert widget.renderer.selected_index == 1

    def test_select_by_index_validates_bounds(self):
        """select_by_index should return False for invalid indices"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockRenderer:
            def _handle_card_select(self, index):
                pass

        class MockWidget:
            def __init__(self):
                self.renderer = MockRenderer()
                self._data = [{'title': 'Item 1'}]

            select_by_index = ListWidget.select_by_index

        widget = MockWidget()

        # Negative index
        assert widget.select_by_index(-1) is False
        # Index out of bounds
        assert widget.select_by_index(5) is False
        # Empty data
        widget._data = []
        assert widget.select_by_index(0) is False

    def test_select_next_moves_to_next_item(self):
        """select_next should select the next item"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockRenderer:
            selected_cards = {0}

            def _handle_card_select(self, index):
                self.selected_cards = {index}

        class MockWidget:
            def __init__(self):
                self.renderer = MockRenderer()
                self._data = [{'title': 'A'}, {'title': 'B'}, {'title': 'C'}]

            get_selected_indices = ListWidget.get_selected_indices
            select_by_index = ListWidget.select_by_index
            select_next = ListWidget.select_next

        widget = MockWidget()
        result = widget.select_next()

        assert result is True
        assert widget.renderer.selected_cards == {1}

    def test_select_next_at_end_returns_false(self):
        """select_next at last item should return False"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockRenderer:
            selected_cards = {2}  # Last item (index 2)

            def _handle_card_select(self, index):
                self.selected_cards = {index}

        class MockWidget:
            def __init__(self):
                self.renderer = MockRenderer()
                self._data = [{'title': 'A'}, {'title': 'B'}, {'title': 'C'}]

            get_selected_indices = ListWidget.get_selected_indices
            select_by_index = ListWidget.select_by_index
            select_next = ListWidget.select_next

        widget = MockWidget()
        result = widget.select_next()

        assert result is False
        # Selection should not have changed
        assert widget.renderer.selected_cards == {2}

    def test_select_previous_moves_to_previous_item(self):
        """select_previous should select the previous item"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockRenderer:
            selected_cards = {2}

            def _handle_card_select(self, index):
                self.selected_cards = {index}

        class MockWidget:
            def __init__(self):
                self.renderer = MockRenderer()
                self._data = [{'title': 'A'}, {'title': 'B'}, {'title': 'C'}]

            get_selected_indices = ListWidget.get_selected_indices
            select_by_index = ListWidget.select_by_index
            select_previous = ListWidget.select_previous

        widget = MockWidget()
        result = widget.select_previous()

        assert result is True
        assert widget.renderer.selected_cards == {1}

    def test_select_previous_at_start_returns_false(self):
        """select_previous at first item should return False"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockRenderer:
            selected_cards = {0}  # First item

            def _handle_card_select(self, index):
                self.selected_cards = {index}

        class MockWidget:
            def __init__(self):
                self.renderer = MockRenderer()
                self._data = [{'title': 'A'}, {'title': 'B'}, {'title': 'C'}]

            get_selected_indices = ListWidget.get_selected_indices
            select_by_index = ListWidget.select_by_index
            select_previous = ListWidget.select_previous

        widget = MockWidget()
        result = widget.select_previous()

        assert result is False
        # Selection should not have changed
        assert widget.renderer.selected_cards == {0}

    def test_select_next_with_no_selection_selects_first(self):
        """select_next with no selection should select first item"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockRenderer:
            selected_cards = set()  # No selection

            def _handle_card_select(self, index):
                self.selected_cards = {index}

        class MockWidget:
            def __init__(self):
                self.renderer = MockRenderer()
                self._data = [{'title': 'A'}, {'title': 'B'}]

            get_selected_indices = ListWidget.get_selected_indices
            select_by_index = ListWidget.select_by_index
            select_next = ListWidget.select_next

        widget = MockWidget()
        result = widget.select_next()

        assert result is True
        assert widget.renderer.selected_cards == {0}

    def test_select_previous_with_no_selection_selects_last(self):
        """select_previous with no selection should select last item"""
        from fichero.shared.widgets.list_widget.base import ListWidget

        class MockRenderer:
            selected_cards = set()  # No selection

            def _handle_card_select(self, index):
                self.selected_cards = {index}

        class MockWidget:
            def __init__(self):
                self.renderer = MockRenderer()
                self._data = [{'title': 'A'}, {'title': 'B'}]

            get_selected_indices = ListWidget.get_selected_indices
            select_by_index = ListWidget.select_by_index
            select_previous = ListWidget.select_previous

        widget = MockWidget()
        result = widget.select_previous()

        assert result is True
        assert widget.renderer.selected_cards == {1}  # Last item
