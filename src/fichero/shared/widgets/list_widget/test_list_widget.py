"""
Unit tests for ListWidget with all renderers (Native Table/Tree/DetailedList, HTML, Card).

These tests verify:
1. Widget creation and initialization
2. Data format conversion
3. Source attachment and updates
4. Selection handling
5. Hierarchical data (for Tree)
6. Platform detection
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import toga
from toga.sources import ListSource, TreeSource

from fichero.shared.widgets.list_widget import ListWidget, Platform
from fichero.shared.widgets.list_widget.renderers.native import NativeRenderer


class TestNativeRendererTable(unittest.TestCase):
    """Test NativeRenderer with Table widget."""

    def setUp(self):
        """Set up test fixtures."""
        self.headings = ['Collections']
        self.test_data = [
            {
                'icon': None,
                'text': 'Collection 1',
                'subtitle': 'Test subtitle 1',
                '_collection_data': {'id': 'c1'},
                '_item_id': 'item1',
            },
            {
                'icon': None,
                'text': 'Collection 2',
                'subtitle': 'Test subtitle 2',
                '_collection_data': {'id': 'c2'},
                '_item_id': 'item2',
            },
        ]

    def test_table_widget_creation(self):
        """Test that Table widget is created correctly."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='table'
        )

        self.assertIsInstance(widget.widget, toga.Table)
        self.assertIsInstance(widget.renderer, NativeRenderer)
        self.assertEqual(widget.renderer.widget_type, 'table')

    def test_table_data_conversion(self):
        """Test data conversion for Table widget."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='table'
        )

        # Convert data
        source_data = widget.renderer.convert_to_source_format(self.test_data)

        # Verify conversion
        self.assertEqual(len(source_data), 2)
        self.assertEqual(source_data[0]['collections'], 'Collection 1')
        self.assertEqual(source_data[0]['title'], 'Collection 1')
        self.assertEqual(source_data[0]['subtitle'], 'Test subtitle 1')
        self.assertEqual(source_data[0]['_item_id'], 'item1')

    def test_table_accessors(self):
        """Test accessor generation for Table widget."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='table'
        )

        accessors = widget.renderer.get_accessors(self.headings)

        # Should include base accessor + custom fields
        self.assertIn('collections', accessors)  # Lowercase from heading
        self.assertIn('title', accessors)
        self.assertIn('subtitle', accessors)
        self.assertIn('icon', accessors)
        self.assertIn('_collection_data', accessors)
        self.assertIn('_item_id', accessors)

    def test_table_set_data(self):
        """Test setting data on Table widget."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='table'
        )

        # Set data
        widget.set_data(self.test_data)

        # Verify source was created and populated
        self.assertIsNotNone(widget._source)
        self.assertIsInstance(widget._source, ListSource)
        self.assertEqual(len(widget._source), 2)

    def test_table_update_data(self):
        """Test updating data on Table widget."""
        widget = ListWidget(
            headings=self.headings,
            data=self.test_data,
            force_widget_type='table'
        )

        # Initial data
        self.assertEqual(len(widget._source), 2)

        # Update with new data
        new_data = [
            {
                'icon': None,
                'text': 'New Collection',
                'subtitle': 'New subtitle',
                '_collection_data': {'id': 'c3'},
                '_item_id': 'item3',
            }
        ]
        widget.set_data(new_data)

        # Verify update
        self.assertEqual(len(widget._source), 1)

    def test_table_clear_data(self):
        """Test clearing data on Table widget."""
        widget = ListWidget(
            headings=self.headings,
            data=self.test_data,
            force_widget_type='table'
        )

        # Clear
        widget.clear()

        # Verify cleared
        self.assertEqual(len(widget._source), 0)

    def test_table_selection_callback(self):
        """Test selection callback for Table widget."""
        selection_result = []

        def on_select(item):
            selection_result.append(item)

        widget = ListWidget(
            headings=self.headings,
            data=self.test_data,
            on_select=on_select,
            force_widget_type='table'
        )

        # Mock widget with selection
        mock_row = Mock()
        mock_row._item_id = 'item1'
        mock_widget = Mock()
        mock_widget.selection = mock_row

        # Trigger selection handler
        widget._handle_select(mock_widget)

        # Verify callback was called
        self.assertEqual(len(selection_result), 1)
        self.assertEqual(selection_result[0]._item_id, 'item1')


class TestNativeRendererTree(unittest.TestCase):
    """Test NativeRenderer with Tree widget."""

    def setUp(self):
        """Set up test fixtures."""
        self.headings = ['Collections']
        self.flat_data = [
            {
                'icon': None,
                'text': 'Collection 1',
                'subtitle': 'Test subtitle 1',
                '_collection_data': {'id': 'c1'},
                '_item_id': 'item1',
            },
            {
                'icon': None,
                'text': 'Collection 2',
                'subtitle': 'Test subtitle 2',
                '_collection_data': {'id': 'c2'},
                '_item_id': 'item2',
            },
        ]

        self.hierarchical_data = [
            {
                'icon': None,
                'text': 'Parent 1',
                'subtitle': 'Parent subtitle',
                '_collection_data': {'id': 'p1'},
                '_item_id': 'parent1',
                'children': [
                    {
                        'icon': None,
                        'text': 'Child 1',
                        'subtitle': 'Child subtitle',
                        '_collection_data': {'id': 'c1'},
                        '_item_id': 'child1',
                    }
                ]
            },
        ]

    def test_tree_widget_creation(self):
        """Test that Tree widget is created correctly."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='tree'
        )

        self.assertIsInstance(widget.widget, toga.Tree)
        self.assertIsInstance(widget.renderer, NativeRenderer)
        self.assertEqual(widget.renderer.widget_type, 'tree')

    def test_tree_data_conversion_flat(self):
        """Test data conversion for Tree widget with flat data."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='tree'
        )

        # Convert data
        source_data = widget.renderer.convert_to_source_format(self.flat_data)

        # Verify conversion - Tree widgets return tuple format: (data_dict, children)
        self.assertEqual(len(source_data), 2)
        # First item is a tuple (data_dict, None) for flat data
        self.assertIsInstance(source_data[0], tuple)
        self.assertEqual(source_data[0][0]['collections'], 'Collection 1')
        self.assertIsNone(source_data[0][1])  # No children

    def test_tree_data_conversion_hierarchical(self):
        """Test data conversion for Tree widget with hierarchical data."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='tree'
        )

        # Convert data
        source_data = widget.renderer.convert_to_source_format(self.hierarchical_data)

        # Verify conversion - Tree widgets return tuple format: (data_dict, children_list)
        self.assertEqual(len(source_data), 1)
        # Parent item is a tuple (data_dict, children_list)
        self.assertIsInstance(source_data[0], tuple)
        self.assertEqual(source_data[0][0]['collections'], 'Parent 1')
        # Check children exist
        children = source_data[0][1]
        self.assertIsNotNone(children)
        self.assertEqual(len(children), 1)
        # Child is also a tuple (data_dict, None)
        self.assertEqual(children[0][0]['collections'], 'Child 1')

    def test_tree_accessors(self):
        """Test accessor generation for Tree widget."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='tree'
        )

        accessors = widget.renderer.get_accessors(self.headings)

        # Should include base accessor + custom fields
        self.assertIn('collections', accessors)
        self.assertIn('title', accessors)
        self.assertIn('subtitle', accessors)
        self.assertIn('icon', accessors)
        self.assertIn('_collection_data', accessors)
        self.assertIn('_item_id', accessors)

    def test_tree_set_data(self):
        """Test setting data on Tree widget."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='tree'
        )

        # Set data
        widget.set_data(self.flat_data)

        # Verify source was created - Tree widgets use TreeSource
        self.assertIsNotNone(widget._source)
        self.assertIsInstance(widget._source, TreeSource)
        self.assertEqual(len(widget._source), 2)


