"""
Unit tests for LayoutManager (PHASE 4)

Tests layout switching, pane management, and state synchronization.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from fichero.windows.main.views.output.layout_manager import LayoutManager, LayoutType


class TestLayoutManager:
    """Test LayoutManager functionality"""

    @pytest.fixture
    def mock_library_manager(self):
        """Create mock library manager"""
        manager = Mock()
        manager.get_item_output_data = AsyncMock()
        return manager

    @pytest.fixture
    def mock_renderer_registry(self):
        """Create mock renderer registry"""
        return Mock()

    @pytest.fixture
    def layout_manager(self, mock_library_manager, mock_renderer_registry):
        """Create LayoutManager instance"""
        with patch('fichero.windows.main.views.output.layout_manager.OutputPane'):
            return LayoutManager(mock_library_manager, mock_renderer_registry)

    # ==================== INITIALIZATION TESTS ====================

    def test_init_sets_defaults(self, layout_manager):
        """Test initialization sets default values"""
        assert layout_manager.current_layout == LayoutType.SINGLE
        assert layout_manager.library_manager is not None
        assert layout_manager.renderer_registry is not None
        assert layout_manager._container is not None

    def test_init_creates_single_pane_by_default(self, layout_manager):
        """Test initialization creates single pane layout"""
        assert layout_manager.get_pane_count() == 1
        assert layout_manager.get_primary_pane() is not None

    # ==================== LAYOUT SWITCHING TESTS ====================

    def test_set_layout_single(self, layout_manager):
        """Test switching to SINGLE layout"""
        layout_manager.set_layout(LayoutType.SINGLE)

        assert layout_manager.current_layout == LayoutType.SINGLE
        assert layout_manager.get_pane_count() == 1

    def test_set_layout_dual(self, layout_manager):
        """Test switching to DUAL layout (Output | Inspector)"""
        layout_manager.set_layout(LayoutType.DUAL)

        assert layout_manager.current_layout == LayoutType.DUAL
        assert layout_manager.get_pane_count() == 1  # Inspector managed separately

    def test_set_layout_dual_compare(self, layout_manager):
        """Test switching to DUAL_COMPARE layout (Output | Output)"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)

        assert layout_manager.current_layout == LayoutType.DUAL_COMPARE
        assert layout_manager.get_pane_count() == 2

    def test_set_layout_triple(self, layout_manager):
        """Test switching to TRIPLE layout (Output | Inspector | Output)"""
        layout_manager.set_layout(LayoutType.TRIPLE)

        assert layout_manager.current_layout == LayoutType.TRIPLE
        assert layout_manager.get_pane_count() == 2  # Inspector in middle, managed separately

    def test_set_layout_quad(self, layout_manager):
        """Test switching to QUAD layout (Output | Inspector | Output | Inspector)"""
        layout_manager.set_layout(LayoutType.QUAD)

        assert layout_manager.current_layout == LayoutType.QUAD
        assert layout_manager.get_pane_count() == 2  # Inspectors managed separately

    def test_set_layout_clears_old_panes(self, layout_manager):
        """Test that switching layout clears old panes"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)
        assert layout_manager.get_pane_count() == 2

        layout_manager.set_layout(LayoutType.SINGLE)
        assert layout_manager.get_pane_count() == 1

    # ==================== PANE ACCESS TESTS ====================

    def test_get_primary_pane(self, layout_manager):
        """Test getting primary pane"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)

        primary = layout_manager.get_primary_pane()
        assert primary is not None
        assert primary == layout_manager.get_pane(0)

    def test_get_pane_valid_index(self, layout_manager):
        """Test getting pane by valid index"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)

        pane0 = layout_manager.get_pane(0)
        pane1 = layout_manager.get_pane(1)

        assert pane0 is not None
        assert pane1 is not None
        assert pane0 != pane1

    def test_get_pane_invalid_index(self, layout_manager):
        """Test getting pane by invalid index returns None"""
        layout_manager.set_layout(LayoutType.SINGLE)

        assert layout_manager.get_pane(5) is None
        assert layout_manager.get_pane(-1) is None

    def test_get_all_panes(self, layout_manager):
        """Test getting all panes"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)

        panes = layout_manager.get_all_panes()
        assert len(panes) == 2
        assert isinstance(panes, list)

    def test_get_pane_count(self, layout_manager):
        """Test getting pane count"""
        layout_manager.set_layout(LayoutType.SINGLE)
        assert layout_manager.get_pane_count() == 1

        layout_manager.set_layout(LayoutType.DUAL_COMPARE)
        assert layout_manager.get_pane_count() == 2

    # ==================== CONTAINER TESTS ====================

    def test_get_container(self, layout_manager):
        """Test getting container for embedding"""
        container = layout_manager.get_container()
        assert container is not None
        assert container == layout_manager._container

    # ==================== STATE SYNC TESTS ====================

    def test_sync_pane_state(self, layout_manager):
        """Test syncing viewer state across panes"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)

        # Mock panes with state methods
        pane0 = layout_manager.get_pane(0)
        pane1 = layout_manager.get_pane(1)

        pane0.get_viewer_state = Mock(return_value={
            'scale': 1.5,
            'rotation': 90,
            'scroll_x': 100,
            'scroll_y': 200
        })
        pane0.set_viewer_state = Mock()
        pane1.set_viewer_state = Mock()

        # Sync from pane 0
        layout_manager.sync_pane_state(pane0)

        # Pane 1 should receive the state
        pane1.set_viewer_state.assert_called_once()

    # ==================== PANE SETTING TESTS ====================

    @pytest.mark.asyncio
    async def test_set_all_panes(self, layout_manager):
        """Test setting all panes to same step"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)

        # Mock set_step on all panes
        for pane in layout_manager.get_all_panes():
            pane.set_step = AsyncMock()

        await layout_manager.set_all_panes("item-123", 2)

        # All panes should be set
        for pane in layout_manager.get_all_panes():
            pane.set_step.assert_called_once_with("item-123", 2)

    @pytest.mark.asyncio
    async def test_set_pane_step_valid_index(self, layout_manager):
        """Test setting specific pane to a step"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)

        pane0 = layout_manager.get_pane(0)
        pane0.set_step = AsyncMock()

        await layout_manager.set_pane_step(0, "item-123", 1)

        pane0.set_step.assert_called_once_with("item-123", 1)

    @pytest.mark.asyncio
    async def test_set_pane_step_invalid_index(self, layout_manager):
        """Test setting pane with invalid index does nothing"""
        layout_manager.set_layout(LayoutType.SINGLE)

        # Should not raise error
        await layout_manager.set_pane_step(5, "item-123", 1)

    # ==================== CLEAR TESTS ====================

    def test_clear_all_panes(self, layout_manager):
        """Test clearing all panes"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)

        # Mock clear on all panes
        for pane in layout_manager.get_all_panes():
            pane.clear = Mock()

        layout_manager.clear_all_panes()

        # All panes should be cleared
        for pane in layout_manager.get_all_panes():
            pane.clear.assert_called_once()

    # ==================== LAYOUT TYPE TESTS ====================

    def test_get_layout_type(self, layout_manager):
        """Test getting current layout type"""
        layout_manager.set_layout(LayoutType.TRIPLE)
        assert layout_manager.get_layout_type() == LayoutType.TRIPLE

    # ==================== COMPARISON SUPPORT TESTS ====================

    def test_supports_comparison_single(self, layout_manager):
        """Test SINGLE layout does not support comparison"""
        layout_manager.set_layout(LayoutType.SINGLE)
        assert layout_manager.supports_comparison() is False

    def test_supports_comparison_dual(self, layout_manager):
        """Test DUAL layout does not support comparison"""
        layout_manager.set_layout(LayoutType.DUAL)
        assert layout_manager.supports_comparison() is False

    def test_supports_comparison_dual_compare(self, layout_manager):
        """Test DUAL_COMPARE layout supports comparison"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)
        assert layout_manager.supports_comparison() is True

    def test_supports_comparison_triple(self, layout_manager):
        """Test TRIPLE layout supports comparison"""
        layout_manager.set_layout(LayoutType.TRIPLE)
        assert layout_manager.supports_comparison() is True

    def test_supports_comparison_quad(self, layout_manager):
        """Test QUAD layout supports comparison"""
        layout_manager.set_layout(LayoutType.QUAD)
        assert layout_manager.supports_comparison() is True

    # ==================== COMPARISON PANE INDICES TESTS ====================

    def test_get_comparison_pane_indices_single(self, layout_manager):
        """Test comparison indices for SINGLE layout"""
        layout_manager.set_layout(LayoutType.SINGLE)
        indices = layout_manager.get_comparison_pane_indices()
        assert indices == [0]

    def test_get_comparison_pane_indices_dual_compare(self, layout_manager):
        """Test comparison indices for DUAL_COMPARE layout"""
        layout_manager.set_layout(LayoutType.DUAL_COMPARE)
        indices = layout_manager.get_comparison_pane_indices()
        assert indices == [0, 1]

    def test_get_comparison_pane_indices_triple(self, layout_manager):
        """Test comparison indices for TRIPLE layout"""
        layout_manager.set_layout(LayoutType.TRIPLE)
        indices = layout_manager.get_comparison_pane_indices()
        assert indices == [0, 1]

    def test_get_comparison_pane_indices_quad(self, layout_manager):
        """Test comparison indices for QUAD layout"""
        layout_manager.set_layout(LayoutType.QUAD)
        indices = layout_manager.get_comparison_pane_indices()
        assert indices == [0, 1]
