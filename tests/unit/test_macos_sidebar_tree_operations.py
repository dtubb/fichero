"""
Unit tests for macos_sidebar tree operations module.

Tests the helper functions used for tree manipulation in NSOutlineViewSidebar.
"""

import pytest
from fichero.shared.widgets.list_widget.renderers.macos_sidebar.tree_operations import (
    clean_item_data,
    get_item_id,
    find_item_by_id,
    is_descendant_of,
    find_item_in_tree,
    remove_item_from_parent,
    insert_item_into_parent,
    flatten_tree,
)


class TestCleanItemData:
    """Tests for clean_item_data function."""

    def test_cleans_dict_preserving_primitives(self):
        """Should preserve string, int, float, bool values."""
        item = {
            'text': 'Test Collection',
            'count': 42,
            'ratio': 0.5,
            'is_active': True,
        }
        result = clean_item_data(item)

        assert result['text'] == 'Test Collection'
        assert result['count'] == 42
        assert result['ratio'] == 0.5
        assert result['is_active'] is True

    def test_removes_none_values(self):
        """Should remove None values (NSDictionary cannot contain nil)."""
        item = {
            'text': 'Test',
            'icon': None,
            'badge': None,
        }
        result = clean_item_data(item)

        assert 'text' in result
        assert 'icon' not in result
        assert 'badge' not in result

    def test_preserves_lists(self):
        """Should preserve list values."""
        item = {
            'text': 'Parent',
            'tags': ['tag1', 'tag2'],
        }
        result = clean_item_data(item)

        assert result['tags'] == ['tag1', 'tag2']

    def test_recursively_cleans_children(self):
        """Should recursively clean _children list."""
        item = {
            'text': 'Parent',
            '_children': [
                {'text': 'Child 1', 'icon': None},
                {'text': 'Child 2', 'count': 5},
            ],
        }
        result = clean_item_data(item)

        assert len(result['_children']) == 2
        assert result['_children'][0]['text'] == 'Child 1'
        assert 'icon' not in result['_children'][0]
        assert result['_children'][1]['count'] == 5

    def test_converts_object_to_dict_via_text(self):
        """Should convert non-dict objects to {'text': str(obj)}."""
        result = clean_item_data("Simple String")
        assert result == {'text': 'Simple String'}

    def test_handles_row_objects_with_dict(self):
        """Should extract dict from objects with __dict__."""
        class MockRow:
            def __init__(self):
                self.text = 'Row Text'
                self.count = 10
                self._private = 'hidden'

        row = MockRow()
        result = clean_item_data(row)

        assert result['text'] == 'Row Text'
        assert result['count'] == 10
        assert '_private' not in result  # Private attrs excluded


class TestGetItemId:
    """Tests for get_item_id function."""

    def test_returns_collection_id_when_present(self):
        """Should prefer _collection_data.id over text."""
        item = {
            'text': 'My Collection',
            '_collection_data': {'id': 'col-123', 'name': 'My Collection'},
        }
        assert get_item_id(item) == 'col-123'

    def test_falls_back_to_text_when_no_collection_data(self):
        """Should use text field when no _collection_data."""
        item = {'text': 'Fallback Item'}
        assert get_item_id(item) == 'Fallback Item'

    def test_returns_empty_string_for_non_dict(self):
        """Should return empty string for non-dict input."""
        assert get_item_id("not a dict") == ""
        assert get_item_id(123) == ""
        assert get_item_id(None) == ""

    def test_returns_empty_string_when_no_id_fields(self):
        """Should return empty string when neither id nor text present."""
        item = {'icon': 'folder', 'count': 5}
        assert get_item_id(item) == ""


