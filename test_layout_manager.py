#!/usr/bin/env python3
"""
Quick test script for LayoutManager Phase 1 changes.

Tests that new layout types can be created without errors.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from fichero.windows.main.views.output.layout_manager import LayoutManager, LayoutType


class MockLibraryManager:
    """Mock library manager for testing"""
    pass


class MockRendererRegistry:
    """Mock renderer registry for testing"""
    pass


def test_layout_types():
    """Test that all layout types can be created"""
    print("Testing LayoutManager Phase 1...")
    print("-" * 60)

    # Create manager with mocks
    lib_mgr = MockLibraryManager()
    renderer = MockRendererRegistry()
    manager = LayoutManager(lib_mgr, renderer)

    # Test all layout types
    layouts_to_test = [
        LayoutType.SINGLE,
        LayoutType.DUAL,
        LayoutType.DUAL_COMPARE,
        LayoutType.TRIPLE,
        LayoutType.QUAD,
        # New Phase 5 layouts
        LayoutType.QUAD_SPLIT_H,
        LayoutType.QUAD_SPLIT_V,
        LayoutType.TRIPLE_SPLIT_H,
        LayoutType.TRIPLE_SPLIT_V
    ]

    for layout_type in layouts_to_test:
        try:
            manager.set_layout(layout_type)
            pane_count = manager.get_pane_count()
            focused_idx = manager.get_focused_pane_index()
            supports_comp = manager.supports_comparison()

            print(f"✓ {layout_type.value:20s} | {pane_count} panes | Focus: {focused_idx} | Comparison: {supports_comp}")
        except Exception as e:
            print(f"✗ {layout_type.value:20s} | ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

    print("-" * 60)
    print("All layout types created successfully!")
    print("\nFocus management test...")

    # Test focus management
    manager.set_layout(LayoutType.QUAD_SPLIT_V)  # 4 panes
    for i in range(4):
        manager.set_focused_pane(i)
        assert manager.get_focused_pane_index() == i, f"Focus index mismatch: expected {i}, got {manager.get_focused_pane_index()}"
        print(f"✓ Focus set to pane {i}")

    print("\nPhase 1 tests PASSED!")
    return True


if __name__ == "__main__":
    success = test_layout_types()
    sys.exit(0 if success else 1)
