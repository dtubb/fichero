"""
Unit tests for ListWidget hierarchical data conversion.

Tests the flat-to-tree conversion and TreeSource format generation
for navigable list widgets with Tree renderer.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys

from src.fichero.shared.widgets.list_widget import ListWidget


class TestFlatToTreeConversion(unittest.TestCase):
    """Test conversion from flat path-based data to hierarchical tree structure."""

    def test_empty_data(self):
        """Test conversion of empty data."""
        widget = ListWidget(headings=['Items'], renderer='tree')
        result = widget._convert_flat_to_tree([])
        self.assertEqual(result, [])

    def test_single_root_item(self):
        """Test conversion of single root item."""
        data = [
            {'text': 'Root', 'path': 'Root', 'is_folder': True}
        ]
        widget = ListWidget(headings=['Items'], renderer='tree')
        result = widget._convert_flat_to_tree(data)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], 'Root')
        self.assertNotIn('children', result[0])  # No children, so key is removed

    def test_flat_list_no_hierarchy(self):
        """Test conversion of flat list with no hierarchy."""
        data = [
            {'text': 'Item1', 'path': 'Item1', 'is_folder': False},
            {'text': 'Item2', 'path': 'Item2', 'is_folder': False},
            {'text': 'Item3', 'path': 'Item3', 'is_folder': False},
        ]
        widget = ListWidget(headings=['Items'], renderer='tree')
        result = widget._convert_flat_to_tree(data)

        self.assertEqual(len(result), 3)
        for item in result:
            self.assertNotIn('children', item)

    def test_one_level_hierarchy(self):
        """Test conversion of one-level hierarchy."""
        data = [
            {'text': 'Folder1', 'path': 'Folder1', 'is_folder': True},
            {'text': 'File1', 'path': 'Folder1/File1', 'is_folder': False},
            {'text': 'File2', 'path': 'Folder1/File2', 'is_folder': False},
        ]
        widget = ListWidget(headings=['Items'], renderer='tree')
        result = widget._convert_flat_to_tree(data)

        # Should have 1 root item (Folder1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], 'Folder1')

        # Folder1 should have 2 children
        self.assertIn('children', result[0])
        self.assertEqual(len(result[0]['children']), 2)
        self.assertEqual(result[0]['children'][0]['text'], 'File1')
        self.assertEqual(result[0]['children'][1]['text'], 'File2')

    def test_two_level_hierarchy(self):
        """Test conversion of two-level hierarchy."""
        data = [
            {'text': 'Folder1', 'path': 'Folder1', 'is_folder': True},
            {'text': 'Folder2', 'path': 'Folder1/Folder2', 'is_folder': True},
            {'text': 'File1', 'path': 'Folder1/Folder2/File1', 'is_folder': False},
        ]
        widget = ListWidget(headings=['Items'], renderer='tree')
        result = widget._convert_flat_to_tree(data)

        # Should have 1 root
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], 'Folder1')

        # Folder1 has 1 child (Folder2)
        self.assertEqual(len(result[0]['children']), 1)
        folder2 = result[0]['children'][0]
        self.assertEqual(folder2['text'], 'Folder2')

        # Folder2 has 1 child (File1)
        self.assertEqual(len(folder2['children']), 1)
        self.assertEqual(folder2['children'][0]['text'], 'File1')

    def test_multiple_roots(self):
        """Test conversion with multiple root items."""
        data = [
            {'text': 'Root1', 'path': 'Root1', 'is_folder': True},
            {'text': 'Child1', 'path': 'Root1/Child1', 'is_folder': False},
            {'text': 'Root2', 'path': 'Root2', 'is_folder': True},
            {'text': 'Child2', 'path': 'Root2/Child2', 'is_folder': False},
        ]
        widget = ListWidget(headings=['Items'], renderer='tree')
        result = widget._convert_flat_to_tree(data)

        # Should have 2 roots
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['text'], 'Root1')
        self.assertEqual(result[1]['text'], 'Root2')

        # Each root has 1 child
        self.assertEqual(len(result[0]['children']), 1)
        self.assertEqual(len(result[1]['children']), 1)

    def test_empty_path_treated_as_root(self):
        """Test that items with empty path are treated as root."""
        data = [
            {'text': 'EmptyPath', 'path': '', 'is_folder': True},
            {'text': 'NoPath', 'is_folder': False},  # Missing path key
        ]
        widget = ListWidget(headings=['Items'], renderer='tree')
        result = widget._convert_flat_to_tree(data)

        # Empty paths are deduplicated to single root item
        # Both items have path='', so they map to same key
        self.assertGreaterEqual(len(result), 1)

    def test_orphan_items(self):
        """Test that items with missing parents are treated as root."""
        data = [
            {'text': 'File1', 'path': 'MissingFolder/File1', 'is_folder': False},
        ]
        widget = ListWidget(headings=['Items'], renderer='tree')
        result = widget._convert_flat_to_tree(data)

        # Orphan should become root
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], 'File1')

    def test_preserves_metadata(self):
        """Test that conversion preserves item metadata."""
        data = [
            {
                'text': 'Folder1',
                'path': 'Folder1',
                'is_folder': True,
                'icon': 'folder_icon',
                '_item_id': '123',
                '_item_data': {'custom': 'value'}
            },
        ]
        widget = ListWidget(headings=['Items'], renderer='tree')
        result = widget._convert_flat_to_tree(data)

        # All metadata should be preserved
        self.assertEqual(result[0]['icon'], 'folder_icon')
        self.assertEqual(result[0]['_item_id'], '123')
        self.assertEqual(result[0]['_item_data']['custom'], 'value')


class TestTreeSourceConversion(unittest.TestCase):
    """Test conversion from hierarchical data to TreeSource tuple format."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock toga to avoid import errors
        self.toga_mock = MagicMock()
        sys.modules['toga'] = self.toga_mock
        sys.modules['toga.sources'] = MagicMock()
        sys.modules['toga.style'] = MagicMock()
        sys.modules['toga.style.pack'] = MagicMock()

    def test_leaf_node_conversion(self):
        """Test conversion of leaf node (no children)."""
        from src.fichero.shared.widgets.list_widget.renderers.native import NativeRenderer

        renderer = NativeRenderer(
            headings=['Items'],
            widget_type='tree',
            platform='macos'
        )

        data = [
            {'text': 'Leaf', 'icon': None, '_item_id': '1'}
        ]

        result = renderer.convert_to_source_format(data)

        # Should be list of tuples: [(node_data, None)]
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

        node_data, children = result[0]
        self.assertIsInstance(node_data, dict)
        self.assertEqual(node_data['items'], 'Leaf')  # accessor is lowercase heading
        self.assertIsNone(children)

    def test_parent_with_children_conversion(self):
        """Test conversion of parent node with children."""
        from src.fichero.shared.widgets.list_widget.renderers.native import NativeRenderer

        renderer = NativeRenderer(
            headings=['Items'],
            widget_type='tree',
            platform='macos'
        )

        data = [
            {
                'text': 'Parent',
                'icon': None,
                '_item_id': '1',
                'children': [
                    {'text': 'Child1', 'icon': None, '_item_id': '2'},
                    {'text': 'Child2', 'icon': None, '_item_id': '3'},
                ]
            }
        ]

        result = renderer.convert_to_source_format(data)

        # Root should have children
        parent_data, children = result[0]
        self.assertEqual(parent_data['items'], 'Parent')
        self.assertIsNotNone(children)
        self.assertEqual(len(children), 2)

        # Check children format
        child1_data, child1_children = children[0]
        self.assertEqual(child1_data['items'], 'Child1')
        self.assertIsNone(child1_children)

    def test_nested_hierarchy_conversion(self):
        """Test conversion of deeply nested hierarchy."""
        from src.fichero.shared.widgets.list_widget.renderers.native import NativeRenderer

        renderer = NativeRenderer(
            headings=['Items'],
            widget_type='tree',
            platform='macos'
        )

        data = [
            {
                'text': 'Level1',
                'children': [
                    {
                        'text': 'Level2',
                        'children': [
                            {'text': 'Level3'}
                        ]
                    }
                ]
            }
        ]

        result = renderer.convert_to_source_format(data)

        # Navigate down the hierarchy
        level1_data, level1_children = result[0]
        self.assertEqual(level1_data['items'], 'Level1')

        level2_data, level2_children = level1_children[0]
        self.assertEqual(level2_data['items'], 'Level2')

        level3_data, level3_children = level2_children[0]
        self.assertEqual(level3_data['items'], 'Level3')
        self.assertIsNone(level3_children)