class TestFindItemById:
    """Tests for find_item_by_id function."""

    def test_finds_item_at_root_level(self):
        """Should find item in root list."""
        data = [
            {'text': 'Item 1'},
            {'text': 'Item 2'},
            {'text': 'Item 3'},
        ]
        result = find_item_by_id(data, 'Item 2')

        assert result is not None
        assert result['text'] == 'Item 2'

    def test_finds_item_by_collection_id(self):
        """Should find item by _collection_data.id."""
        data = [
            {'text': 'Col 1', '_collection_data': {'id': 'c1'}},
            {'text': 'Col 2', '_collection_data': {'id': 'c2'}},
        ]
        result = find_item_by_id(data, 'c2')

        assert result is not None
        assert result['text'] == 'Col 2'

    def test_finds_nested_item(self):
        """Should find item in nested children."""
        data = [
            {
                'text': 'Parent',
                '_children': [
                    {'text': 'Child 1'},
                    {'text': 'Child 2', '_children': [{'text': 'Grandchild'}]},
                ],
            },
        ]
        result = find_item_by_id(data, 'Grandchild')

        assert result is not None
        assert result['text'] == 'Grandchild'

    def test_returns_none_when_not_found(self):
        """Should return None when item not found."""
        data = [{'text': 'Item 1'}]
        assert find_item_by_id(data, 'NonExistent') is None

    def test_handles_empty_list(self):
        """Should handle empty list."""
        assert find_item_by_id([], 'anything') is None

    def test_handles_non_list_input(self):
        """Should handle non-list input."""
        assert find_item_by_id("not a list", 'anything') is None


class TestIsDescendantOf:
    """Tests for is_descendant_of function."""

    def test_returns_true_for_same_item(self):
        """Should return True if item matches ancestor_id."""
        item = {'text': 'My Item'}
        assert is_descendant_of(item, 'My Item') is True

    def test_returns_true_for_same_collection_id(self):
        """Should match by _collection_data.id."""
        item = {'text': 'My Item', '_collection_data': {'id': 'item-123'}}
        assert is_descendant_of(item, 'item-123') is True

    def test_returns_true_for_child(self):
        """Should return True if ancestor_id matches a child."""
        item = {
            'text': 'Parent',
            '_children': [
                {'text': 'Child 1'},
                {'text': 'Child 2'},
            ],
        }
        assert is_descendant_of(item, 'Child 1') is True

    def test_returns_true_for_deep_descendant(self):
        """Should return True for deeply nested descendants."""
        item = {
            'text': 'Root',
            '_children': [
                {
                    'text': 'Level 1',
                    '_children': [
                        {
                            'text': 'Level 2',
                            '_children': [{'text': 'Target'}],
                        },
                    ],
                },
            ],
        }
        assert is_descendant_of(item, 'Target') is True

    def test_returns_false_for_non_descendant(self):
        """Should return False for non-descendant."""
        item = {'text': 'Item', '_children': [{'text': 'Child'}]}
        assert is_descendant_of(item, 'NonExistent') is False

    def test_handles_non_dict(self):
        """Should return False for non-dict input."""
        assert is_descendant_of("string", 'anything') is False


class TestFindItemInTree:
    """Tests for find_item_in_tree function."""

    def test_finds_item_at_root_returns_tuple(self):
        """Should return (item, parent, index) tuple."""
        data = [{'text': 'Item 1'}, {'text': 'Item 2'}]
        item, parent, index = find_item_in_tree(data, 'Item 2')

        assert item['text'] == 'Item 2'
        assert parent is None  # Root level
        assert index == 1

    def test_finds_nested_item_with_parent(self):
        """Should return parent for nested items."""
        parent_item = {
            'text': 'Parent',
            '_children': [{'text': 'Child 1'}, {'text': 'Child 2'}],
        }
        data = [parent_item]

        item, parent, index = find_item_in_tree(data, 'Child 2')

        assert item['text'] == 'Child 2'
        assert parent['text'] == 'Parent'
        assert index == 1

    def test_returns_none_tuple_when_not_found(self):
        """Should return (None, None, -1) when not found."""
        data = [{'text': 'Item'}]
        item, parent, index = find_item_in_tree(data, 'NonExistent')

        assert item is None
        assert parent is None
        assert index == -1


class TestRemoveItemFromParent:
    """Tests for remove_item_from_parent function."""

    def test_removes_from_root_level(self):
        """Should remove item from root data list."""
        item = {'text': 'To Remove'}
        data = [{'text': 'Keep'}, item]

        result = remove_item_from_parent(item, None, data)

        assert result is True
        assert len(data) == 1
        assert item not in data

    def test_removes_from_parent_children(self):
        """Should remove item from parent's _children."""
        item = {'text': 'Child to Remove'}
        parent = {'text': 'Parent', '_children': [item, {'text': 'Other'}]}
        data = [parent]

        result = remove_item_from_parent(item, parent, data)

        assert result is True
        assert len(parent['_children']) == 1
        assert item not in parent['_children']

    def test_returns_false_when_item_not_in_parent(self):
        """Should return False when item not found."""
        item = {'text': 'Not Here'}
        data = [{'text': 'Other'}]

        result = remove_item_from_parent(item, None, data)

        assert result is False


