"""
Integration tests for Phase 1: SelectionManager Service

Tests the integration of SelectionManager with the rest of the application.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import time


class TestPhase1Integration:
    """Integration tests for SelectionManager with application components"""

    def setup_method(self):
        """Set up test fixtures"""
        # Import here to avoid issues with module-level imports
        from fichero.shared.selection import SelectionManager
        self.manager = SelectionManager()

    def test_selection_manager_initializes_correctly(self):
        """Test that SelectionManager can be instantiated"""
        from fichero.shared.selection import SelectionManager

        manager = SelectionManager()
        assert manager is not None
        assert hasattr(manager, 'set_selection')
        assert hasattr(manager, 'get_selection')
        assert hasattr(manager, 'get_selection_count')

    def test_selection_changes_tracked(self):
        """Test that selection changes are properly tracked"""
        # Set initial selection
        self.manager.set_selection('collection', ['item-1'])
        assert self.manager.get_selection('collection') == ['item-1']

        # Change selection
        self.manager.set_selection('collection', ['item-2', 'item-3'])
        assert self.manager.get_selection('collection') == ['item-2', 'item-3']

        # Verify count
        assert self.manager.get_selection_count('collection') == 2

    @patch('fichero.shared.selection.selection_manager.emit_navigation_event')
    def test_events_emitted_properly(self, mock_emit):
        """Test that SELECTION_CHANGED events are emitted"""
        self.manager.set_selection('collection', ['item-1'])

        # Verify event was emitted
        mock_emit.assert_called_once()
        event_type, event_data = mock_emit.call_args[0]

        assert event_type == "SELECTION_CHANGED"
        assert event_data['view_id'] == 'collection'
        assert event_data['new_selection'] == ['item-1']
        assert event_data['count'] == 1
        assert 'timestamp' in event_data

    def test_multi_selection_works(self):
        """Test that multi-selection is handled correctly"""
        items = ['item-1', 'item-2', 'item-3', 'item-4']
        self.manager.set_selection('collection', items)

        assert self.manager.get_selection_count('collection') == 4
        retrieved = self.manager.get_selection('collection')
        assert retrieved == items

    def test_metadata_preserved(self):
        """Test that metadata is preserved with selection"""
        metadata = [
            {'name': 'Document 1', 'type': 'pdf', 'size': 1024},
            {'name': 'Document 2', 'type': 'image', 'size': 2048}
        ]

        self.manager.set_selection(
            'collection',
            ['item-1', 'item-2'],
            metadata=metadata
        )

        retrieved_meta = self.manager.get_selection_metadata('collection')
        assert len(retrieved_meta) == 2
        assert retrieved_meta[0]['name'] == 'Document 1'
        assert retrieved_meta[1]['type'] == 'image'

    def test_get_state_returns_snapshot(self):
        """Test that get_state_snapshot returns correct snapshot"""
        self.manager.set_selection(
            'collection',
            ['item-1', 'item-2'],
            metadata=[{'name': 'Item 1'}, {'name': 'Item 2'}]
        )

        snapshot = self.manager.get_state_snapshot('collection')

        assert snapshot is not None
        assert snapshot.view_id == 'collection'
        assert snapshot.count == 2
        assert snapshot.has_selection == True
        assert len(snapshot.metadata) == 2

    def test_multiple_views_independent(self):
        """Test that different views maintain independent selections"""
        self.manager.set_selection('library', ['coll-1'])
        self.manager.set_selection('collection', ['item-1', 'item-2'])
        self.manager.set_selection('steps', ['step-0'])

        # All should be independent
        assert self.manager.get_selection_count('library') == 1
        assert self.manager.get_selection_count('collection') == 2
        assert self.manager.get_selection_count('steps') == 1

        # Clearing one shouldn't affect others
        self.manager.clear_selection('collection')
        assert self.manager.get_selection_count('library') == 1
        assert self.manager.get_selection_count('collection') == 0
        assert self.manager.get_selection_count('steps') == 1

    @patch('fichero.shared.selection.selection_manager.emit_navigation_event')
    def test_event_not_emitted_when_selection_unchanged(self, mock_emit):
        """Test that event is not emitted when selection doesn't change"""
        self.manager.set_selection('collection', ['item-1'])
        mock_emit.reset_mock()

        # Set same selection again
        self.manager.set_selection('collection', ['item-1'])

        # Event should not be emitted
        mock_emit.assert_not_called()

    def test_clear_all_selections_works(self):
        """Test clearing all selections at once"""
        self.manager.set_selection('library', ['coll-1'])
        self.manager.set_selection('collection', ['item-1'])
        self.manager.set_selection('steps', ['step-0'])

        self.manager.clear_all_selections()

        assert self.manager.get_selection_count('library') == 0
        assert self.manager.get_selection_count('collection') == 0
        assert self.manager.get_selection_count('steps') == 0

    def test_context_enum_mapping(self):
        """Test that view_ids map to correct contexts"""
        from fichero.shared.selection import SelectionContext

        # Test each context
        self.manager.set_selection('library', ['item-1'])
        snapshot = self.manager.get_state_snapshot('library')
        assert snapshot.context == SelectionContext.LIBRARY

        self.manager.set_selection('collection', ['item-1'])
        snapshot = self.manager.get_state_snapshot('collection')
        assert snapshot.context == SelectionContext.COLLECTION

        self.manager.set_selection('steps', ['item-1'])
        snapshot = self.manager.get_state_snapshot('steps')
        assert snapshot.context == SelectionContext.STEPS

    @patch('fichero.shared.selection.selection_manager.emit_navigation_event')
    def test_event_emission_failure_doesnt_crash(self, mock_emit):
        """Test that SelectionManager handles event emission failures gracefully"""
        # Make event emission fail
        mock_emit.side_effect = Exception("Event bus error")

        # Should not crash
        self.manager.set_selection('collection', ['item-1'])

        # State should still be updated
        assert self.manager.get_selection('collection') == ['item-1']

    def test_selection_state_immutability(self):
        """Test that SelectionState snapshot is immutable (modifications don't affect manager)"""
        self.manager.set_selection('collection', ['item-1'])

        # Get snapshot
        snapshot = self.manager.get_state_snapshot('collection')

        # Try to modify snapshot's item_ids
        snapshot.item_ids.append('item-2')

        # Manager's state should be unchanged
        assert self.manager.get_selection('collection') == ['item-1']

    def test_metadata_mutation_isolation(self):
        """Test that metadata mutations don't affect stored state"""
        metadata = [{'name': 'Document', 'data': 'original'}]
        self.manager.set_selection('collection', ['item-1'], metadata=metadata)

        # Modify original metadata
        metadata[0]['data'] = 'modified'

        # Retrieved metadata should be unchanged
        retrieved = self.manager.get_selection_metadata('collection')
        assert retrieved[0]['data'] == 'original'


class TestPhase1AppIntegration:
    """Tests for SelectionManager integration with FicheroApp"""

    def test_selection_manager_in_app_imports(self):
        """Test that SelectionManager is importable from app context"""
        # This verifies the import chain works
        from fichero.shared.selection import SelectionManager, SelectionContext, SelectionState

        assert SelectionManager is not None
        assert SelectionContext is not None
        assert SelectionState is not None

    def test_navigation_events_has_selection_changed(self):
        """Test that NavigationEvents has SELECTION_CHANGED constant"""
        from fichero.shared.navigation.navigation_event_bus import NavigationEvents

        assert hasattr(NavigationEvents, 'SELECTION_CHANGED')
        assert NavigationEvents.SELECTION_CHANGED == "selection_changed"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
