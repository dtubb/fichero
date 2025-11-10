"""
Unit tests for AbstractTreeList widget.

Tests platform detection and data conversion for Tree/Table/DetailedList widgets.
"""

import unittest
from unittest.mock import Mock, patch
import sys

from src.fichero.shared.widgets import AbstractTreeList, Platform


class TestAbstractTreeList(unittest.TestCase):
    """Test AbstractTreeList platform detection and data handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_data = [
            {
                'icon': None,
                'text': 'Item 1',
                'children': [
                    {'icon': None, 'text': 'Child 1.1'},
                    {'icon': None, 'text': 'Child 1.2'},
                ]
            },
            {
                'icon': None,
                'text': 'Item 2',
            }
        ]

    @patch('sys.platform', 'darwin')
    def test_platform_detection_macos(self):
        """Test that macOS is correctly detected."""
        tree_list = AbstractTreeList(headings=['Name'])
        self.assertEqual(tree_list.platform, Platform.MACOS)

    @patch('sys.platform', 'win32')
    def test_platform_detection_windows(self):
        """Test that Windows is correctly detected."""
        tree_list = AbstractTreeList(headings=['Name'])
        self.assertEqual(tree_list.platform, Platform.WINDOWS)

    @patch('sys.platform', 'linux')
    def test_platform_detection_linux(self):
        """Test that Linux is correctly detected."""
        tree_list = AbstractTreeList(headings=['Name'])
        self.assertEqual(tree_list.platform, Platform.LINUX)

    def test_tree_data_conversion(self):
        """Test conversion to Tree format."""
        tree_list = AbstractTreeList(headings=['Name'])
        converted = tree_list._convert_to_tree_data(self.sample_data)

        # Check structure (Toga Tree uses tuple format: (data_dict, children_list))
        self.assertEqual(len(converted), 2)

        # First item should have data dict and children
        item1_data, item1_children = converted[0]
        self.assertEqual(item1_data['text'], 'Item 1')
        self.assertEqual(len(item1_children), 2)

        # Check first child
        child1_data, child1_children = item1_children[0]
        self.assertEqual(child1_data['text'], 'Child 1.1')

        # Second item has no children
        item2_data, item2_children = converted[1]
        self.assertEqual(item2_data['text'], 'Item 2')
        self.assertEqual(len(item2_children), 0)

    def test_table_data_flattening(self):
        """Test flattening hierarchical data for Table widget."""
        tree_list = AbstractTreeList(headings=['Name'])
        flattened = tree_list._flatten_tree_data(self.sample_data)

        # Check that hierarchy is flattened with indentation
        self.assertEqual(len(flattened), 4)  # 2 parents + 2 children
        self.assertEqual(flattened[0]['text'], 'Item 1')  # No indent
        self.assertEqual(flattened[1]['text'], '  Child 1.1')  # Indented
        self.assertEqual(flattened[2]['text'], '  Child 1.2')  # Indented
        self.assertEqual(flattened[3]['text'], 'Item 2')  # No indent

    def test_detailed_list_conversion(self):
        """Test conversion to DetailedList format."""
        tree_list = AbstractTreeList(headings=['Name'])
        converted = tree_list._convert_to_detailed_list_data(self.sample_data)

        # Check structure (children ignored for mobile)
        self.assertEqual(len(converted), 2)
        self.assertEqual(converted[0]['title'], 'Item 1')
        self.assertEqual(converted[1]['title'], 'Item 2')

    def test_set_data(self):
        """Test setting data updates the widget."""
        tree_list = AbstractTreeList(headings=['Name'])

        # Set new data
        new_data = [{'icon': None, 'text': 'New Item'}]
        tree_list.set_data(new_data)

        # Verify internal data is updated
        self.assertEqual(tree_list._data, new_data)

    def test_clear(self):
        """Test clearing data."""
        tree_list = AbstractTreeList(headings=['Name'], data=self.sample_data)
        tree_list.clear()

        # Verify data is cleared
        self.assertEqual(tree_list._data, [])

    def test_selection_callback(self):
        """Test selection callback is stored."""
        callback = Mock()
        tree_list = AbstractTreeList(headings=['Name'], on_select=callback)

        self.assertEqual(tree_list._on_select, callback)

    def test_activation_callback(self):
        """Test activation callback is stored."""
        callback = Mock()
        tree_list = AbstractTreeList(headings=['Name'], on_activate=callback)

        self.assertEqual(tree_list._on_activate, callback)

    def test_multiple_select_flag(self):
        """Test multiple select flag is respected."""
        tree_list = AbstractTreeList(headings=['Name'], multiple_select=True)

        self.assertTrue(tree_list.multiple_select)


if __name__ == '__main__':
    unittest.main()
