"""
LayoutManager - Split view layout management

PHASE 4: Manages split view layouts for OutputView.
Creates and arranges OutputPane instances for different layout configurations.
"""

import logging
from typing import List, Optional, Dict, Any
from enum import Enum

import toga
from toga.style import Pack

from .output_pane import OutputPane
from fichero.shared.navigation.navigation_event_bus import emit_navigation_event

logger = logging.getLogger(__name__)


class ColumnContainer:
    """
    Container for a single column of panes (PHASE 5).

    Each column can have multiple panes stacked vertically.
    """

    def __init__(self, max_panes_per_column: int = 3):
        self.panes: List[OutputPane] = []
        self.container: Optional[toga.Box] = None
        self.max_panes: int = max_panes_per_column

    def add_pane(self, pane: OutputPane) -> bool:
        """Add a pane to this column. Returns False if max limit reached."""
        if len(self.panes) >= self.max_panes:
            return False
        self.panes.append(pane)
        return True

    def remove_pane(self, pane_index: int):
        """Remove a pane from this column."""
        if 0 <= pane_index < len(self.panes):
            self.panes.pop(pane_index)

    def rebuild_layout(self):
        """
        Rebuild this column's layout with all panes equally sized.

        Uses flex-based layout for responsive resizing.
        """
        if not self.container:
            # Create container with flex=1 for responsive width
            self.container = toga.Box(style=Pack(direction='column', flex=1))

        self.container.clear()
        for pane in self.panes:
            pane_box = pane.as_box()
            pane_box.style.flex = 1  # Equal height
            self.container.add(pane_box)


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

    # FEATURE 1: Universal split layouts with directional naming
    # SPLIT_V = vertical columns (side-by-side)
    # SPLIT_H = horizontal rows (stacked)
    SPLIT_V = "split_v"                  # Split right (add column to right)
    SPLIT_H = "split_h"                  # Split down (add row below)
    SPLIT_V_LEFT = "split_v_left"        # Split left (add column to left)
    SPLIT_H_UP = "split_h_up"            # Split up (add row above)
    MOVE_TO_WINDOW = "move_to_window"    # Move pane to new window
    COPY_TO_WINDOW = "copy_to_window"    # Copy pane to new window


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

    def __init__(self, library_manager, renderer_registry, status_bar=None):
        """
        Initialize layout manager.

        Args:
            library_manager: LibraryManager instance for data access
            renderer_registry: RendererRegistry instance for rendering
            status_bar: Optional StatusBar instance for status updates (PHASE 5)
        """
        self.library_manager = library_manager
        self.renderer_registry = renderer_registry
        self.status_bar = status_bar
        self.logger = logging.getLogger(__name__)

        # Current state
        self.current_layout: LayoutType = LayoutType.SINGLE

        # PHASE 5: Column-based architecture
        self.columns: List[ColumnContainer] = []
        self.focused_column_index: int = 0
        self.focused_pane_index: int = 0  # Pane within focused column

        # Backward compatibility: keep panes list for old layout methods
        self.panes: List[OutputPane] = []

        # PHASE 5: Limits
        self.max_panes_per_column: int = 3

        # UI components
        self._container = None  # Will be ScrollContainer
        self._scroll_container = None
        self._columns_container = None  # Horizontal box containing columns
        self._build_ui()

        # Initialize with single column, single pane
        self._initialize_single_column()

    def _build_ui(self):
        """Build container for columns with horizontal scroll - PHASE 5"""
        # The split structure is built dynamically using nested SplitContainers
        # Start with an empty placeholder
        self._split_structure = toga.Box(style=Pack(flex=1))

        # Scroll container - enables horizontal scrolling when many columns
        # Using ScrollContainer allows overflow, SplitContainer handles resizing
        self._scroll_container = toga.ScrollContainer(
            content=self._split_structure,
            horizontal=True,
            vertical=False,
            style=Pack(flex=1)
        )

        # Main container is the scroll container
        self._container = self._scroll_container

    def _build_split_structure(self) -> toga.Widget:
        """
        Build simple Box structure from columns with flex-based responsive layout.

        Each column gets equal flex ratio (flex=1) for equal widths.
        Users can manually adjust column widths using grow/shrink commands.

        Returns:
            Box containing all columns with flex-based layout
        """
        if not self.columns:
            return toga.Box(style=Pack(flex=1))

        if len(self.columns) == 1:
            # Single column - return directly
            self.columns[0].container.style.flex = 1
            return self.columns[0].container

        # Multiple columns - create horizontal box with flex=1 for each column
        columns_box = toga.Box(style=Pack(direction='row', flex=1))

        for column in self.columns:
            # Set each column to flex=1 for equal initial widths
            column.container.style.flex = 1
            columns_box.add(column.container)

        self.logger.debug(f"Built columns box with {len(self.columns)} columns, flex=1 each")
        return columns_box

    def _rebuild_split_structure(self):
        """Rebuild and update the split container structure"""
        # CRITICAL: Remove column containers from their current parent first
        # Toga widgets can only belong to one container at a time
        for column in self.columns:
            if column.container and hasattr(column.container, '_impl'):
                # Clear the widget's container reference
                try:
                    # Access the native implementation to force detachment
                    if hasattr(column.container._impl, 'container'):
                        column.container._impl.container = None
                except Exception as e:
                    self.logger.debug(f"Could not clear container reference: {e}")

        # Build new split structure
        new_structure = self._build_split_structure()

        # Update scroll container content
        self._scroll_container.content = new_structure
        self._split_structure = new_structure

        self.logger.debug(f"Rebuilt split structure with {len(self.columns)} columns")

    def _initialize_single_column(self):
        """Initialize with a single column containing a single pane - PHASE 5"""
        self.logger.info("Initializing with single column")

        # Create first column
        column = ColumnContainer(max_panes_per_column=self.max_panes_per_column)

        # Create first pane
        pane = self._create_pane()
        column.add_pane(pane)

        column.rebuild_layout()

        # Add column to list
        self.columns.append(column)

        # Update backward-compat panes list
        self.panes = [pane]

        # Rebuild split structure
        self._rebuild_split_structure()

        # Set focus on first pane
        self.focused_column_index = 0
        self.focused_pane_index = 0
        self._update_all_focus_indicators()  # Use column-based focus system

        self.logger.info(f"Initialized with 1 column, 1 pane")

    def set_layout(self, layout_type: LayoutType):
        """
        Switch to a different layout.

        Creates/removes panes as needed.
        PHASE 5: Now works with column-based system.

        Args:
            layout_type: Type of layout to use
        """
        self.logger.info(f"Setting layout to: {layout_type.value}")

        # Store old layout
        old_layout = self.current_layout
        self.current_layout = layout_type

        # Clear existing columns and panes
        self.columns = []
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

        # Rebuild split structure after creating columns
        self._rebuild_split_structure()

        # Set initial focus to first pane
        if self.panes:
            self.set_focused_pane(0)

        self.logger.info(f"Layout set to {layout_type.value} with {len(self.panes)} panes")

    def _create_single_layout(self):
        """Create single pane layout: [Output] - PHASE 5 uses column system"""
        # Create column with single pane
        column = ColumnContainer(max_panes_per_column=self.max_panes_per_column)
        pane = self._create_pane()
        column.add_pane(pane)
        column.rebuild_layout()

        # Add to system
        self.columns.append(column)
        self.panes.append(pane)  # Backward compat

    def _create_dual_layout(self):
        """
        Create dual pane layout: [Output | Inspector] - PHASE 5.

        NOTE: Inspector is managed by OutputView, not here.
        This just creates the output pane on the left.
        """
        # Single column with single pane (inspector added separately by OutputView)
        column = ColumnContainer(max_panes_per_column=self.max_panes_per_column)
        pane = self._create_pane()
        column.add_pane(pane)
        column.rebuild_layout()

        self.columns.append(column)
        self.panes.append(pane)

    def _create_dual_compare_layout(self):
        """Create dual comparison layout: [Output | Output] - PHASE 5"""
        # Two columns, each with one pane
        for i in range(2):
            column = ColumnContainer(max_panes_per_column=self.max_panes_per_column)
            pane = self._create_pane()
            column.add_pane(pane)
            column.rebuild_layout()

            self.columns.append(column)
            self.panes.append(pane)

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
        Create a new output pane with click handler (PHASE 5).

        Returns:
            New OutputPane instance
        """
        return OutputPane(
            self.library_manager,
            self.renderer_registry,
            on_click=self._on_pane_clicked  # PHASE 5: click-to-focus
        )

    def _on_pane_clicked(self, pane: OutputPane, meta_key=False, ctrl_key=False, shift_key=False, alt_key=False):
        """
        Handle pane click - update focus, or split if Cmd/Ctrl is pressed (PHASE 5).

        Args:
            pane: The pane that was clicked
            meta_key: Cmd key on Mac
            ctrl_key: Ctrl key on Windows/Linux
            shift_key: Shift key (modifies split direction)
            alt_key: Alt/Option key
        """
        # Find which column and pane index this is
        for col_idx, column in enumerate(self.columns):
            for pane_idx, p in enumerate(column.panes):
                if p is pane:
                    # Check if Cmd/Ctrl was pressed - trigger split
                    if meta_key or ctrl_key:
                        self.logger.info(f"Cmd/Ctrl+Click detected on pane - triggering split")

                        # Focus the clicked pane first
                        self.focused_column_index = col_idx
                        self.focused_pane_index = pane_idx
                        self._update_all_focus_indicators()

                        # Split based on Shift modifier:
                        # Shift: vertical split (down)
                        # No Shift: horizontal split (right)
                        pane_global_index = self.panes.index(pane)
                        if shift_key:
                            self.logger.info("Shift held - vertical split")
                            self.split_pane_vertical(pane_global_index)
                        else:
                            self.logger.info("No Shift - horizontal split")
                            self.split_pane_horizontal(pane_global_index)
                        return

                    # Normal click - update focus
                    self.logger.debug(f"Pane clicked: column {col_idx}, pane {pane_idx}")
                    self.focused_column_index = col_idx
                    self.focused_pane_index = pane_idx
                    self._update_all_focus_indicators()

                    # Update status bar to show which pane is selected (PHASE 5)
                    if self.status_bar:
                        total_cols = len(self.columns)
                        total_panes_in_col = len(column.panes)
                        status_text = f"Column {col_idx + 1}/{total_cols} • Pane {pane_idx + 1}/{total_panes_in_col}"
                        self.status_bar.set_status(status_text)
                        self.logger.debug(f"Status bar updated: {status_text}")

                    # Update step browser to match pane's current step (PHASE 5)
                    if hasattr(pane, 'current_step_index') and pane.current_step_index is not None:
                        self.logger.debug(f"Pane is showing step {pane.current_step_index} - updating toolbar")
                        # Emit navigation event to sync toolbar
                        from fichero.shared.navigation.navigation_event_bus import emit_navigation_event
                        emit_navigation_event('step_browser_select', {'step_index': pane.current_step_index})
                    return

        self.logger.warning("Clicked pane not found in columns")

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
        Get currently focused pane using column system.

        Returns:
            Focused OutputPane or None if no panes
        """
        if 0 <= self.focused_column_index < len(self.columns):
            column = self.columns[self.focused_column_index]
            if 0 <= self.focused_pane_index < len(column.panes):
                pane = column.panes[self.focused_pane_index]
                self.logger.debug(f"get_focused_pane: Column {self.focused_column_index}, Pane {self.focused_pane_index} -> {id(pane)}")
                return pane
        self.logger.warning(f"get_focused_pane: Invalid indices - Column {self.focused_column_index}/{len(self.columns)}, Pane {self.focused_pane_index}")
        return None

    def get_focused_pane_index(self) -> int:
        """
        Get index of currently focused pane.

        Returns:
            Index of focused pane
        """
        return self.focused_pane_index

    def _update_all_focus_indicators(self):
        """
        Update focus indicators on all panes based on current column+pane indices - PHASE 5.
        """
        self.logger.info(f"🎯 Updating focus: Column {self.focused_column_index}, Pane {self.focused_pane_index}")

        for col_idx, column in enumerate(self.columns):
            for pane_idx, pane in enumerate(column.panes):
                is_focused = (col_idx == self.focused_column_index and
                             pane_idx == self.focused_pane_index)
                pane.set_focused(is_focused)
                if is_focused:
                    self.logger.info(f"  ✅ Focused: Column {col_idx}, Pane {pane_idx}")

        # Update status bar
        if self.status_bar and self.focused_column_index < len(self.columns):
            column = self.columns[self.focused_column_index]
            total_cols = len(self.columns)
            total_panes_in_col = len(column.panes)
            status_text = f"Column {self.focused_column_index + 1}/{total_cols} • Pane {self.focused_pane_index + 1}/{total_panes_in_col}"
            self.status_bar.set_status(status_text)
            self.logger.info(f"  📊 Status bar: {status_text}")

    def cycle_focus(self, direction='next'):
        """
        Cycle focus to next/previous pane.

        Moves focus through all panes in reading order (left-to-right, top-to-bottom).

        Args:
            direction: 'next' or 'prev'
        """
        # Build flat list of (col_idx, pane_idx) tuples
        pane_positions = []
        for col_idx, column in enumerate(self.columns):
            for pane_idx in range(len(column.panes)):
                pane_positions.append((col_idx, pane_idx))

        total_panes = len(pane_positions)

        if total_panes <= 1:
            self.logger.info("Only one pane, no cycling needed")
            return  # Nothing to cycle

        try:
            # Find current position in flat list
            current_pos = pane_positions.index(
                (self.focused_column_index, self.focused_pane_index)
            )
        except ValueError:
            # Current position not found, default to first pane
            self.logger.warning(f"Current focus position ({self.focused_column_index}, {self.focused_pane_index}) not found, defaulting to first pane")
            current_pos = 0

        # Calculate next position
        if direction == 'next':
            next_pos = (current_pos + 1) % total_panes
        else:  # 'prev'
            next_pos = (current_pos - 1) % total_panes

        # Update focus
        self.focused_column_index, self.focused_pane_index = pane_positions[next_pos]
        self._update_all_focus_indicators()

        self.logger.info(f"🔄 Cycled focus {direction} to Column {self.focused_column_index + 1}, Pane {self.focused_pane_index + 1}")

    # ===== COLUMN WIDTH AND PANE HEIGHT ADJUSTMENT =====

    def grow_focused_pane(self):
        """
        Smart grow: adjusts height if pane has siblings, otherwise adjusts column width.

        If the focused pane has siblings in its column (vertical split), grows the pane's
        height by 10%. Otherwise, grows the column's width by 10%.
        """
        if not (0 <= self.focused_column_index < len(self.columns)):
            self.logger.warning(f"Invalid focused column index: {self.focused_column_index}")
            return

        column = self.columns[self.focused_column_index]

        # Check if there are multiple panes in this column (vertical split)
        if len(column.panes) > 1:
            # Adjust pane height
            self.grow_focused_pane_height()
        else:
            # Adjust column width
            self.grow_focused_column_width()

    def shrink_focused_pane(self):
        """
        Smart shrink: adjusts height if pane has siblings, otherwise adjusts column width.

        If the focused pane has siblings in its column (vertical split), shrinks the pane's
        height by 10%. Otherwise, shrinks the column's width by 10%.
        """
        if not (0 <= self.focused_column_index < len(self.columns)):
            self.logger.warning(f"Invalid focused column index: {self.focused_column_index}")
            return

        column = self.columns[self.focused_column_index]

        # Check if there are multiple panes in this column (vertical split)
        if len(column.panes) > 1:
            # Adjust pane height
            self.shrink_focused_pane_height()
        else:
            # Adjust column width
            self.shrink_focused_column_width()

    def grow_focused_pane_height(self):
        """
        Grow the focused pane's height by 10% within its column, reducing other panes proportionally.
        """
        if not (0 <= self.focused_column_index < len(self.columns)):
            self.logger.warning(f"Invalid focused column index: {self.focused_column_index}")
            return

        column = self.columns[self.focused_column_index]

        if len(column.panes) <= 1:
            self.logger.info("Cannot grow pane height - only one pane in column")
            return

        if not (0 <= self.focused_pane_index < len(column.panes)):
            self.logger.warning(f"Invalid focused pane index: {self.focused_pane_index}")
            return

        # Get current flex values for all panes in this column
        current_flex = []
        for pane in column.panes:
            pane_box = pane.as_box()
            flex = getattr(pane_box.style, 'flex', 1)
            current_flex.append(flex if flex else 1)

        total_flex = sum(current_flex)
        focused_flex = current_flex[self.focused_pane_index]

        # Calculate new flex for focused pane (10% increase)
        new_focused_flex = focused_flex * 1.1

        # Calculate remaining flex to distribute among other panes
        other_total = total_flex - focused_flex

        if other_total <= 0:
            self.logger.warning("Cannot grow - focused pane already at maximum")
            return

        # Reduce other panes proportionally
        reduction_factor = (total_flex - new_focused_flex) / other_total

        # Apply new flex values
        for i, pane in enumerate(column.panes):
            pane_box = pane.as_box()
            if i == self.focused_pane_index:
                pane_box.style.flex = new_focused_flex
                self.logger.debug(f"Pane {i}: flex={new_focused_flex:.2f} (grew by 10%)")
            else:
                new_flex = current_flex[i] * reduction_factor
                pane_box.style.flex = new_flex
                self.logger.debug(f"Pane {i}: flex={new_flex:.2f} (reduced)")

        self.logger.info(f"✅ Grew pane {self.focused_pane_index + 1} height by 10% in column {self.focused_column_index + 1}")

    def shrink_focused_pane_height(self):
        """
        Shrink the focused pane's height by 10% within its column, increasing other panes proportionally.
        """
        if not (0 <= self.focused_column_index < len(self.columns)):
            self.logger.warning(f"Invalid focused column index: {self.focused_column_index}")
            return

        column = self.columns[self.focused_column_index]

        if len(column.panes) <= 1:
            self.logger.info("Cannot shrink pane height - only one pane in column")
            return

        if not (0 <= self.focused_pane_index < len(column.panes)):
            self.logger.warning(f"Invalid focused pane index: {self.focused_pane_index}")
            return

        # Get current flex values for all panes in this column
        current_flex = []
        for pane in column.panes:
            pane_box = pane.as_box()
            flex = getattr(pane_box.style, 'flex', 1)
            current_flex.append(flex if flex else 1)

        total_flex = sum(current_flex)
        focused_flex = current_flex[self.focused_pane_index]

        # Calculate new flex for focused pane (10% decrease)
        new_focused_flex = focused_flex * 0.9

        # Minimum flex to prevent pane from disappearing
        min_flex = 0.1
        if new_focused_flex < min_flex:
            self.logger.warning("Cannot shrink - focused pane already at minimum height")
            return

        # Calculate remaining flex to distribute among other panes
        other_total = total_flex - focused_flex

        if other_total <= 0:
            self.logger.warning("Cannot shrink - no other panes to grow")
            return

        # Increase other panes proportionally
        increase_factor = (total_flex - new_focused_flex) / other_total

        # Apply new flex values
        for i, pane in enumerate(column.panes):
            pane_box = pane.as_box()
            if i == self.focused_pane_index:
                pane_box.style.flex = new_focused_flex
                self.logger.debug(f"Pane {i}: flex={new_focused_flex:.2f} (shrank by 10%)")
            else:
                new_flex = current_flex[i] * increase_factor
                pane_box.style.flex = new_flex
                self.logger.debug(f"Pane {i}: flex={new_flex:.2f} (increased)")

        self.logger.info(f"✅ Shrank pane {self.focused_pane_index + 1} height by 10% in column {self.focused_column_index + 1}")

    def grow_focused_column_width(self):
        """
        Grow the focused column by 10% width, reducing others proportionally.

        Increases the focused column's flex value by 10% while decreasing
        other columns' flex values to maintain total proportions.
        """
        if len(self.columns) <= 1:
            self.logger.info("Cannot grow column - only one column exists")
            return

        if not (0 <= self.focused_column_index < len(self.columns)):
            self.logger.warning(f"Invalid focused column index: {self.focused_column_index}")
            return

        # Get current flex values
        current_flex = []
        for column in self.columns:
            flex = getattr(column.container.style, 'flex', 1)
            current_flex.append(flex if flex else 1)

        total_flex = sum(current_flex)
        focused_flex = current_flex[self.focused_column_index]

        # Calculate new flex for focused column (10% increase)
        new_focused_flex = focused_flex * 1.1

        # Calculate remaining flex to distribute among other columns
        remaining_flex = total_flex - focused_flex  # Original total minus old focused
        other_total = remaining_flex

        if other_total <= 0:
            # Edge case: focused column already takes all flex
            self.logger.warning("Cannot grow - focused column already at maximum")
            return

        # Reduce other columns proportionally
        reduction_factor = (total_flex - new_focused_flex) / other_total

        # Apply new flex values
        for i, column in enumerate(self.columns):
            if i == self.focused_column_index:
                column.container.style.flex = new_focused_flex
                self.logger.debug(f"Column {i}: flex={new_focused_flex:.2f} (grew by 10%)")
            else:
                new_flex = current_flex[i] * reduction_factor
                column.container.style.flex = new_flex
                self.logger.debug(f"Column {i}: flex={new_flex:.2f} (reduced)")

        self.logger.info(f"✅ Grew column {self.focused_column_index + 1} by 10%")

    def shrink_focused_column_width(self):
        """
        Shrink the focused column by 10% width, increasing others proportionally.

        Decreases the focused column's flex value by 10% while increasing
        other columns' flex values to maintain total proportions.
        """
        if len(self.columns) <= 1:
            self.logger.info("Cannot shrink column - only one column exists")
            return

        if not (0 <= self.focused_column_index < len(self.columns)):
            self.logger.warning(f"Invalid focused column index: {self.focused_column_index}")
            return

        # Get current flex values
        current_flex = []
        for column in self.columns:
            flex = getattr(column.container.style, 'flex', 1)
            current_flex.append(flex if flex else 1)

        total_flex = sum(current_flex)
        focused_flex = current_flex[self.focused_column_index]

        # Calculate new flex for focused column (10% decrease)
        new_focused_flex = focused_flex * 0.9

        # Minimum flex to prevent column from disappearing
        min_flex = 0.1
        if new_focused_flex < min_flex:
            self.logger.warning(f"Cannot shrink - focused column already at minimum width")
            return

        # Calculate remaining flex to distribute among other columns
        remaining_flex = total_flex - focused_flex  # Original total minus old focused
        other_total = remaining_flex

        if other_total <= 0:
            # Edge case: only one column with flex
            self.logger.warning("Cannot shrink - no other columns to grow")
            return

        # Increase other columns proportionally
        increase_factor = (total_flex - new_focused_flex) / other_total

        # Apply new flex values
        for i, column in enumerate(self.columns):
            if i == self.focused_column_index:
                column.container.style.flex = new_focused_flex
                self.logger.debug(f"Column {i}: flex={new_focused_flex:.2f} (shrank by 10%)")
            else:
                new_flex = current_flex[i] * increase_factor
                column.container.style.flex = new_flex
                self.logger.debug(f"Column {i}: flex={new_flex:.2f} (increased)")

        self.logger.info(f"✅ Shrank column {self.focused_column_index + 1} by 10%")

    # ===== SPLIT PANE OPERATIONS (PHASE 5) =====

    def split_pane_horizontal(self, pane_index: int):
        """
        Add a new column (horizontal split) - PHASE 5 Column System.

        Creates a new column with a single pane. Unlimited columns allowed,
        horizontal scrolling appears after 4 columns (due to 1/4 window width minimum).

        Args:
            pane_index: Ignored (kept for backward compat)
        """
        self.logger.info(f"=" * 60)
        self.logger.info(f"SPLIT HORIZONTAL: Adding new column")
        self.logger.info(f"Current columns: {len(self.columns)}")

        # Create new column with new pane
        column = ColumnContainer(max_panes_per_column=self.max_panes_per_column)
        new_pane = self._create_pane()
        column.add_pane(new_pane)

        column.rebuild_layout()

        # Add column to system
        self.columns.append(column)
        self.panes.append(new_pane)  # Backward compat

        # Rebuild split structure
        self._rebuild_split_structure()

        # Focus new pane in new column
        self.focused_column_index = len(self.columns) - 1
        self.focused_pane_index = 0
        self._update_all_focus_indicators()

        self.logger.info(f"✅ Horizontal split complete. Total columns: {len(self.columns)}")
        self.logger.info(f"=" * 60)

    def split_pane_vertical(self, pane_index: int):
        """
        Split the focused column vertically (add row) - PHASE 5 Column System.

        Adds a new pane below the focused pane within the focused column.
        Maximum 3 panes per column.

        Args:
            pane_index: Ignored (kept for backward compat)
        """
        self.logger.info(f"=" * 60)
        self.logger.info(f"SPLIT VERTICAL: Adding row to focused column")
        self.logger.info(f"Current columns: {len(self.columns)}")

        # Get focused column
        if self.focused_column_index >= len(self.columns):
            self.logger.error(f"Invalid focused_column_index: {self.focused_column_index}")
            return

        column = self.columns[self.focused_column_index]

        # Check limit for this column
        if len(column.panes) >= self.max_panes_per_column:
            self.logger.warning(f"⚠️ Maximum {self.max_panes_per_column} panes per column reached")
            self.logger.info(f"=" * 60)
            return

        # Save content from this column's panes
        saved_content = []
        for pane in column.panes:
            saved_content.append({
                'item_id': pane.current_item_id,
                'step_index': pane.current_step_index
            })

        self.logger.info(f"Saved content from {len(saved_content)} panes in column {self.focused_column_index}")

        # Create new pane in column
        new_pane = self._create_pane()
        column.add_pane(new_pane)
        column.rebuild_layout()  # Rebuild just this column

        # Update global panes list
        self.panes.append(new_pane)

        # Restore content to column's panes
        for i, content in enumerate(saved_content):
            if content['item_id'] is not None:
                column.panes[i].load_item(content['item_id'], content['step_index'])

        # Focus new pane
        self.focused_pane_index = len(column.panes) - 1
        self._update_all_focus_indicators()

        self.logger.info(f"✅ Vertical split complete. Column {self.focused_column_index} now has {len(column.panes)} panes")
        self.logger.info(f"=" * 60)

    def _rebuild_equal_layout(self, direction: str):
        """
        Rebuild layout with all panes equally sized - PHASE 5 Helper.

        Args:
            direction: 'row' for columns (horizontal split), 'column' for rows (vertical split)
        """
        self.logger.info(f"Rebuilding layout with {len(self.panes)} panes, direction={direction}")

        # Clear container
        self._container.clear()

        # Update container direction
        self._container.style.direction = direction

        # Add all panes with equal flex
        for i, pane in enumerate(self.panes):
            pane_box = pane.as_box()
            pane_box.style.flex = 1  # Equal sizing
            self._container.add(pane_box)
            self.logger.info(f"Added pane {i} to container with flex=1")

        self.logger.info(f"Layout rebuild complete: {len(self.panes)} equal panes in {direction}")

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

    # ==================== STATE PERSISTENCE ====================

    def get_layout_state(self) -> Dict[str, Any]:
        """
        Get complete layout state for persistence.

        Returns:
            Dictionary containing:
            - layout_type: Current layout type (e.g., "single", "split_v")
            - columns: List of column states with flex ratios and pane contexts
            - focused_column_index: Index of focused column
            - focused_pane_index: Index of focused pane within column

        Example:
            {
                'layout_type': 'split_v',
                'columns': [
                    {
                        'flex': 1,
                        'panes': [
                            {
                                'flex': 1,
                                'context': {'item_id': '123', 'step_index': 0},
                                'viewer_state': {'scale': 1.0, 'rotation': 0}
                            }
                        ]
                    }
                ],
                'focused_column_index': 0,
                'focused_pane_index': 0
            }
        """
        state = {
            'layout_type': self.current_layout.value if self.current_layout else 'single',
            'columns': [],
            'focused_column_index': self.focused_column_index,
            'focused_pane_index': self.focused_pane_index
        }

        # Collect state from each column
        for column in self.columns:
            column_state = {
                'flex': getattr(column.container.style, 'flex', 1),
                'panes': []
            }

            for pane in column.panes:
                pane_state = {
                    'flex': getattr(pane.as_box().style, 'flex', 1),
                    'context': pane.get_context(),
                    'viewer_state': pane.get_viewer_state()
                }
                column_state['panes'].append(pane_state)

            state['columns'].append(column_state)

        self.logger.debug(f"Captured layout state: {len(state['columns'])} columns")
        return state

    async def restore_layout_state(self, state: Dict[str, Any]):
        """
        Restore layout from saved state.

        Args:
            state: Dictionary from get_layout_state() containing layout configuration

        This method:
        1. Clears the current layout
        2. Recreates columns and panes from saved state
        3. Restores content context (item_id, step_index) for each pane
        4. Restores viewer state (zoom, rotation, scroll) for each pane
        5. Restores focus to the correct pane
        """
        try:
            self.logger.info(f"Restoring layout state: {state.get('layout_type', 'unknown')} layout")

            # Clear existing layout
            self.columns = []
            self.panes = []
            if self.content_container:
                self.content_container.clear()

            # Recreate columns and panes from state
            for col_index, col_state in enumerate(state.get('columns', [])):
                column = self._create_column()

                for pane_index, pane_state in enumerate(col_state.get('panes', [])):
                    pane = self._create_pane()

                    # Restore context (item_id, step_index, etc.)
                    context = pane_state.get('context', {})
                    if context.get('item_id'):
                        await pane.set_context(context)
                        self.logger.debug(f"Restored pane context: item={context.get('item_id')}, step={context.get('step_index')}")

                    # Restore viewer state (zoom, rotation, scroll)
                    viewer_state = pane_state.get('viewer_state', {})
                    if viewer_state:
                        pane.set_viewer_state(viewer_state)
                        self.logger.debug(f"Restored viewer state: scale={viewer_state.get('scale')}, rotation={viewer_state.get('rotation')}")

                    # Set flex ratio for pane height
                    pane_flex = pane_state.get('flex', 1)
                    pane.as_box().style.flex = pane_flex

                    column.add_pane(pane)
                    self.panes.append(pane)

                # Set flex ratio for column width
                column_flex = col_state.get('flex', 1)
                column.container.style.flex = column_flex

                column.rebuild_layout()
                self.columns.append(column)

            # Rebuild split structure
            self._rebuild_split_structure()

            # Restore focus
            self.focused_column_index = state.get('focused_column_index', 0)
            self.focused_pane_index = state.get('focused_pane_index', 0)
            self._update_all_focus_indicators()

            # Update layout type
            layout_type_str = state.get('layout_type', 'single')
            try:
                self.current_layout = LayoutType(layout_type_str)
            except ValueError:
                self.logger.warning(f"Invalid layout type '{layout_type_str}', defaulting to single")
                self.current_layout = LayoutType.SINGLE

            self.logger.info(f"✅ Layout restored: {len(self.columns)} columns, {len(self.panes)} panes")

        except Exception as e:
            self.logger.error(f"Failed to restore layout state: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Fall back to single pane layout on error
            self.set_layout(LayoutType.SINGLE)