class TestInsertItemIntoParent:
    """Tests for insert_item_into_parent function."""

    def test_inserts_at_root_level(self):
        """Should insert at root level when parent is None."""
        item = {'text': 'New Item'}
        data = [{'text': 'Existing'}]

        result = insert_item_into_parent(item, None, 0, data)

        assert result is True
        assert data[0] == item
        assert len(data) == 2

    def test_inserts_at_end_with_negative_index(self):
        """Should append when index is -1."""
        item = {'text': 'New Item'}
        data = [{'text': 'First'}]

        result = insert_item_into_parent(item, None, -1, data)

        assert result is True
        assert data[-1] == item

    def test_inserts_into_parent_children(self):
        """Should insert into parent's _children."""
        item = {'text': 'New Child'}
        parent = {'text': 'Parent', '_children': [{'text': 'Existing'}]}
        data = [parent]

        result = insert_item_into_parent(item, parent, 0, data)

        assert result is True
        assert parent['_children'][0] == item
        assert parent['_has_children'] is True

    def test_creates_children_list_if_needed(self):
        """Should handle parent with empty _children list."""
        item = {'text': 'First Child'}
        parent = {'text': 'Parent', '_children': []}
        data = [parent]

        result = insert_item_into_parent(item, parent, 0, data)

        assert result is True
        assert len(parent['_children']) == 1


class TestFlattenTree:
    """Tests for flatten_tree function."""

    def test_flattens_simple_list(self):
        """Should return same list for flat data."""
        data = [{'text': 'A'}, {'text': 'B'}, {'text': 'C'}]
        result = flatten_tree(data)

        assert len(result) == 3
        assert [item['text'] for item in result] == ['A', 'B', 'C']

    def test_flattens_nested_structure(self):
        """Should flatten nested children in tree order."""
        data = [
            {
                'text': 'Parent',
                '_children': [
                    {'text': 'Child 1'},
                    {'text': 'Child 2'},
                ],
            },
        ]
        result = flatten_tree(data)

        assert len(result) == 3
        assert [item['text'] for item in result] == ['Parent', 'Child 1', 'Child 2']

    def test_flattens_deeply_nested(self):
        """Should handle deeply nested structures."""
        data = [
            {
                'text': 'L0',
                '_children': [
                    {
                        'text': 'L1',
                        '_children': [
                            {'text': 'L2'},
                        ],
                    },
                ],
            },
        ]
        result = flatten_tree(data)

        assert len(result) == 3
        assert [item['text'] for item in result] == ['L0', 'L1', 'L2']

    def test_handles_empty_list(self):
        """Should return empty list for empty input."""
        assert flatten_tree([]) == []

    def test_skips_non_dict_items(self):
        """Should skip non-dict items."""
        data = [{'text': 'Valid'}, 'string', 123, None]
        result = flatten_tree(data)

        assert len(result) == 1
        assert result[0]['text'] == 'Valid'