class TestTableDetailedListConversion(unittest.TestCase):
    """Test conversion for Table and DetailedList (flat renderers)."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock toga
        self.toga_mock = MagicMock()
        sys.modules['toga'] = self.toga_mock
        sys.modules['toga.sources'] = MagicMock()
        sys.modules['toga.style'] = MagicMock()
        sys.modules['toga.style.pack'] = MagicMock()

    def test_table_conversion_flat_list(self):
        """Test Table renderer converts to flat list of dicts."""
        from src.fichero.shared.widgets.list_widget.renderers.native import NativeRenderer

        renderer = NativeRenderer(
            headings=['Items'],
            widget_type='table',
            platform='macos'
        )

        data = [
            {'text': 'Item1', 'icon': None},
            {'text': 'Item2', 'icon': None},
        ]

        result = renderer.convert_to_source_format(data)

        # Should be list of dicts (not tuples)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], dict)
        self.assertEqual(result[0]['items'], 'Item1')

    def test_detailedlist_conversion(self):
        """Test DetailedList renderer includes title/subtitle."""
        from src.fichero.shared.widgets.list_widget.renderers.native import NativeRenderer

        renderer = NativeRenderer(
            headings=['Items'],
            widget_type='detailedlist',
            platform='ios'
        )

        data = [
            {'text': 'Item1', 'subtitle': 'Subtitle1', 'icon': None},
        ]

        result = renderer.convert_to_source_format(data)

        # Should have title and subtitle
        self.assertIsInstance(result[0], dict)
        self.assertEqual(result[0]['title'], 'Item1')
        self.assertEqual(result[0]['subtitle'], 'Subtitle1')


class TestNavigableListWidget(unittest.TestCase):
    """Test navigable ListWidget behavior."""

    def test_navigable_filters_initial_data(self):
        """Test that navigable=True filters data initially."""
        data = [
            {'text': 'Root', 'path': 'Root', 'is_folder': True},
            {'text': 'Child', 'path': 'Root/Child', 'is_folder': False},
        ]

        widget = ListWidget(
            headings=['Items'],
            data=data,
            navigable=True,
            renderer='native'
        )

        # Should only show root level items initially
        self.assertEqual(len(widget._data), 1)
        self.assertEqual(widget._data[0]['text'], 'Root')


if __name__ == '__main__':
    unittest.main()
