"""
Unit tests for Phase 2: StatusBar selection count integration.

Tests message formatting for library, collection, and steps contexts.
"""

import unittest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))

from fichero.shared.bars.status_bar import StatusBar


class TestStatusBarMessageFormatting(unittest.TestCase):
    """Test StatusBar message formatting methods"""

    def setUp(self):
        """Create StatusBar instance for testing"""
        self.status_bar = StatusBar(platform='desktop')

    def test_pluralize_basic(self):
        """Test basic pluralization"""
        # Zero items
        self.assertEqual(self.status_bar._pluralize(0, "item"), "No items")
        # Single item
        self.assertEqual(self.status_bar._pluralize(1, "item"), "1 item")
        # Multiple items
        self.assertEqual(self.status_bar._pluralize(5, "item"), "5 items")

    def test_pluralize_with_suffix(self):
        """Test pluralization with suffix"""
        self.assertEqual(
            self.status_bar._pluralize(1, "item", suffix=" selected"),
            "1 item selected"
        )
        self.assertEqual(
            self.status_bar._pluralize(3, "item", suffix=" selected"),
            "3 items selected"
        )

    def test_pluralize_custom_plural(self):
        """Test pluralization with custom plural form"""
        # Custom plural (e.g., "children" not "childs")
        self.assertEqual(
            self.status_bar._pluralize(0, "child", plural="children"),
            "No children"
        )
        self.assertEqual(
            self.status_bar._pluralize(1, "child", plural="children"),
            "1 child"
        )
        self.assertEqual(
            self.status_bar._pluralize(2, "child", plural="children"),
            "2 children"
        )

    def test_pluralize_no_prefix(self):
        """Test pluralization without 'No' prefix"""
        self.assertEqual(
            self.status_bar._pluralize(0, "item", no_prefix=True),
            "0 items"
        )

    def test_format_selection_message(self):
        """Test selection message formatting"""
        # Single item selected
        self.assertEqual(
            self.status_bar._format_selection_message(1),
            "1 item selected"
        )
        # Multiple items selected
        self.assertEqual(
            self.status_bar._format_selection_message(3),
            "3 items selected"
        )
        self.assertEqual(
            self.status_bar._format_selection_message(100),
            "100 items selected"
        )

    def test_format_library_status(self):
        """Test library view status formatting"""
        # No collections
        self.assertEqual(
            self.status_bar._format_library_status(0, 0),
            "No collections"
        )
        # Single collection
        self.assertEqual(
            self.status_bar._format_library_status(1, 0),
            "1 collection"
        )
        # Multiple collections
        self.assertEqual(
            self.status_bar._format_library_status(5, 0),
            "5 collections"
        )
        self.assertEqual(
            self.status_bar._format_library_status(127, 0),
            "127 collections"
        )

    def test_format_collection_status_no_folders(self):
        """Test collection view status without folders"""
        # No items
        self.assertEqual(
            self.status_bar._format_collection_status(0, 0, 0, {}),
            "No items"
        )
        # Single item
        self.assertEqual(
            self.status_bar._format_collection_status(1, 0, 0, {}),
            "1 item"
        )
        # Multiple items
        self.assertEqual(
            self.status_bar._format_collection_status(127, 0, 0, {}),
            "127 items"
        )

    def test_format_collection_status_with_folders(self):
        """Test collection view status with folders"""
        # Items and folders
        self.assertEqual(
            self.status_bar._format_collection_status(127, 5, 0, {}),
            "127 items, 5 folders"
        )
        # Single folder
        self.assertEqual(
            self.status_bar._format_collection_status(10, 1, 0, {}),
            "10 items, 1 folder"
        )
        # Only folders (folders count as items too)
        self.assertEqual(
            self.status_bar._format_collection_status(5, 5, 0, {}),
            "5 items, 5 folders"
        )

    def test_format_steps_status(self):
        """Test steps view status formatting"""
        # No steps
        self.assertEqual(
            self.status_bar._format_steps_status(0, 0),
            "No steps"
        )
        # Single step
        self.assertEqual(
            self.status_bar._format_steps_status(1, 0),
            "1 step"
        )
        # Multiple steps
        self.assertEqual(
            self.status_bar._format_steps_status(10, 0),
            "10 steps"
        )

    def test_format_generic_status(self):
        """Test generic status formatting"""
        # No items
        self.assertEqual(
            self.status_bar._format_generic_status(0),
            "No items"
        )
        # Single item
        self.assertEqual(
            self.status_bar._format_generic_status(1),
            "1 item"
        )
        # Multiple items
        self.assertEqual(
            self.status_bar._format_generic_status(25),
            "25 items"
        )

    def test_count_folders_and_items(self):
        """Test folder counting from collection items (dictionaries)"""
        # Empty list
        folder_count, total_count = self.status_bar._count_folders_and_items([])
        self.assertEqual(folder_count, 0)
        self.assertEqual(total_count, 0)

        # List with no folders
        items = [
            {'id': '1', 'name': 'Item 1', 'is_folder': False},
            {'id': '2', 'name': 'Item 2', 'is_folder': False},
        ]
        folder_count, total_count = self.status_bar._count_folders_and_items(items)
        self.assertEqual(folder_count, 0)
        self.assertEqual(total_count, 2)

        # List with folders
        items = [
            {'id': '1', 'name': 'Folder 1', 'is_folder': True},
            {'id': '2', 'name': 'Item 1', 'is_folder': False},
            {'id': '3', 'name': 'Folder 2', 'is_folder': True},
            {'id': '4', 'name': 'Item 2', 'is_folder': False},
            {'id': '5', 'name': 'Item 3', 'is_folder': False},
        ]
        folder_count, total_count = self.status_bar._count_folders_and_items(items)
        self.assertEqual(folder_count, 2)
        self.assertEqual(total_count, 5)

        # List with items missing is_folder key (defaults to False)
        items = [
            {'id': '1', 'name': 'Item 1'},  # No is_folder key
            {'id': '2', 'name': 'Folder 1', 'is_folder': True},
        ]
        folder_count, total_count = self.status_bar._count_folders_and_items(items)
        self.assertEqual(folder_count, 1)
        self.assertEqual(total_count, 2)

    def test_update_status_from_selection_library(self):
        """Test update_status_from_selection for library context"""
        # No selection, 5 collections
        self.status_bar.update_status_from_selection(
            context='library',
            selected_count=0,
            metadata={'total_items': 5}
        )
        self.assertEqual(self.status_bar.status_label.text, "5 collections")

        # 1 collection selected
        self.status_bar.update_status_from_selection(
            context='library',
            selected_count=1,
            metadata={'total_items': 5}
        )
        self.assertEqual(self.status_bar.status_label.text, "1 item selected")

        # Multiple collections selected
        self.status_bar.update_status_from_selection(
            context='library',
            selected_count=3,
            metadata={'total_items': 5}
        )
        self.assertEqual(self.status_bar.status_label.text, "3 items selected")

    def test_update_status_from_selection_collection(self):
        """Test update_status_from_selection for collection context"""
        # No selection, 127 items, no folders
        self.status_bar.update_status_from_selection(
            context='collection',
            selected_count=0,
            metadata={'total_items': 127, 'folder_count': 0}
        )
        self.assertEqual(self.status_bar.status_label.text, "127 items")

        # No selection, items with folders
        self.status_bar.update_status_from_selection(
            context='collection',
            selected_count=0,
            metadata={'total_items': 127, 'folder_count': 5}
        )
        self.assertEqual(self.status_bar.status_label.text, "127 items, 5 folders")

        # Items selected
        self.status_bar.update_status_from_selection(
            context='collection',
            selected_count=3,
            metadata={'total_items': 127, 'folder_count': 5}
        )
        self.assertEqual(self.status_bar.status_label.text, "3 items selected")

    def test_update_status_from_selection_steps(self):
        """Test update_status_from_selection for steps context"""
        # No selection, 10 steps
        self.status_bar.update_status_from_selection(
            context='steps',
            selected_count=0,
            metadata={'total_items': 10}
        )
        self.assertEqual(self.status_bar.status_label.text, "10 steps")

        # 1 step selected
        self.status_bar.update_status_from_selection(
            context='steps',
            selected_count=1,
            metadata={'total_items': 10}
        )
        self.assertEqual(self.status_bar.status_label.text, "1 item selected")

    def test_update_status_from_selection_empty_metadata(self):
        """Test update_status_from_selection with missing metadata"""
        # No metadata provided (should default to 0)
        self.status_bar.update_status_from_selection(
            context='library',
            selected_count=0,
            metadata=None
        )
        self.assertEqual(self.status_bar.status_label.text, "No collections")

        # Empty metadata dict
        self.status_bar.update_status_from_selection(
            context='collection',
            selected_count=0,
            metadata={}
        )
        self.assertEqual(self.status_bar.status_label.text, "No items")

    def test_update_status_from_selection_unknown_context(self):
        """Test update_status_from_selection with unknown context"""
        # Unknown context defaults to generic formatting
        self.status_bar.update_status_from_selection(
            context='unknown',
            selected_count=0,
            metadata={'total_items': 10}
        )
        self.assertEqual(self.status_bar.status_label.text, "10 items")

        # Unknown context with selection
        self.status_bar.update_status_from_selection(
            context='unknown',
            selected_count=3,
            metadata={'total_items': 10}
        )
        self.assertEqual(self.status_bar.status_label.text, "3 items selected")


class TestStatusBarEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""

    def setUp(self):
        """Create StatusBar instance for testing"""
        self.status_bar = StatusBar(platform='desktop')

    def test_zero_items_zero_selection(self):
        """Test empty view with no selection"""
        self.status_bar.update_status_from_selection(
            context='library',
            selected_count=0,
            metadata={'total_items': 0}
        )
        self.assertEqual(self.status_bar.status_label.text, "No collections")

    def test_all_items_selected(self):
        """Test when all items are selected"""
        # All 5 collections selected
        self.status_bar.update_status_from_selection(
            context='library',
            selected_count=5,
            metadata={'total_items': 5}
        )
        # Should show "5 items selected", not "5 collections (5 selected)"
        self.assertEqual(self.status_bar.status_label.text, "5 items selected")

    def test_large_numbers(self):
        """Test with large item counts"""
        self.status_bar.update_status_from_selection(
            context='collection',
            selected_count=0,
            metadata={'total_items': 10000, 'folder_count': 500}
        )
        self.assertEqual(self.status_bar.status_label.text, "10000 items, 500 folders")

        self.status_bar.update_status_from_selection(
            context='collection',
            selected_count=9999,
            metadata={'total_items': 10000, 'folder_count': 500}
        )
        self.assertEqual(self.status_bar.status_label.text, "9999 items selected")


if __name__ == '__main__':
    unittest.main()
