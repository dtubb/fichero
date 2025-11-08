"""
LayoutManager - Split view layout management

PHASE 4: Manages split view layouts for OutputView.
Creates and arranges OutputPane instances for different layout configurations.
"""

import logging
from typing import List, Optional
from enum import Enum

import toga
from toga.style import Pack

from .output_pane import OutputPane

logger = logging.getLogger(__name__)


class LayoutType(Enum):
    """Supported layout types (PHASE 4)"""
    SINGLE = "single"                    # [Output]
    DUAL = "dual"                        # [Output | Inspector]
    DUAL_COMPARE = "dual_compare"        # [Output | Output]
    TRIPLE = "triple"                    # [Output | Inspector | Output]
    QUAD = "quad"                        # [Output | Inspector | Output | Inspector]

    # NEW: 4-pane split layouts (PHASE 5)
    QUAD_SPLIT_H = "quad_split_h"        # [Output | Output]
                                          # [Output | Output] (2x2 grid)
    QUAD_SPLIT_V = "quad_split_v"        # [Output | Output | Output | Output] (1x4)
    TRIPLE_SPLIT_H = "triple_split_h"    # [Output | Output]
                                          # [Output] (3 panes: 2 top, 1 bottom)
    TRIPLE_SPLIT_V = "triple_split_v"    # [Output | Output | Output] (1x3)


