"""
Tests for CollectionView search filter functionality.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestCollectionViewSearchFilter:
    """Tests for CollectionView.apply_search_filter and clear_search_filter"""

    def _create_mock_collection_view(self):
        """Create a mock CollectionView with search filter attributes"""
        mock_view = Mock()
        mock_view.collection_items = [
            {'id': 'item1', 'name': 'Document 1', 'type': 'file'},
            {'id': 'item2', 'name': 'Document 2', 'type': 'file'},
            {'id': 'item3', 'name': 'Folder A', 'type': 'folder'},
            {'id': 'item4', 'name': 'Document 3', 'type': 'file'},
        ]
        mock_view._all_items = []
        mock_view._search_query = None
        mock_view._search_item_ids = None
        mock_view._update_items_list = Mock()
        mock_view._update_title = Mock()
        return mock_view

    def test_apply_search_filter_stores_original_items(self):
        """Test that apply_search_filter stores original items before filtering"""
        # Import the actual method
        from fichero.windows.main.views.collection.collection_view import CollectionView

        mock_view = self._create_mock_collection_view()
        original_items = list(mock_view.collection_items)
        matching_ids = {'item1', 'item3'}

        # Call the method bound to mock
        CollectionView.apply_search_filter(mock_view, 'test query', matching_ids)

        # Verify original items were stored
        assert mock_view._all_items == original_items
        assert mock_view._search_query == 'test query'
        assert mock_view._search_item_ids == matching_ids

    def test_apply_search_filter_filters_items(self):
        """Test that apply_search_filter correctly filters items"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        mock_view = self._create_mock_collection_view()
        matching_ids = {'item1', 'item3'}

        CollectionView.apply_search_filter(mock_view, 'test query', matching_ids)

        # Verify only matching items remain
        assert len(mock_view.collection_items) == 2
        item_ids = {item['id'] for item in mock_view.collection_items}
        assert item_ids == {'item1', 'item3'}

    def test_apply_search_filter_with_empty_matches(self):
        """Test that apply_search_filter handles empty match set"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        mock_view = self._create_mock_collection_view()
        matching_ids = set()  # No matches

        CollectionView.apply_search_filter(mock_view, 'no results', matching_ids)

        # Verify items are empty
        assert len(mock_view.collection_items) == 0
        assert mock_view._search_query == 'no results'

    def test_clear_search_filter_restores_items(self):
        """Test that clear_search_filter restores original items"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        mock_view = self._create_mock_collection_view()
        original_items = list(mock_view.collection_items)

        # First apply filter
        CollectionView.apply_search_filter(mock_view, 'test', {'item1'})
        assert len(mock_view.collection_items) == 1

        # Then clear filter
        CollectionView.clear_search_filter(mock_view)

        # Verify items are restored
        assert len(mock_view.collection_items) == len(original_items)
        assert mock_view._search_query is None
        assert mock_view._search_item_ids is None

    def test_clear_search_filter_noop_when_no_filter_active(self):
        """Test that clear_search_filter does nothing when no filter is active"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        mock_view = self._create_mock_collection_view()
        original_items = list(mock_view.collection_items)

        # Clear without applying filter first
        CollectionView.clear_search_filter(mock_view)

        # Verify nothing changed
        assert mock_view.collection_items == original_items
        mock_view._update_items_list.assert_not_called()

    def test_is_search_active(self):
        """Test is_search_active method"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        mock_view = self._create_mock_collection_view()

        # Initially no search active
        assert CollectionView.is_search_active(mock_view) == False

        # Apply filter
        CollectionView.apply_search_filter(mock_view, 'test', {'item1'})
        assert CollectionView.is_search_active(mock_view) == True

        # Clear filter
        CollectionView.clear_search_filter(mock_view)
        assert CollectionView.is_search_active(mock_view) == False


class TestSearchFilterIntegration:
    """Integration tests for search filter with LibraryView"""

    def test_search_filter_clears_on_collection_change(self):
        """Test that search filter is cleared when collection changes"""
        from fichero.windows.main.views.collection.collection_view import CollectionView

        mock_view = Mock()
        mock_view._search_query = 'old query'
        mock_view._search_item_ids = {'item1'}
        mock_view._all_items = [{'id': 'item1'}]
        mock_view._load_collection_items = Mock()

        # Call set_collection_id
        CollectionView.set_collection_id(mock_view, 'new_collection_123')

        # Verify search state was cleared
        assert mock_view._search_query is None
        assert mock_view._search_item_ids is None
        assert mock_view._all_items == []
        assert mock_view.collection_id == 'new_collection_123'
