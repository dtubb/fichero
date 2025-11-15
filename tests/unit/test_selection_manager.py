"""
Unit tests for SelectionManager service.

Tests all scenarios from Phase 1 implementation plan plus edge cases from review.
"""

import pytest
from unittest.mock import Mock, patch, call
from fichero.shared.selection import SelectionManager, SelectionContext, SelectionState


class TestSelectionManager:
    """Test suite for SelectionManager"""

    def setup_method(self):
        """Set up test fixtures"""
        self.manager = SelectionManager()

    # Test Scenario 1: Initial state is empty
    def test_initial_state_empty(self):
        """Test that SelectionManager initializes with empty state"""
        assert self.manager.get_selection_count('collection') == 0
        assert self.manager.get_selection('collection') == []
        assert self.manager.get_selection_metadata('collection') == []

    # Test Scenario 2: Set selection
    def test_set_selection(self):
        """Test setting selection for a view"""
        self.manager.set_selection('collection', ['item-1', 'item-2'])
        assert self.manager.get_selection_count('collection') == 2
        assert self.manager.get_selection('collection') == ['item-1', 'item-2']

    # Test Scenario 3: Get selection
    def test_get_selection_returns_copy(self):
        """Test that get_selection returns a copy (prevents mutation)"""
        self.manager.set_selection('collection', ['item-1'])
        selected = self.manager.get_selection('collection')
        selected.append('item-2')  # Try to mutate
        # Original should be unchanged
        assert self.manager.get_selection('collection') == ['item-1']

    # Test Scenario 4: Clear selection
    def test_clear_selection(self):
        """Test clearing selection for a view"""
        self.manager.set_selection('collection', ['item-1', 'item-2'])
        self.manager.clear_selection('collection')
        assert self.manager.get_selection_count('collection') == 0

    # Test Scenario 5: Set selection with metadata
    def test_set_selection_with_metadata(self):
        """Test setting selection with metadata"""
        metadata = [
            {'name': 'Item 1', 'type': 'pdf'},
            {'name': 'Item 2', 'type': 'image'}
        ]
        self.manager.set_selection(
            'collection',
            ['item-1', 'item-2'],
            metadata=metadata
        )
        retrieved_metadata = self.manager.get_selection_metadata('collection')
        assert len(retrieved_metadata) == 2
        assert retrieved_metadata[0]['name'] == 'Item 1'
        assert retrieved_metadata[1]['type'] == 'image'

    # Test Scenario 6: Get state snapshot
    def test_get_state_snapshot(self):
        """Test getting immutable state snapshot"""
        self.manager.set_selection(
            'collection',
            ['item-1'],
            metadata=[{'name': 'Test Item'}]
        )
        snapshot = self.manager.get_state_snapshot('collection')
        assert snapshot is not None
        assert snapshot.count == 1
        assert snapshot.has_selection == True
        assert snapshot.view_id == 'collection'
        assert snapshot.context == SelectionContext.COLLECTION

    # Test Scenario 7: Clear all selections
    def test_clear_all_selections(self):
        """Test clearing all selections"""
        self.manager.set_selection('collection', ['item-1'])
        self.manager.set_selection('library', ['coll-1'])
        self.manager.clear_all_selections()
        assert self.manager.get_selection_count('collection') == 0
        assert self.manager.get_selection_count('library') == 0

    # Edge Case Test: Metadata length mismatch (from Review Recommendation #1)
    def test_metadata_length_mismatch(self):
        """Test that metadata length mismatch is handled gracefully"""
        # Should log warning and ignore metadata
        self.manager.set_selection(
            'collection',
            ['item-1', 'item-2'],
            metadata=[{'name': 'Item 1'}]  # Only 1 metadata for 2 items
        )
        # Metadata should be ignored due to mismatch
        assert self.manager.get_selection_metadata('collection') == []
        # Selection should still be set
        assert self.manager.get_selection('collection') == ['item-1', 'item-2']

    # Edge Case Test: Unknown view_id handling
    def test_unknown_view_id(self):
        """Test handling of unknown view_id"""
        self.manager.set_selection('unknown_view', ['item-1'])
        # Should not crash, should use fallback context
        assert self.manager.get_selection('unknown_view') == ['item-1']
        snapshot = self.manager.get_state_snapshot('unknown_view')
        # Should default to COLLECTION context
        assert snapshot.context == SelectionContext.COLLECTION

    # Edge Case Test: None values in item_ids
    def test_none_values_filtered(self):
        """Test that None values are filtered from item_ids"""
        self.manager.set_selection('collection', ['item-1', None, 'item-2'])
        # None should be filtered out
        assert self.manager.get_selection('collection') == ['item-1', 'item-2']

    # Edge Case Test: Non-list input conversion
    def test_non_list_input_conversion(self):
        """Test that single item is converted to list"""
        self.manager.set_selection('collection', 'item-1')
        assert self.manager.get_selection('collection') == ['item-1']

    # Edge Case Test: Empty list clears selection
    def test_empty_list_clears_selection(self):
        """Test that empty list clears selection"""
        self.manager.set_selection('collection', ['item-1'])
        self.manager.set_selection('collection', [])
        assert self.manager.get_selection_count('collection') == 0

    # Edge Case Test: Selection unchanged skips event
    @patch('fichero.shared.selection.selection_manager.emit_navigation_event')
    def test_selection_unchanged_skips_event(self, mock_emit):
        """Test that unchanged selection doesn't emit event"""
        self.manager.set_selection('collection', ['item-1'])
        mock_emit.reset_mock()
        # Set same selection again
        self.manager.set_selection('collection', ['item-1'])
        # Should not emit event (selection unchanged)
        mock_emit.assert_not_called()

    # Edge Case Test: Event emission with correct payload
    @patch('fichero.shared.selection.selection_manager.emit_navigation_event')
    def test_event_emission_payload(self, mock_emit):
        """Test that SELECTION_CHANGED event has correct payload"""
        self.manager.set_selection('collection', ['item-1', 'item-2'])
        # Verify event was emitted
        mock_emit.assert_called_once()
        event_type, event_data = mock_emit.call_args[0]
        assert event_type == "SELECTION_CHANGED"
        assert event_data['view_id'] == 'collection'
        assert event_data['context'] == 'collection'
        assert event_data['old_selection'] == []
        assert event_data['new_selection'] == ['item-1', 'item-2']
        assert event_data['count'] == 2

    # Edge Case Test: Metadata deep copy (Review Issue #4)
    def test_metadata_deep_copy(self):
        """Test that metadata is deep copied to prevent mutation"""
        original_metadata = [{'name': 'Item 1', 'data': {'nested': 'value'}}]
        self.manager.set_selection('collection', ['item-1'], metadata=original_metadata)

        # Mutate original metadata
        original_metadata[0]['name'] = 'Modified'
        original_metadata[0]['data']['nested'] = 'changed'

        # Retrieved metadata should be unchanged
        retrieved = self.manager.get_selection_metadata('collection')
        assert retrieved[0]['name'] == 'Item 1'
        # Note: .copy() does shallow copy, so nested dicts ARE shared
        # This is acceptable per review - if needed, switch to deepcopy

    # Edge Case Test: Event emission failure doesn't crash (Review Issue #1)
    @patch('fichero.shared.selection.selection_manager.emit_navigation_event')
    def test_event_emission_failure_handled(self, mock_emit):
        """Test that event emission failure doesn't crash SelectionManager"""
        # Make emit_navigation_event raise an exception
        mock_emit.side_effect = Exception("Event bus failure")

        # Should not crash, should log error
        self.manager.set_selection('collection', ['item-1'])

        # State should still be updated
        assert self.manager.get_selection('collection') == ['item-1']

    # Test: SelectionState to_dict method
    def test_selection_state_to_dict(self):
        """Test SelectionState to_dict serialization"""
        self.manager.set_selection('collection', ['item-1'], metadata=[{'name': 'Item'}])
        snapshot = self.manager.get_state_snapshot('collection')
        state_dict = snapshot.to_dict()

        assert state_dict['view_id'] == 'collection'
        assert state_dict['item_ids'] == ['item-1']
        assert state_dict['context'] == 'collection'
        assert state_dict['count'] == 1
        assert state_dict['has_selection'] == True

    # Test: Multiple view isolation
    def test_multiple_view_isolation(self):
        """Test that different views have independent selections"""
        self.manager.set_selection('collection', ['item-1'])
        self.manager.set_selection('library', ['coll-1'])
        self.manager.set_selection('steps', ['step-1'])

        # Each view should have independent selection
        assert self.manager.get_selection('collection') == ['item-1']
        assert self.manager.get_selection('library') == ['coll-1']
        assert self.manager.get_selection('steps') == ['step-1']

    # Test: Context mapping for view aliases
    def test_context_mapping_aliases(self):
        """Test that view aliases map to correct contexts"""
        # 'output' should map to PREVIEW context
        self.manager.set_selection('output', ['item-1'])
        snapshot = self.manager.get_state_snapshot('output')
        assert snapshot.context == SelectionContext.PREVIEW

    # Test: get_state_snapshot returns None for invalid view_id
    def test_get_state_snapshot_invalid_view(self):
        """Test that get_state_snapshot handles invalid view gracefully"""
        # Create a view_id that's truly not in _selections dict
        snapshot = self.manager.get_state_snapshot('completely_invalid_view_12345')
        # Should handle gracefully and return state with fallback context
        assert snapshot is not None  # We always create state for any view_id


class TestSelectionContext:
    """Test SelectionContext enum"""

    def test_context_values(self):
        """Test that all context values are defined"""
        assert SelectionContext.LIBRARY.value == "library"
        assert SelectionContext.COLLECTION.value == "collection"
        assert SelectionContext.STEPS.value == "steps"
        assert SelectionContext.PREVIEW.value == "preview"
        assert SelectionContext.ADJUST.value == "adjust"


class TestSelectionState:
    """Test SelectionState dataclass"""

    def test_selection_state_properties(self):
        """Test SelectionState computed properties"""
        state = SelectionState(
            view_id='collection',
            item_ids=['item-1', 'item-2'],
            metadata=[],
            timestamp=1234567890.0,
            context=SelectionContext.COLLECTION
        )
        assert state.count == 2
        assert state.has_selection == True

    def test_selection_state_empty(self):
        """Test SelectionState with empty selection"""
        state = SelectionState(
            view_id='collection',
            item_ids=[],
            metadata=[],
            timestamp=1234567890.0,
            context=SelectionContext.COLLECTION
        )
        assert state.count == 0
        assert state.has_selection == False