class LayoutManager:
    """
    Manages split view layouts for OutputView (PHASE 4).

    Creates and arranges OutputPane instances.
    Handles layout switching and pane synchronization.

    Example:
        manager = LayoutManager(library_manager, renderer_registry)

        # Single pane
        manager.set_layout(LayoutType.SINGLE)
        await manager.get_primary_pane().set_step(item_id, step_index)

        # Dual pane comparison
        manager.set_layout(LayoutType.DUAL_COMPARE)
        await manager.get_pane(0).set_step(item_id, step_index=0)
        await manager.get_pane(1).set_step(item_id, step_index=1)
    """

    def __init__(self, library_manager, renderer_registry):
        """
        Initialize layout manager.

        Args:
            library_manager: LibraryManager instance for data access
            renderer_registry: RendererRegistry instance for rendering
        """
        self.library_manager = library_manager
        self.renderer_registry = renderer_registry
        self.logger = logging.getLogger(__name__)

        # Current state
        self.current_layout: LayoutType = LayoutType.SINGLE
        self.panes: List[OutputPane] = []

        # Focus tracking (PHASE 5)
        self.focused_pane_index: int = 0

        # UI components
        self._container = None
        self._build_ui()

        # Initialize with single pane
        self.set_layout(LayoutType.SINGLE)

    def _build_ui(self):
        """Build container for panes"""
        self._container = toga.Box(
            style=Pack(
                direction='row',
                flex=1
            )
        )

    def set_layout(self, layout_type: LayoutType):
        """
        Switch to a different layout.

        Creates/removes panes as needed.

        Args:
            layout_type: Type of layout to use
        """
        self.logger.info(f"Setting layout to: {layout_type.value}")

        # Store old layout
        old_layout = self.current_layout
        self.current_layout = layout_type

        # Clear container
        self._container.clear()

        # Clear existing panes
        self.panes = []

        # Create panes based on layout
        if layout_type == LayoutType.SINGLE:
            self._create_single_layout()
        elif layout_type == LayoutType.DUAL:
            self._create_dual_layout()
        elif layout_type == LayoutType.DUAL_COMPARE:
            self._create_dual_compare_layout()
        elif layout_type == LayoutType.TRIPLE:
            self._create_triple_layout()
        elif layout_type == LayoutType.QUAD:
            self._create_quad_layout()
        # NEW: 4-pane split layouts (PHASE 5)
        elif layout_type == LayoutType.QUAD_SPLIT_H:
            self._create_quad_split_h_layout()
        elif layout_type == LayoutType.QUAD_SPLIT_V:
            self._create_quad_split_v_layout()
        elif layout_type == LayoutType.TRIPLE_SPLIT_H:
            self._create_triple_split_h_layout()
        elif layout_type == LayoutType.TRIPLE_SPLIT_V:
            self._create_triple_split_v_layout()
        else:
            self.logger.warning(f"Unknown layout type: {layout_type}")
            self._create_single_layout()

        # Set initial focus to first pane
        if self.panes:
            self.set_focused_pane(0)

        self.logger.info(f"Layout set to {layout_type.value} with {len(self.panes)} panes")

    def _create_single_layout(self):
        """Create single pane layout: [Output]"""
        pane = self._create_pane()
        self.panes.append(pane)
        self._container.add(pane.as_box())

    def _create_dual_layout(self):
        """
        Create dual pane layout: [Output | Inspector].

        NOTE: Inspector is managed by OutputView, not here.
        This just creates the output pane on the left.
        """
        pane = self._create_pane()
        self.panes.append(pane)
        self._container.add(pane.as_box())

    def _create_dual_compare_layout(self):
        """Create dual comparison layout: [Output | Output]"""
        # Left pane
        left_pane = self._create_pane()
        self.panes.append(left_pane)

        # Right pane
        right_pane = self._create_pane()
        self.panes.append(right_pane)

        # Add both with equal flex
        self._container.add(left_pane.as_box())
        self._container.add(right_pane.as_box())

    def _create_triple_layout(self):
        """Create triple pane layout: [Output | Inspector | Output]"""
        # Left pane
        left_pane = self._create_pane()
        self.panes.append(left_pane)

        # Right pane
        right_pane = self._create_pane()
        self.panes.append(right_pane)

        # Add both (inspector goes in middle, managed by OutputView)
        self._container.add(left_pane.as_box())
        # Inspector added by OutputView
        self._container.add(right_pane.as_box())

    def _create_quad_layout(self):
        """Create quad pane layout: [Output | Inspector | Output | Inspector]"""
        # Left pane
        left_pane = self._create_pane()
        self.panes.append(left_pane)

        # Right pane
        right_pane = self._create_pane()
        self.panes.append(right_pane)

        # Add both (inspectors managed by OutputView)
        self._container.add(left_pane.as_box())
        # Inspector 1 added by OutputView
        self._container.add(right_pane.as_box())
        # Inspector 2 added by OutputView

    def _create_quad_split_h_layout(self):
        """
        Create quad horizontal split layout: 2x2 grid (PHASE 5)

        [Output | Output]
        [Output | Output]
        """
        # Change container direction to column for rows
        self._container.style.direction = 'column'

        # Top row
        top_row = toga.Box(style=Pack(direction='row', flex=1))
        top_left = self._create_pane()
        top_right = self._create_pane()
        self.panes.extend([top_left, top_right])
        top_row.add(top_left.as_box())
        top_row.add(top_right.as_box())

        # Bottom row
        bottom_row = toga.Box(style=Pack(direction='row', flex=1))
        bottom_left = self._create_pane()
        bottom_right = self._create_pane()
        self.panes.extend([bottom_left, bottom_right])
        bottom_row.add(bottom_left.as_box())
        bottom_row.add(bottom_right.as_box())

        # Add rows to container
        self._container.add(top_row)
        self._container.add(bottom_row)

    def _create_quad_split_v_layout(self):
        """
        Create quad vertical split layout: 1x4 (PHASE 5)

        [Output | Output | Output | Output]
        """
        # Container already has direction=row
        pane1 = self._create_pane()
        pane2 = self._create_pane()
        pane3 = self._create_pane()
        pane4 = self._create_pane()

        self.panes.extend([pane1, pane2, pane3, pane4])

        self._container.add(pane1.as_box())
        self._container.add(pane2.as_box())
        self._container.add(pane3.as_box())
        self._container.add(pane4.as_box())

    def _create_triple_split_h_layout(self):
        """
        Create triple horizontal split layout: 2 top, 1 bottom (PHASE 5)

        [Output | Output]
        [   Output     ]
        """
        # Change container direction to column for rows
        self._container.style.direction = 'column'

        # Top row (2 panes)
        top_row = toga.Box(style=Pack(direction='row', flex=1))
        top_left = self._create_pane()
        top_right = self._create_pane()
        self.panes.extend([top_left, top_right])
        top_row.add(top_left.as_box())
        top_row.add(top_right.as_box())

        # Bottom pane (full width)
        bottom_pane = self._create_pane()
        self.panes.append(bottom_pane)

        # Add to container
        self._container.add(top_row)
        self._container.add(bottom_pane.as_box())

    def _create_triple_split_v_layout(self):
        """
        Create triple vertical split layout: 1x3 (PHASE 5)

        [Output | Output | Output]
        """
        # Container already has direction=row
        pane1 = self._create_pane()
        pane2 = self._create_pane()
        pane3 = self._create_pane()

        self.panes.extend([pane1, pane2, pane3])

        self._container.add(pane1.as_box())
        self._container.add(pane2.as_box())
        self._container.add(pane3.as_box())

    def _create_pane(self) -> OutputPane:
        """
        Create a new output pane.

        Returns:
            New OutputPane instance
        """
        return OutputPane(self.library_manager, self.renderer_registry)

    def _rebuild_layout_simple(self, direction: str):
        """
        Rebuild layout with all panes in a simple row or column (PHASE 5).

        This is a simple implementation that arranges all panes in a single direction.
        Future versions can support more complex nested layouts.

        Args:
            direction: 'row' (horizontal) or 'column' (vertical)
        """
        # Clear the container
        self._container.clear()

        # Set container direction
        self._container.style.direction = direction

        # Add all panes to the container
        for pane in self.panes:
            self._container.add(pane.as_box())

        self.logger.debug(f"Rebuilt layout with {len(self.panes)} panes in {direction} direction")

    def get_container(self) -> toga.Box:
        """
        Get the layout container for embedding.

        Returns:
            Toga Box containing all panes
        """
        return self._container

    def get_primary_pane(self) -> Optional[OutputPane]:
        """
        Get the main/primary output pane.

        Returns:
            Primary OutputPane or None if no panes
        """
        return self.panes[0] if self.panes else None

    def get_pane(self, index: int) -> Optional[OutputPane]:
        """
        Get pane by index.

        Args:
            index: Pane index

        Returns:
            OutputPane at index or None if out of range
        """
        return self.panes[index] if 0 <= index < len(self.panes) else None

    def get_all_panes(self) -> List[OutputPane]:
        """
        Get all active panes.

        Returns:
            List of all OutputPane instances
        """
        return self.panes.copy()

    def get_pane_count(self) -> int:
        """
        Get number of active panes.

        Returns:
            Number of panes
        """
        return len(self.panes)

    def sync_pane_state(self, source_pane: OutputPane):
        """
        Sync viewer state (zoom, rotation) across all panes.

        Used when user wants same zoom level in multiple views.

        Args:
            source_pane: Pane to copy state from
        """
        state = source_pane.get_viewer_state()

        for pane in self.panes:
            if pane != source_pane:
                pane.set_viewer_state(state)

        self.logger.debug(f"Synced viewer state across {len(self.panes)} panes")

    async def set_all_panes(self, item_id: str, step_index: int):
        """
        Set all panes to display the same step.

        Args:
            item_id: Library item ID
            step_index: Step index to display
        """
        for pane in self.panes:
            await pane.set_step(item_id, step_index)

    async def set_pane_step(self, pane_index: int, item_id: str, step_index: int):
        """
        Set a specific pane to display a step.

        Args:
            pane_index: Index of pane to update
            item_id: Library item ID
            step_index: Step index to display
        """
        pane = self.get_pane(pane_index)
        if pane:
            await pane.set_step(item_id, step_index)
        else:
            self.logger.warning(f"Pane index {pane_index} out of range")

    def clear_all_panes(self):
        """Clear content from all panes"""
        for pane in self.panes:
            pane.clear()

    def get_layout_type(self) -> LayoutType:
        """
        Get current layout type.

        Returns:
            Current LayoutType
        """
        return self.current_layout

    def supports_comparison(self) -> bool:
        """
        Check if current layout supports side-by-side comparison.

        Returns:
            True if layout has multiple output panes
        """
        return self.current_layout in [
            LayoutType.DUAL_COMPARE,
            LayoutType.TRIPLE,
            LayoutType.QUAD,
            # PHASE 5: New split layouts
            LayoutType.QUAD_SPLIT_H,
            LayoutType.QUAD_SPLIT_V,
            LayoutType.TRIPLE_SPLIT_H,
            LayoutType.TRIPLE_SPLIT_V
        ]

    def get_comparison_pane_indices(self) -> List[int]:
        """
        Get indices of panes suitable for comparison.

        Returns:
            List of pane indices
        """
        if self.current_layout == LayoutType.DUAL_COMPARE:
            return [0, 1]
        elif self.current_layout == LayoutType.TRIPLE:
            return [0, 1]
        elif self.current_layout == LayoutType.QUAD:
            return [0, 1]
        else:
            return [0]

    # ===== FOCUS MANAGEMENT (PHASE 5) =====

    def set_focused_pane(self, pane_index: int):
        """
        Set which pane has focus.

        Args:
            pane_index: Index of pane to focus
        """
        if 0 <= pane_index < len(self.panes):
            # Update all panes to show/hide focus indicator
            for i, pane in enumerate(self.panes):
                pane.set_focused(i == pane_index)

            self.focused_pane_index = pane_index
            self.logger.debug(f"Focus set to pane {pane_index}")

            # Emit event for inspector to follow
            try:
                from fichero.shared.navigation.navigation_event_bus import emit_navigation_event
                emit_navigation_event("PANE_FOCUS_CHANGED", {
                    'pane_index': pane_index,
                    'pane': self.panes[pane_index]
                })
            except Exception as e:
                self.logger.error(f"Failed to emit pane focus event: {e}")
        else:
            self.logger.warning(f"Pane index {pane_index} out of range")

    def get_focused_pane(self) -> Optional[OutputPane]:
        """
        Get currently focused pane.

        Returns:
            Focused OutputPane or None if no panes
        """
        if 0 <= self.focused_pane_index < len(self.panes):
            return self.panes[self.focused_pane_index]
        return None

    def get_focused_pane_index(self) -> int:
        """
        Get index of currently focused pane.

        Returns:
            Index of focused pane
        """
        return self.focused_pane_index

    # ===== SPLIT PANE OPERATIONS (PHASE 5) =====

    def split_pane_horizontal(self, pane_index: int):
        """
        Split a pane horizontally (top/bottom) - PHASE 5 Dynamic Splitting.

        Args:
            pane_index: Index of pane to split
        """
        self.logger.info(f"split_pane_horizontal() called for pane {pane_index}")

        # Simple approach: add a new pane below the focused one
        # This creates a simple horizontal split
        new_pane = self._create_pane()
        self.panes.append(new_pane)

        # For now, rebuild the entire layout as a vertical stack
        # (All panes stacked vertically)
        self._rebuild_layout_simple('column')

        # Set focus to the new pane
        self.set_focused_pane(len(self.panes) - 1)

        self.logger.info(f"Added pane {len(self.panes) - 1} (horizontal split)")

    def split_pane_vertical(self, pane_index: int):
        """
        Split a pane vertically (side by side) - PHASE 5 Dynamic Splitting.

        Args:
            pane_index: Index of pane to split
        """
        self.logger.info(f"split_pane_vertical() called for pane {pane_index}")

        # Simple approach: add a new pane to the right of the focused one
        # This creates a simple vertical split
        new_pane = self._create_pane()
        self.panes.append(new_pane)

        # For now, rebuild the entire layout as a horizontal row
        # (All panes side by side)
        self._rebuild_layout_simple('row')

        # Set focus to the new pane
        self.set_focused_pane(len(self.panes) - 1)

        self.logger.info(f"Added pane {len(self.panes) - 1} (vertical split)")

    def close_pane(self, pane_index: int):
        """
        Close a specific pane (NOT YET IMPLEMENTED - Phase 5).

        This will be implemented in Phase 5 to dynamically close panes.
        For now, use set_layout() to switch to layouts with fewer panes.

        Args:
            pane_index: Index of pane to close
        """
        self.logger.info(f"close_pane() called for pane {pane_index}")
        self.logger.warning("Dynamic pane closing not yet implemented - use set_layout() instead")
        # TODO: Implement dynamic pane closing in Phase 5
