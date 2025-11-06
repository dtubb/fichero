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
        else:
            self.logger.warning(f"Unknown layout type: {layout_type}")
            self._create_single_layout()

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

    def _create_pane(self) -> OutputPane:
        """
        Create a new output pane.

        Returns:
            New OutputPane instance
        """
        return OutputPane(self.library_manager, self.renderer_registry)

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
            LayoutType.QUAD
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
