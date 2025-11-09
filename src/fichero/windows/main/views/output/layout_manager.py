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

    def rebuild_layout(self, min_width: Optional[int] = None):
        """
        Rebuild this column's layout with all panes equally sized.

        Args:
            min_width: Optional minimum width for the column (1/4 window width)
        """
        if not self.container:
            # Create container with optional minimum width
            if min_width:
                self.container = toga.Box(style=Pack(direction='column', flex=1, width=min_width))
            else:
                self.container = toga.Box(style=Pack(direction='column', flex=1))

        # Update width if specified
        if min_width and self.container:
            self.container.style.width = min_width

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
        # Columns container - holds all columns side by side
        self._columns_container = toga.Box(
            style=Pack(
                direction='row',  # Horizontal layout for columns
                flex=1
            )
        )

        # Scroll container - enables horizontal scrolling when > 4 columns
        self._scroll_container = toga.ScrollContainer(
            content=self._columns_container,
            horizontal=True,
            vertical=False,
            style=Pack(flex=1)
        )

        # Main container is the scroll container
        self._container = self._scroll_container

    def _get_min_column_width(self) -> Optional[int]:
        """
        Calculate minimum column width as 1/4 of container width.

        Returns:
            Minimum width in pixels, or None if cannot determine
        """
        try:
            # Try to get window from the scroll container
            if hasattr(self._scroll_container, 'window') and self._scroll_container.window:
                window_width = self._scroll_container.window.size[0]
                min_width = int(window_width / 4)
                self.logger.debug(f"Calculated min column width: {min_width}px (window: {window_width}px)")
                return min_width
        except Exception as e:
            self.logger.debug(f"Could not calculate min column width: {e}")
        return None

    def _initialize_single_column(self):
        """Initialize with a single column containing a single pane - PHASE 5"""
        self.logger.info("Initializing with single column")

        # Create first column
        column = ColumnContainer(max_panes_per_column=self.max_panes_per_column)

        # Create first pane
        pane = self._create_pane()
        column.add_pane(pane)

        # Get minimum column width (1/4 of window width)
        min_width = self._get_min_column_width()
        column.rebuild_layout(min_width=min_width)

        # Add column to list
        self.columns.append(column)

        # Add column to UI
        self._columns_container.add(column.container)

        # Update backward-compat panes list
        self.panes = [pane]

        # Set focus
        self.focused_column_index = 0
        self.focused_pane_index = 0
        self.set_focused_pane(0)

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

        # Clear columns container (not _container which is ScrollContainer)
        self._columns_container.clear()

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
        self._columns_container.add(column.container)
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
        self._columns_container.add(column.container)
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
            self._columns_container.add(column.container)
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

    def _on_pane_clicked(self, pane: OutputPane):
        """
        Handle pane click - update focus, status bar, and sync with toolbar (PHASE 5).

        Args:
            pane: The pane that was clicked
        """
        # Find which column and pane index this is
        for col_idx, column in enumerate(self.columns):
            for pane_idx, p in enumerate(column.panes):
                if p is pane:
                    # Found it - update focus
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

    def _update_all_focus_indicators(self):
        """
        Update focus indicators on all panes based on current column+pane indices - PHASE 5.
        """
        for col_idx, column in enumerate(self.columns):
            for pane_idx, pane in enumerate(column.panes):
                is_focused = (col_idx == self.focused_column_index and
                             pane_idx == self.focused_pane_index)
                pane.set_focused(is_focused)

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

        # Get minimum column width (1/4 of window width)
        min_width = self._get_min_column_width()
        column.rebuild_layout(min_width=min_width)

        # Add column to system
        self.columns.append(column)
        self._columns_container.add(column.container)
        self.panes.append(new_pane)  # Backward compat

        # Update existing columns with minimum width
        for existing_column in self.columns[:-1]:  # All except the one we just added
            if min_width:
                existing_column.rebuild_layout(min_width=min_width)

        # Focus new pane in new column
        self.focused_column_index = len(self.columns) - 1
        self.focused_pane_index = 0
        self._update_all_focus_indicators()

        self.logger.info(f"✅ Horizontal split complete. Total columns: {len(self.columns)}, min_width: {min_width}px")
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