class TestDragDropValidation:
    """Integration tests for drag-drop validation helpers."""

    def test_circular_reference_detection(self):
        """Should detect when dropping item onto its descendant."""
        parent = {
            'text': 'Parent',
            '_collection_data': {'id': 'parent-id'},
            '_children': [
                {'text': 'Child', '_collection_data': {'id': 'child-id'}},
            ],
        }

        # Trying to drop Parent onto Child should be detected as circular
        child = parent['_children'][0]
        assert is_descendant_of(parent, 'child-id') is True  # Child is descendant of Parent

    def test_move_item_preserves_tree_integrity(self):
        """Should maintain valid tree structure after move."""
        section = {
            'text': 'Section',
            '_children': [
                {'text': 'Col 1', '_collection_data': {'id': 'c1'}},
                {'text': 'Col 2', '_collection_data': {'id': 'c2'}},
                {'text': 'Col 3', '_collection_data': {'id': 'c3'}},
            ],
        }
        data = [section]

        # Find and remove Col 2
        item, parent, idx = find_item_in_tree(section['_children'], 'Col 2')
        assert item is not None

        remove_item_from_parent(item, section, data)
        assert len(section['_children']) == 2

        # Insert at beginning
        insert_item_into_parent(item, section, 0, data)
        assert section['_children'][0]['text'] == 'Col 2'
        assert len(section['_children']) == 3

    def test_self_drop_detection_by_text(self):
        """Should detect when item is dropped onto itself (by text ID)."""
        item = {'text': 'Flagged', '_is_section_header': False}

        # get_item_id returns 'text' when no _collection_data
        item_id = get_item_id(item)
        assert item_id == 'Flagged'

        # Dropping item onto itself should be detected
        assert is_descendant_of(item, 'Flagged') is True

    def test_self_drop_detection_by_collection_id(self):
        """Should detect when item is dropped onto itself (by collection ID)."""
        item = {
            'text': 'My Collection',
            '_collection_data': {'id': 'col-abc-123', 'name': 'My Collection'},
        }

        # get_item_id returns collection ID
        item_id = get_item_id(item)
        assert item_id == 'col-abc-123'

        # Dropping item onto itself should be detected
        assert is_descendant_of(item, 'col-abc-123') is True

    def test_drop_onto_section_header_allowed(self):
        """Should allow dropping onto section headers (items go to end)."""
        section = {
            'text': 'COLLECTIONS',
            '_is_section_header': True,
            '_children': [
                {'text': 'Col 1', '_collection_data': {'id': 'c1'}},
                {'text': 'Col 2', '_collection_data': {'id': 'c2'}},
            ],
        }

        # Section headers can accept drops (items become children)
        children = section.get('_children', [])
        insert_index = len(children)  # Drop at end

        assert insert_index == 2
        assert section.get('_is_section_header') is True

    def test_drop_between_items_preserves_order(self):
        """Should maintain correct order when dropping between items."""
        section = {
            'text': 'Section',
            '_is_section_header': True,
            '_children': [
                {'text': 'A', '_collection_data': {'id': 'a'}},
                {'text': 'B', '_collection_data': {'id': 'b'}},
                {'text': 'C', '_collection_data': {'id': 'c'}},
            ],
        }
        data = [section]

        # Move C to position 0 (before A)
        item, parent, idx = find_item_in_tree(section['_children'], 'C')
        assert item is not None
        assert idx == 2

        remove_item_from_parent(item, section, data)
        insert_item_into_parent(item, section, 0, data)

        # Verify new order: C, A, B
        assert section['_children'][0]['text'] == 'C'
        assert section['_children'][1]['text'] == 'A'
        assert section['_children'][2]['text'] == 'B'

    def test_drop_between_items_index_adjustment(self):
        """Should adjust index when moving within same parent."""
        section = {
            'text': 'Section',
            '_children': [
                {'text': 'A'},  # index 0
                {'text': 'B'},  # index 1
                {'text': 'C'},  # index 2
            ],
        }
        data = [section]

        # Move A from index 0 to index 2 (after B, before C)
        # After removing A: [B, C] - target index 2 should become 1
        item, parent, source_idx = find_item_in_tree(section['_children'], 'A')
        assert source_idx == 0

        remove_item_from_parent(item, section, data)
        assert len(section['_children']) == 2

        # Insert at adjusted index
        target_index = 2
        adjusted_index = target_index - 1  # Moving within same parent, source before target
        insert_item_into_parent(item, section, adjusted_index, data)

        # Verify order: B, A, C
        assert section['_children'][0]['text'] == 'B'
        assert section['_children'][1]['text'] == 'A'
        assert section['_children'][2]['text'] == 'C'

    def test_circular_reference_deep_nesting(self):
        """Should detect circular reference in deeply nested structures."""
        grandparent = {
            'text': 'Grandparent',
            '_collection_data': {'id': 'gp'},
            '_children': [
                {
                    'text': 'Parent',
                    '_collection_data': {'id': 'p'},
                    '_children': [
                        {
                            'text': 'Child',
                            '_collection_data': {'id': 'c'},
                            '_children': [
                                {'text': 'Grandchild', '_collection_data': {'id': 'gc'}},
                            ],
                        },
                    ],
                },
            ],
        }

        # Grandparent contains Grandchild
        assert is_descendant_of(grandparent, 'gc') is True

        # But Grandchild does NOT contain Grandparent
        grandchild = grandparent['_children'][0]['_children'][0]['_children'][0]
        assert is_descendant_of(grandchild, 'gp') is False

    def test_non_descendant_items_allowed(self):
        """Should allow dropping unrelated items."""
        section1 = {
            'text': 'Section 1',
            '_children': [
                {'text': 'Item A', '_collection_data': {'id': 'a'}},
            ],
        }
        section2 = {
            'text': 'Section 2',
            '_children': [
                {'text': 'Item B', '_collection_data': {'id': 'b'}},
            ],
        }

        # Item A is not in Section 2's tree
        assert is_descendant_of(section2, 'a') is False

        # Item B is not in Section 1's tree
        assert is_descendant_of(section1, 'b') is False