class TestNativeRendererDetailedList(unittest.TestCase):
    """Test NativeRenderer with DetailedList widget."""

    def setUp(self):
        """Set up test fixtures."""
        self.headings = ['Collections']
        self.test_data = [
            {
                'icon': None,
                'text': 'Collection 1',
                'subtitle': 'Test subtitle 1',
                '_collection_data': {'id': 'c1'},
                '_item_id': 'item1',
            },
            {
                'icon': None,
                'text': 'Collection 2',
                'subtitle': 'Test subtitle 2',
                '_collection_data': {'id': 'c2'},
                '_item_id': 'item2',
            },
        ]

    def test_detailedlist_widget_creation(self):
        """Test that DetailedList widget is created correctly."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='detailedlist'
        )

        self.assertIsInstance(widget.widget, toga.DetailedList)
        self.assertIsInstance(widget.renderer, NativeRenderer)
        self.assertEqual(widget.renderer.widget_type, 'detailedlist')

    def test_detailedlist_data_conversion(self):
        """Test data conversion for DetailedList widget."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='detailedlist'
        )

        # Convert data
        source_data = widget.renderer.convert_to_source_format(self.test_data)

        # Verify conversion - DetailedList requires 'title' and 'subtitle'
        self.assertEqual(len(source_data), 2)
        self.assertEqual(source_data[0]['title'], 'Collection 1')
        self.assertEqual(source_data[0]['subtitle'], 'Test subtitle 1')
        self.assertEqual(source_data[0]['_item_id'], 'item1')

    def test_detailedlist_accessors(self):
        """Test accessor generation for DetailedList widget."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='detailedlist'
        )

        accessors = widget.renderer.get_accessors(self.headings)

        # DetailedList requires 'title', 'subtitle', 'icon'
        self.assertIn('title', accessors)
        self.assertIn('subtitle', accessors)
        self.assertIn('icon', accessors)
        self.assertIn('_collection_data', accessors)
        self.assertIn('_item_id', accessors)

    def test_detailedlist_set_data(self):
        """Test setting data on DetailedList widget."""
        widget = ListWidget(
            headings=self.headings,
            force_widget_type='detailedlist'
        )

        # Set data
        widget.set_data(self.test_data)

        # Verify source was created and populated
        self.assertIsNotNone(widget._source)
        self.assertIsInstance(widget._source, ListSource)
        self.assertEqual(len(widget._source), 2)

    def test_detailedlist_empty_subtitle(self):
        """Test DetailedList with missing subtitle."""
        data_no_subtitle = [
            {
                'icon': None,
                'text': 'Collection 1',
                # No subtitle provided
                '_collection_data': {'id': 'c1'},
                '_item_id': 'item1',
            }
        ]

        widget = ListWidget(
            headings=self.headings,
            force_widget_type='detailedlist'
        )

        # Convert data
        source_data = widget.renderer.convert_to_source_format(data_no_subtitle)

        # Should have empty subtitle
        self.assertEqual(source_data[0]['subtitle'], '')


class TestPlatformDetection(unittest.TestCase):
    """Test platform detection logic."""

    @patch('sys.platform', 'darwin')
    def test_detect_macos(self):
        """Test macOS platform detection."""
        widget = ListWidget(headings=['Test'])
        self.assertEqual(widget.platform, Platform.MACOS)

    @patch('sys.platform', 'linux')
    def test_detect_linux(self):
        """Test Linux platform detection."""
        widget = ListWidget(headings=['Test'])
        self.assertEqual(widget.platform, Platform.LINUX)

    @patch('sys.platform', 'win32')
    def test_detect_windows(self):
        """Test Windows platform detection."""
        widget = ListWidget(headings=['Test'])
        self.assertEqual(widget.platform, Platform.WINDOWS)

    @patch.dict('os.environ', {'FORCE_MOBILE_UI': 'true'})
    @patch('sys.platform', 'darwin')
    def test_force_mobile_ui_ios(self):
        """Test forcing mobile UI on macOS."""
        widget = ListWidget(headings=['Test'])
        self.assertEqual(widget.platform, Platform.IOS)


class TestWidgetSelection(unittest.TestCase):
    """Test automatic widget selection based on platform."""

    @patch('sys.platform', 'darwin')
    def test_desktop_selects_table(self):
        """Test that desktop platforms select Table by default."""
        widget = ListWidget(headings=['Test'])
        self.assertIsInstance(widget.widget, toga.Table)

    @patch.dict('os.environ', {'FORCE_MOBILE_UI': 'true'})
    @patch('sys.platform', 'darwin')
    def test_mobile_selects_detailedlist(self):
        """Test that mobile platforms select DetailedList."""
        widget = ListWidget(headings=['Test'])
        self.assertIsInstance(widget.widget, toga.DetailedList)

    def test_force_widget_type_override(self):
        """Test that force_widget_type overrides platform detection."""
        # Force Tree on desktop
        widget = ListWidget(headings=['Test'], force_widget_type='tree')
        self.assertIsInstance(widget.widget, toga.Tree)


if __name__ == '__main__':
    unittest.main()