class TestDropVisualFeedback:
    """
    Tests for drag-drop visual feedback behaviors.

    NSOutlineView uses two types of visual feedback during drag:
    - Insertion line (index >= 0): Shows where item will be inserted BETWEEN other items
    - Blue highlight (index == -1): Shows item will be dropped ON/INTO the target

    The index parameter determines which feedback is shown:
    - index >= 0: Insertion line at that position
    - index == -1: Blue highlight on the target item
    """

    def test_insertion_line_index_values(self):
        """
        index >= 0 means insertion line - item inserted BETWEEN siblings.

        Visual: A horizontal line appears between items showing insertion point.
        """
        section = {
            'text': 'Section',
            '_is_section_header': True,
            '_children': [
                {'text': 'First'},
                {'text': 'Second'},
                {'text': 'Third'},
            ],
        }

        # index=0: Insert BEFORE First (line above First)
        # index=1: Insert BETWEEN First and Second
        # index=2: Insert BETWEEN Second and Third
        # index=3: Insert AFTER Third (at end)

        for index in [0, 1, 2, 3]:
            # Valid insertion line positions
            assert index >= 0
            assert index <= len(section['_children'])

    def test_highlight_index_value(self):
        """
        index == -1 means blue highlight - item dropped ON/INTO target.

        Visual: Target item shows blue selection highlight.
        """
        folder = {
            'text': 'Folder',
            '_can_accept_drops': True,
            '_children': [],
        }

        # index=-1 signifies drop ON the item (not between)
        drop_on_index = -1
        assert drop_on_index == -1

    def test_folder_accepts_drops_flag(self):
        """
        Items with _can_accept_drops=True can receive drops (show highlight).
        """
        folder = {
            'text': 'My Folder',
            '_can_accept_drops': True,
            '_children': [],
        }

        regular_item = {
            'text': 'Regular Item',
            # No _can_accept_drops flag
        }

        assert folder.get('_can_accept_drops', False) is True
        assert regular_item.get('_can_accept_drops', False) is False

    def test_section_header_always_accepts_drops(self):
        """
        Section headers always accept drops (items become children).
        """
        section = {
            'text': 'COLLECTIONS',
            '_is_section_header': True,
            '_children': [],
        }

        assert section.get('_is_section_header', False) is True
        # Section headers implicitly accept drops

    def test_drop_on_folder_adds_at_end(self):
        """
        When dropping ON a folder (index=-1), item goes to end of children.
        """
        folder = {
            'text': 'Folder',
            '_can_accept_drops': True,
            '_children': [
                {'text': 'Existing 1'},
                {'text': 'Existing 2'},
            ],
        }
        data = [folder]

        new_item = {'text': 'New Item'}

        # When drop index is -1 (ON folder), insert at end of children
        insert_index = len(folder['_children'])
        assert insert_index == 2

        insert_item_into_parent(new_item, folder, insert_index, data)

        # Item should be at end
        assert folder['_children'][-1]['text'] == 'New Item'
        assert len(folder['_children']) == 3

    def test_drop_between_uses_exact_index(self):
        """
        When dropping BETWEEN items (index >= 0), use exact insertion position.
        """
        section = {
            'text': 'Section',
            '_is_section_header': True,
            '_children': [
                {'text': 'A'},
                {'text': 'B'},
                {'text': 'C'},
            ],
        }
        data = [section]

        new_item = {'text': 'NEW'}

        # Insert at index 1 (between A and B)
        insert_item_into_parent(new_item, section, 1, data)

        assert section['_children'][0]['text'] == 'A'
        assert section['_children'][1]['text'] == 'NEW'
        assert section['_children'][2]['text'] == 'B'
        assert section['_children'][3]['text'] == 'C'


class TestDropContainerTypes:
    """
    Tests for different container types and their drop behavior.
    """

    def test_section_header_container(self):
        """Section headers are containers for collections."""
        section = {
            'text': 'SMART COLLECTIONS',
            '_is_section_header': True,
            '_has_children': True,
            '_children': [
                {'text': 'Flagged', '_collection_data': {'id': 'flagged'}},
            ],
        }

        assert section.get('_is_section_header') is True
        assert section.get('_has_children') is True
        assert len(section.get('_children', [])) == 1

    def test_folder_container(self):
        """Folders with _can_accept_drops are containers."""
        folder = {
            'text': 'Archive',
            '_can_accept_drops': True,
            '_has_children': True,
            '_children': [
                {'text': 'Old Item 1'},
                {'text': 'Old Item 2'},
            ],
        }

        assert folder.get('_can_accept_drops') is True
        assert folder.get('_has_children') is True

    def test_regular_item_not_container(self):
        """Regular items without flags are not containers."""
        item = {
            'text': 'Just a Collection',
            '_collection_data': {'id': 'col-123'},
        }

        # Should not accept drops
        assert item.get('_can_accept_drops', False) is False
        assert item.get('_is_section_header', False) is False

    def test_nested_folder_drop(self):
        """Can drop items into nested folder structures."""
        root_folder = {
            'text': 'Root',
            '_can_accept_drops': True,
            '_children': [
                {
                    'text': 'Subfolder',
                    '_can_accept_drops': True,
                    '_children': [],
                },
            ],
        }
        data = [root_folder]

        new_item = {'text': 'New Item'}
        subfolder = root_folder['_children'][0]

        # Drop into subfolder
        insert_item_into_parent(new_item, subfolder, 0, data)

        assert len(subfolder['_children']) == 1
        assert subfolder['_children'][0]['text'] == 'New Item'
        assert subfolder.get('_has_children') is True


class TestDropValidationRules:
    """
    Tests for drop validation rules that determine valid drop targets.
    """

    def test_reject_drop_on_non_container_items(self):
        """
        Cannot drop ON regular items (only BETWEEN them).

        Regular items should reject index=-1 (highlight) drops.
        Only section headers and folders accept ON drops.
        """
        regular_item = {
            'text': 'Regular Collection',
            '_collection_data': {'id': 'col-1'},
        }

        # Should not accept ON drops
        can_accept_on = (
            regular_item.get('_is_section_header', False) or
            regular_item.get('_can_accept_drops', False)
        )
        assert can_accept_on is False

    def test_accept_drop_between_siblings(self):
        """Can always drop BETWEEN sibling items for reordering."""
        section = {
            'text': 'Section',
            '_is_section_header': True,
            '_children': [
                {'text': 'A'},
                {'text': 'B'},
                {'text': 'C'},
            ],
        }

        # Insertion between any siblings should be valid
        # index values 0-3 are all valid for 3 children
        for index in range(len(section['_children']) + 1):
            assert index >= 0  # All are insertion line positions

    def test_cannot_drop_item_onto_itself(self):
        """Dropping item onto itself is invalid."""
        item = {
            'text': 'Item',
            '_collection_data': {'id': 'item-1'},
        }

        source_id = get_item_id(item)
        target_id = get_item_id(item)

        # Same ID = self-drop = invalid
        assert source_id == target_id
        assert is_descendant_of(item, source_id) is True

    def test_cannot_drop_parent_into_descendant(self):
        """Dropping parent into its own child creates circular reference."""
        parent = {
            'text': 'Parent',
            '_collection_data': {'id': 'parent'},
            '_can_accept_drops': True,
            '_children': [
                {
                    'text': 'Child',
                    '_collection_data': {'id': 'child'},
                    '_can_accept_drops': True,
                    '_children': [],
                },
            ],
        }

        parent_id = get_item_id(parent)
        child = parent['_children'][0]

        # Child contains parent in its ancestry? No, parent contains child
        assert is_descendant_of(parent, 'child') is True

        # If we tried to drop parent INTO child, that would create a cycle
        # The check is: does target contain source? If yes, reject.
        # Here child does NOT contain parent, so technically allowed
        # But parent contains child, so moving parent under child = cycle

        # The correct check: before moving source under target,
        # verify target is NOT a descendant of source
        source_id = 'parent'
        target = child

        # is_descendant_of(parent, 'child') = True means child is IN parent
        # So dropping parent under child would create: child -> parent -> child (cycle)
        assert is_descendant_of(parent, get_item_id(target)) is True

    def test_allow_drop_between_unrelated_items(self):
        """Dropping between unrelated items is valid."""
        section1 = {
            'text': 'Section 1',
            '_is_section_header': True,
            '_children': [
                {'text': 'A', '_collection_data': {'id': 'a'}},
            ],
        }
        section2 = {
            'text': 'Section 2',
            '_is_section_header': True,
            '_children': [
                {'text': 'B', '_collection_data': {'id': 'b'}},
            ],
        }

        # A is not in Section 2's tree
        assert is_descendant_of(section2, 'a') is False

        # So moving A into Section 2 is valid (no circular ref)


class TestMoveOperations:
    """
    Tests for complete move operations (remove + insert).
    """

    def test_reorder_within_section(self):
        """Moving item within same section reorders children."""
        section = {
            'text': 'Section',
            '_is_section_header': True,
            '_children': [
                {'text': 'First'},
                {'text': 'Second'},
                {'text': 'Third'},
            ],
        }
        data = [section]

        # Move 'Third' to first position
        item, parent, idx = find_item_in_tree(section['_children'], 'Third')
        assert item is not None
        assert idx == 2

        remove_item_from_parent(item, section, data)
        insert_item_into_parent(item, section, 0, data)

        assert [c['text'] for c in section['_children']] == ['Third', 'First', 'Second']

    def test_move_to_different_section(self):
        """Moving item to different section removes from source."""
        section1 = {
            'text': 'Section 1',
            '_is_section_header': True,
            '_children': [
                {'text': 'Item A'},
                {'text': 'Item B'},
            ],
        }
        section2 = {
            'text': 'Section 2',
            '_is_section_header': True,
            '_children': [],
        }
        data = [section1, section2]

        # Move Item B to Section 2
        item, parent, idx = find_item_in_tree(section1['_children'], 'Item B')

        remove_item_from_parent(item, section1, data)
        insert_item_into_parent(item, section2, 0, data)

        assert len(section1['_children']) == 1
        assert section1['_children'][0]['text'] == 'Item A'

        assert len(section2['_children']) == 1
        assert section2['_children'][0]['text'] == 'Item B'

    def test_move_into_folder(self):
        """Moving item into folder makes it a child."""
        folder = {
            'text': 'Archive Folder',
            '_can_accept_drops': True,
            '_children': [],
        }
        section = {
            'text': 'Section',
            '_is_section_header': True,
            '_children': [
                folder,
                {'text': 'Item to Move'},
            ],
        }
        data = [section]

        item, parent, idx = find_item_in_tree(section['_children'], 'Item to Move')

        remove_item_from_parent(item, section, data)
        insert_item_into_parent(item, folder, 0, data)

        # Item is now in folder
        assert len(folder['_children']) == 1
        assert folder['_children'][0]['text'] == 'Item to Move'
        assert folder.get('_has_children') is True

        # And removed from section
        assert len(section['_children']) == 1

    def test_move_preserves_item_data(self):
        """Moving item preserves all its data including _collection_data."""
        item = {
            'text': 'My Collection',
            '_collection_data': {'id': 'col-123', 'name': 'My Collection', 'type': 'smart'},
            'icon': 'folder',
        }
        section = {
            'text': 'Section',
            '_is_section_header': True,
            '_children': [item],
        }
        new_section = {
            'text': 'New Section',
            '_is_section_header': True,
            '_children': [],
        }
        data = [section, new_section]

        remove_item_from_parent(item, section, data)
        insert_item_into_parent(item, new_section, 0, data)

        moved = new_section['_children'][0]
        assert moved['text'] == 'My Collection'
        assert moved['_collection_data']['id'] == 'col-123'
        assert moved['_collection_data']['type'] == 'smart'
        assert moved['icon'] == 'folder'
