"""
Universal Layout Manager for Fichero

Manages dynamic splitting and layout of views across both desktop and mobile platforms.
Replaces the hardcoded 3-pane system with flexible, resizable view containers.

Part of Phase 3.1: Enhanced Navigation Controller

Desktop: Uses toga.SplitContainer for native resizable panes
Mobile: Uses toga.Box with single-column layout (no SplitContainer support)
"""

import logging
import uuid
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field

import toga
from toga.style.pack import Pack
from toga.constants import ROW, COLUMN, Direction

logger = logging.getLogger(__name__)


class SplitDirection(Enum):
    """Direction to split a view"""
    HORIZONTAL = "horizontal"  # Split left/right (creates columns)
    VERTICAL = "vertical"      # Split top/bottom (creates rows)


@dataclass
class ViewSlot:
    """
    A slot in the layout that can hold a view.

    Represents one "pane" in the layout system. Each slot has:
    - Unique ID
    - Reference to the view it contains (if any)
    - Flex ratio for SplitContainer sizing (desktop) or size in pixels (mobile)
    - Position in parent container
    - Trackable wrapper box for width/height persistence
    """
    slot_id: str
    view: Optional[Any] = None  # BaseViewInterface instance
    container: Optional[toga.Box] = None  # Outer container for SplitContainer
    content_box: Optional[toga.Box] = None  # Inner trackable box for width/height
    flex: int = 1  # Flex ratio for SplitContainer (desktop mode)
    size: int = 200  # Size in pixels (mobile mode only)
    min_size: int = 100  # Minimum size in pixels
    is_focused: bool = False
    # Track current dimensions for persistence
    current_width: Optional[int] = None
    current_height: Optional[int] = None
    # Click handler callback
    on_click: Optional[Callable[[], None]] = None
    # Column visibility and metadata (for collapsible columns)
    is_visible: bool = True
    is_collapsible: bool = False  # Can this column be auto-hidden?
    column_name: Optional[str] = None  # Name for menu commands (e.g., "Library", "Collection")
    fixed_width: Optional[int] = None  # Fixed width in pixels (None = flexible)

    def __post_init__(self):
        """Create the container box and trackable content box after initialization"""
        if self.container is None:
            # Create outer container for SplitContainer
            # This fills 100% of available height
            self.container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1  # Fill available space
                )
            )

            # Create inner trackable box for actual content
            # This box will have measurable width/height that we can persist
            self.content_box = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"  # White background for content
                )
            )

            # Add content box to container
            self.container.add(self.content_box)

    def set_focused(self, focused: bool):
        """Update focus state and visual indicator"""
        self.is_focused = focused

        # Update visual border to indicate focus
        # Using a subtle left border instead of margin to avoid layout shifts
        if focused:
            # Blue left border for focused slot
            self.content_box.style.update(
                background_color="#E3F2FD"  # Light blue background
                # No margin - border-only focus indicator
            )
        else:
            # Reset to default
            self.content_box.style.update(
                background_color="#FFFFFF"  # White background
                # No margin in unfocused state either
            )


class UniversalLayoutManager:
    """
    Manages dynamic layout of views with resizable splits.

    Replaces the hardcoded 3-pane system (left/center/right) with a flexible
    system that can split views in any direction.

    Key features:
    - Desktop: Uses toga.SplitContainer for native resizable panes
    - Mobile: Uses toga.Box with single-column layout
    - Focus tracking
    - State persistence (flex ratios)

    Architecture (Desktop):
    - Root container holds nested SplitContainers
    - Each ViewSlot has a container Box
    - Flex ratios control initial sizing

    Example desktop layout (3 columns):
        SplitContainer(HORIZONTAL) {
          left: ViewSlot 1 (Library)
          right: SplitContainer(HORIZONTAL) {
            left: ViewSlot 2 (Collection)
            right: ViewSlot 3 (Preview)
          }
        }
    """

    def __init__(self, is_mobile: bool = False):
        """
        Initialize the layout manager.

        Args:
            is_mobile: If True, uses Box layout for mobile (no SplitContainer)
        """
        self.is_mobile = is_mobile

        # Root container that holds everything
        # Will be populated by add_view() calls
        self.root_container: Optional[toga.Widget] = None

        # Track all view slots by ID
        self.view_slots: Dict[str, ViewSlot] = {}

        # Track the root split container (desktop only)
        self.root_split: Optional[toga.SplitContainer] = None

        # Currently focused view slot
        self.focused_slot_id: Optional[str] = None

        # Callbacks for layout events
        self.on_view_focused: Optional[Callable[[str], None]] = None
        self.on_view_added: Optional[Callable[[str], None]] = None
        self.on_view_removed: Optional[Callable[[str], None]] = None

        logger.info(f"UniversalLayoutManager initialized (mobile={is_mobile})")

    def add_columns(
        self,
        views: List[Any],
        flex_ratios: List[int] = None,
        min_widths: List[int] = None,
        widths: List[int] = None  # Deprecated - use min_widths
    ) -> List[str]:
        """
        Create a dynamic multi-column layout with any number of columns.

        Args:
            views: List of views to display (one per column)
            flex_ratios: Optional flex ratios for each column (defaults to equal sizing)
            min_widths: Optional minimum pixel widths for each column (None = flexible)
                       Example: [270, 250, None, 250] - minimum widths for cols 1,2,4, flexible for col 3
            widths: DEPRECATED - use min_widths instead

        Returns:
            List of slot IDs for each column
        """
        if not views:
            logger.error("Cannot create layout with no views")
            return []

        # Handle deprecated widths parameter
        if widths is not None:
            logger.warning("widths parameter is deprecated, use min_widths instead")
            if min_widths is None:
                min_widths = widths

        # Validate min_widths if provided
        if min_widths is not None and len(min_widths) != len(views):
            logger.warning(f"min_widths count ({len(min_widths)}) doesn't match views count ({len(views)}), ignoring min_widths")
            min_widths = None

        # Default to equal flex ratios if not provided
        if flex_ratios is None:
            flex_ratios = [1] * len(views)
        elif len(flex_ratios) != len(views):
            logger.warning(f"Flex ratios count ({len(flex_ratios)}) doesn't match views count ({len(views)}), using equal ratios")
            flex_ratios = [1] * len(views)

        # Create ViewSlots for each column
        slots = []
        for i, view in enumerate(views):
            # Use flex ratio for all columns
            flex = flex_ratios[i]

            slot = ViewSlot(
                slot_id=str(uuid.uuid4()),
                view=view,
                flex=flex
            )

            # Add view's container to slot's content_box (not outer container)
            if hasattr(view, 'container'):
                slot.content_box.add(view.container)

            slots.append(slot)
            self.view_slots[slot.slot_id] = slot

        if self.is_mobile:
            # Mobile: Simple vertical stack
            mobile_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
            for slot in slots:
                mobile_box.add(slot.container)
            self.root_container = mobile_box
            logger.info(f"Created mobile {len(slots)}-column layout (vertical stack)")
        else:
            # Desktop: Nested SplitContainers for multi-column layout
            # Build from right to left to create proper nesting
            current_container = slots[-1].container
            current_flex = slots[-1].flex

            for i in range(len(slots) - 2, -1, -1):
                # Create a new split with current column on left, accumulated on right
                new_split = toga.SplitContainer(
                    direction=Direction.VERTICAL,  # Vertical split line = horizontal layout
                    content=[
                        (slots[i].container, slots[i].flex),
                        (current_container, current_flex)
                    ],
                    style=Pack(flex=1)  # Ensure SplitContainer fills available space
                )
                current_container = new_split
                current_flex = slots[i].flex + current_flex

            self.root_split = current_container
            self.root_container = current_container
            # Format flex info for logging
            flex_info = [f"{s.flex}" for s in slots]
            logger.info(f"Created desktop {len(slots)}-column layout (flex={':'.join(flex_info)})")

        # Emit events
        if self.on_view_added:
            for slot in slots:
                self.on_view_added(slot.slot_id)

        return [slot.slot_id for slot in slots]

    def add_columns_fixed(
        self,
        views: List[Any],
        widths: List[Optional[int]],
        column_names: Optional[List[str]] = None,
        collapsible: Optional[List[bool]] = None,
        min_widths: Optional[List[int]] = None
    ) -> List[str]:
        """
        Create a multi-column layout with fixed widths (no SplitContainer).

        This avoids autolayout warnings by using a simple Box layout instead of
        nested SplitContainers. Fixed-width columns get exact pixel widths,
        flexible columns (width=None) expand to fill remaining space.

        Supports collapsible columns that can be hidden when window is too narrow.

        Args:
            views: List of views to display (one per column)
            widths: List of widths - integer for fixed pixels, None for flexible
                   Example: [270, 250, None, 250] - fixed sidebars, flexible preview
            column_names: Optional names for columns (for menu commands)
                         Example: ["Library", "Collection", "Preview", "Adjust"]
            collapsible: Optional list marking which columns can auto-hide
                        Example: [True, True, False, True] - Preview can't hide
            min_widths: Optional minimum widths before auto-hiding
                       Example: [270, 250, 800, 250] - Preview needs 800px minimum

        Returns:
            List of slot IDs for each column
        """
        if not views:
            logger.error("Cannot create layout with no views")
            return []

        if len(widths) != len(views):
            logger.error(f"Widths count ({len(widths)}) doesn't match views count ({len(views)})")
            return []

        # Default all columns to non-collapsible if not specified
        if collapsible is None:
            collapsible = [False] * len(views)

        # Default no names if not specified
        if column_names is None:
            column_names = [None] * len(views)

        # Default no minimum widths if not specified
        if min_widths is None:
            min_widths = [None] * len(views)

        # Create ViewSlots for each column
        slots = []
        for i, view in enumerate(views):
            slot = ViewSlot(
                slot_id=str(uuid.uuid4()),
                view=view,
                flex=1,  # Placeholder - not used in fixed layout
                fixed_width=widths[i],
                column_name=column_names[i],
                is_collapsible=collapsible[i],
                min_size=min_widths[i] if min_widths[i] is not None else 100
            )

            # Set width on outer container
            if widths[i] is not None:
                # Fixed width column
                slot.container.style.update(width=widths[i], flex=0)
                logger.debug(f"Column {i} ({column_names[i]}): fixed width={widths[i]}px, collapsible={collapsible[i]}")
            else:
                # Flexible column - expands to fill space
                slot.container.style.update(flex=1)
                logger.debug(f"Column {i} ({column_names[i]}): flexible (flex=1), min_width={min_widths[i]}px")

            # Add view's container to slot's content_box
            if hasattr(view, 'container'):
                slot.content_box.add(view.container)

            slots.append(slot)
            self.view_slots[slot.slot_id] = slot

        if self.is_mobile:
            # Mobile: Vertical stack
            mobile_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
            for slot in slots:
                mobile_box.add(slot.container)
            self.root_container = mobile_box
            logger.info(f"Created mobile layout with {len(slots)} columns (vertical stack)")
        else:
            # Desktop: Horizontal Box (no SplitContainer!)
            desktop_box = toga.Box(style=Pack(direction=ROW, flex=1))
            for slot in slots:
                desktop_box.add(slot.container)
            self.root_container = desktop_box

            # Format width info for logging
            width_info = [f"{w}px" if w else "flex" for w in widths]
            logger.info(f"Created desktop {len(slots)}-column fixed layout (widths={', '.join(width_info)})")

        # Emit events
        if self.on_view_added:
            for slot in slots:
                self.on_view_added(slot.slot_id)

        return [slot.slot_id for slot in slots]

    def add_three_column_layout(
        self,
        left_view: Any,
        center_view: Any,
        right_view: Any,
        left_flex: int = 1,
        center_flex: int = 2,
        right_flex: int = 2,
        split_right_pane: bool = False,
        right_top_view: Any = None,
        right_bottom_view: Any = None,
        right_top_flex: int = 1,
        right_bottom_flex: int = 2
    ) -> Tuple[str, str, str]:
        """
        Create a 3-column desktop layout using nested SplitContainers.

        Desktop structure:
            SplitContainer(HORIZONTAL) {
              left: ViewSlot 1 (Library)
              right: SplitContainer(HORIZONTAL) {
                left: ViewSlot 2 (Collection)
                right: ViewSlot 3 (Preview)
              }
            }

        Mobile structure:
            Box(COLUMN) {
              ViewSlot 1 (Library)
              ViewSlot 2 (Collection)
              ViewSlot 3 (Preview)
            }

        Args:
            left_view: View for left pane
            center_view: View for center pane
            right_view: View for right pane
            left_flex: Flex ratio for left pane (desktop only)
            center_flex: Flex ratio for center pane (desktop only)
            right_flex: Flex ratio for right pane (desktop only)

        Returns:
            Tuple of (left_slot_id, center_slot_id, right_slot_id)
        """
        # Create ViewSlots for each pane
        left_slot = ViewSlot(
            slot_id=str(uuid.uuid4()),
            view=left_view,
            flex=left_flex
        )
        center_slot = ViewSlot(
            slot_id=str(uuid.uuid4()),
            view=center_view,
            flex=center_flex
        )
        right_slot = ViewSlot(
            slot_id=str(uuid.uuid4()),
            view=right_view,
            flex=right_flex
        )

        # Add views' containers to slots
        if hasattr(left_view, 'container'):
            left_slot.container.add(left_view.container)
        if hasattr(center_view, 'container'):
            center_slot.container.add(center_view.container)
        if hasattr(right_view, 'container'):
            right_slot.container.add(right_view.container)

        # Track slots
        self.view_slots[left_slot.slot_id] = left_slot
        self.view_slots[center_slot.slot_id] = center_slot
        self.view_slots[right_slot.slot_id] = right_slot

        if self.is_mobile:
            # Mobile: Simple Box layout
            mobile_box = toga.Box(
                style=Pack(direction=COLUMN, flex=1)
            )
            mobile_box.add(left_slot.container)
            mobile_box.add(center_slot.container)
            mobile_box.add(right_slot.container)
            self.root_container = mobile_box
            logger.info("Created mobile 3-pane layout (vertical stack)")
        else:
            # Desktop: Nested SplitContainers
            # Note: Direction.VERTICAL means vertical split line (horizontal layout)
            #       Direction.HORIZONTAL means horizontal split line (vertical layout)

            # Inner split: center | right (side by side)
            inner_split = toga.SplitContainer(
                direction=Direction.VERTICAL,  # Vertical split line = horizontal layout
                content=[
                    (center_slot.container, center_flex),
                    (right_slot.container, right_flex)
                ],
                style=Pack(flex=1)  # Ensure SplitContainer fills available space
            )

            # Outer split: left | inner_split (side by side)
            outer_split = toga.SplitContainer(
                direction=Direction.VERTICAL,  # Vertical split line = horizontal layout
                content=[
                    (left_slot.container, left_flex),
                    (inner_split, center_flex + right_flex)  # Combined flex for right side
                ],
                style=Pack(flex=1)  # Ensure SplitContainer fills available space
            )

            self.root_split = outer_split
            self.root_container = outer_split
            logger.info(f"Created desktop 3-column layout (flex={left_flex}:{center_flex}:{right_flex})")

        # Emit events
        if self.on_view_added:
            self.on_view_added(left_slot.slot_id)
            self.on_view_added(center_slot.slot_id)
            self.on_view_added(right_slot.slot_id)

        return (left_slot.slot_id, center_slot.slot_id, right_slot.slot_id)

    def split_slot_vertical(
        self,
        slot_id: str,
        top_view: Any,
        bottom_view: Any,
        top_flex: int = 1,
        bottom_flex: int = 1
    ) -> Tuple[str, str]:
        """
        Split a view slot vertically (top/bottom) using SplitContainer.

        Args:
            slot_id: ID of the slot to split
            top_view: View for top pane
            bottom_view: View for bottom pane
            top_flex: Flex ratio for top pane
            bottom_flex: Flex ratio for bottom pane

        Returns:
            Tuple of (top_slot_id, bottom_slot_id)
        """
        if slot_id not in self.view_slots:
            logger.error(f"Cannot split non-existent slot: {slot_id}")
            return ("", "")

        if self.is_mobile:
            logger.warning("Vertical split not supported on mobile")
            return ("", "")

        # Get the existing slot
        old_slot = self.view_slots[slot_id]

        logger.info(f"🔍 split_slot_vertical: BEFORE split - fixed_width={old_slot.fixed_width}, column_name={old_slot.column_name}, width={old_slot.container.style.width}, flex={old_slot.container.style.flex}")

        # IMPORTANT: Preserve the parent slot's metadata (fixed_width, column_name, etc.)
        # so that toggling the parent column still works correctly after splitting
        parent_fixed_width = old_slot.fixed_width
        parent_column_name = old_slot.column_name
        parent_is_collapsible = old_slot.is_collapsible

        # Create new ViewSlots
        top_slot = ViewSlot(
            slot_id=str(uuid.uuid4()),
            view=top_view,
            flex=top_flex
        )
        bottom_slot = ViewSlot(
            slot_id=str(uuid.uuid4()),
            view=bottom_view,
            flex=bottom_flex
        )

        # Add views' containers to slots' content_box (not container)
        # This ensures views are inside the focus-styled content_box
        if hasattr(top_view, 'container'):
            top_slot.content_box.add(top_view.container)
        if hasattr(bottom_view, 'container'):
            bottom_slot.content_box.add(bottom_view.container)

        # Create vertical split (horizontal split line = top/bottom)
        # Set explicit width to match parent's fixed_width so it respects parent sizing
        # Without this, SplitContainer (native widget) doesn't shrink when parent width=0
        split_style = None
        if old_slot.fixed_width is not None:
            split_style = Pack(width=old_slot.fixed_width)

        vertical_split = toga.SplitContainer(
            direction=Direction.HORIZONTAL,  # Horizontal split line = vertical layout
            content=[
                (top_slot.container, top_flex),
                (bottom_slot.container, bottom_flex)
            ],
            style=split_style
        )

        # Replace the old slot's container content with the new split
        old_slot.container.clear()
        old_slot.container.add(vertical_split)

        logger.info(f"🔍 split_slot_vertical: AFTER split - fixed_width={old_slot.fixed_width}, column_name={old_slot.column_name}, width={old_slot.container.style.width}, flex={old_slot.container.style.flex}")

        # IMPORTANT: Keep the parent slot in view_slots so column toggles still work
        # The parent slot's metadata (fixed_width, column_name) must remain intact
        # Don't overwrite old_slot - it's the parent container for the vertical split

        # Track new child slots
        self.view_slots[top_slot.slot_id] = top_slot
        self.view_slots[bottom_slot.slot_id] = bottom_slot

        # Emit events
        if self.on_view_added:
            self.on_view_added(top_slot.slot_id)
            self.on_view_added(bottom_slot.slot_id)

        logger.info(f"Split slot {slot_id} vertically (flex={top_flex}:{bottom_flex}), parent slot preserved with fixed_width={old_slot.fixed_width}")
        return (top_slot.slot_id, bottom_slot.slot_id)

    def focus_slot(self, slot_id: str):
        """
        Focus a specific slot by updating visual indicators.

        Args:
            slot_id: ID of the slot to focus
        """
        if slot_id not in self.view_slots:
            logger.warning(f"Attempted to focus non-existent slot: {slot_id}")
            return

        # Unfocus the currently focused slot (if any)
        if self.focused_slot_id and self.focused_slot_id in self.view_slots:
            old_slot = self.view_slots[self.focused_slot_id]
            old_slot.set_focused(False)

        # Focus the new slot
        new_slot = self.view_slots[slot_id]
        new_slot.set_focused(True)

        # Update focused slot ID
        self.focused_slot_id = slot_id

        # Call the on_view_focused callback if set
        if self.on_view_focused:
            self.on_view_focused(slot_id)

        logger.debug(f"Focused slot: {slot_id}")

    def focus_view(self, slot_id: str):
        """
        Set focus to a specific view.

        Args:
            slot_id: ID of the slot to focus
        """
        if slot_id not in self.view_slots:
            logger.warning(f"Attempted to focus non-existent slot: {slot_id}")
            return

        # Clear previous focus
        if self.focused_slot_id and self.focused_slot_id in self.view_slots:
            old_slot = self.view_slots[self.focused_slot_id]
            old_slot.is_focused = False
            if hasattr(old_slot.view, 'set_focused'):
                old_slot.view.set_focused(False)

        # Set new focus
        slot = self.view_slots[slot_id]
        slot.is_focused = True
        if hasattr(slot.view, 'set_focused'):
            slot.view.set_focused(True)

        self.focused_slot_id = slot_id

        # Emit event
        if self.on_view_focused:
            self.on_view_focused(slot_id)

        logger.debug(f"Focused view (slot_id={slot_id})")

    def get_focused_view(self) -> Optional[Any]:
        """
        Get the currently focused view.

        Returns:
            The focused view, or None if no view is focused
        """
        if self.focused_slot_id and self.focused_slot_id in self.view_slots:
            return self.view_slots[self.focused_slot_id].view
        return None

    def get_layout_state(self) -> Dict[str, Any]:
        """
        Get current layout state for persistence.

        Returns:
            Dictionary containing layout state including flex ratios and visibility
        """
        state = {
            'is_mobile': self.is_mobile,
            'focused_slot_id': self.focused_slot_id,
            'slots': []
        }

        for slot_id, slot in self.view_slots.items():
            slot_state = {
                'slot_id': slot_id,
                'name': slot.name,  # Column name for visibility restoration
                'flex': slot.flex,  # Save flex ratio for desktop
                'size': slot.size,  # Save size for mobile
                'is_visible': slot.is_visible,  # Save visibility state
                'fixed_width': slot.fixed_width,  # Save fixed width if any
                'view_type': None
            }

            # Get view type if available
            if slot.view and hasattr(slot.view, 'view_type'):
                slot_state['view_type'] = slot.view.view_type.value

            state['slots'].append(slot_state)

        logger.debug(f"Layout state captured: {len(state['slots'])} slots")
        return state

    def restore_layout(self, state: Dict[str, Any]):
        """
        Restore layout from saved state.

        Args:
            state: Dictionary containing layout state with column visibility and dimensions

        Restores:
        - Column visibility states (show/hide)
        - Column widths (for fixed-width columns)
        - Flex ratios (for flexible columns)
        - Focus state
        """
        try:
            logger.info(f"Restoring layout state with {len(state.get('slots', []))} slots")

            # Restore each slot's visibility and dimensions
            for slot_state in state.get('slots', []):
                slot_name = slot_state.get('name')
                if not slot_name:
                    continue

                slot = self._find_slot_by_name(slot_name)
                if not slot:
                    logger.warning(f"Slot '{slot_name}' not found during restore")
                    continue

                # Restore visibility
                is_visible = slot_state.get('is_visible', True)
                if is_visible and not slot.is_visible:
                    self.show_column(slot_name)
                    logger.debug(f"Restored column '{slot_name}' as visible")
                elif not is_visible and slot.is_visible:
                    self.hide_column(slot_name)
                    logger.debug(f"Restored column '{slot_name}' as hidden")

                # Restore fixed width if applicable (only for visible columns with fixed widths)
                if is_visible and slot_state.get('fixed_width') is not None:
                    slot.fixed_width = slot_state['fixed_width']
                    slot.container.style.width = slot.fixed_width
                    slot.container.style.flex = 0
                    logger.debug(f"Restored fixed width for '{slot_name}': {slot.fixed_width}px")

                # Restore flex ratio (for flexible columns)
                if is_visible and slot_state.get('flex') is not None:
                    slot.flex = slot_state['flex']
                    # Only set flex on container if it's not a fixed-width column
                    if slot.fixed_width is None:
                        slot.container.style.flex = slot.flex
                        logger.debug(f"Restored flex for '{slot_name}': {slot.flex}")

            # Restore focus
            focused_slot_id = state.get('focused_slot_id')
            if focused_slot_id and focused_slot_id in self.view_slots:
                self.focus_slot(focused_slot_id)
                logger.debug(f"Restored focus to slot: {focused_slot_id}")

            logger.info(f"✅ Layout state restored successfully")

        except Exception as e:
            logger.error(f"Failed to restore layout state: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # Column Visibility Management

    def toggle_column(self, column_name: str) -> bool:
        """
        Toggle visibility of a named column.

        Args:
            column_name: Name of column to toggle (e.g., "Library", "Collection")

        Returns:
            New visibility state (True = visible, False = hidden)
        """
        slot = self._find_slot_by_name(column_name)
        if not slot:
            logger.warning(f"Column '{column_name}' not found")
            return False

        if not slot.is_collapsible:
            logger.warning(f"Column '{column_name}' is not collapsible")
            return slot.is_visible

        # Toggle visibility
        new_state = not slot.is_visible
        if new_state:
            self.show_column(column_name)
        else:
            self.hide_column(column_name)

        return new_state

    def show_column(self, column_name: str):
        """Show a previously hidden column."""
        slot = self._find_slot_by_name(column_name)
        if not slot:
            logger.warning(f"Column '{column_name}' not found")
            return

        if slot.is_visible:
            logger.debug(f"Column '{column_name}' already visible")
            return

        logger.info(f"🔍 show_column('{column_name}'): fixed_width={slot.fixed_width}, current_width={slot.container.style.width}, current_flex={slot.container.style.flex}")

        # Remove the width=0 constraint from both container and content_box
        try:
            del slot.container.style.width
        except AttributeError:
            pass
        try:
            del slot.content_box.style.width
        except AttributeError:
            pass

        # Restore width on container - BOTH width AND flex are critical
        if slot.fixed_width is not None:
            slot.container.style.width = slot.fixed_width
            slot.container.style.flex = 0
            logger.info(f"🔧 Set width={slot.fixed_width}, flex=0")
        else:
            # For flexible columns, must explicitly remove width property
            try:
                del slot.container.style.width
            except (AttributeError, KeyError):
                pass
            slot.container.style.flex = 1
            logger.info(f"🔧 Set flex=1 (no fixed width)")

        # Restore content_box to flex=1 (fill parent)
        slot.content_box.style.flex = 1

        slot.is_visible = True
        logger.info(f"✅ Showing column '{column_name}' (width={slot.fixed_width if slot.fixed_width else 'flex'})")
        logger.info(f"🔍 After show: width={slot.container.style.width}, flex={slot.container.style.flex}")

    def hide_column(self, column_name: str):
        """Hide a collapsible column."""
        slot = self._find_slot_by_name(column_name)
        if not slot:
            logger.warning(f"Column '{column_name}' not found")
            return

        if not slot.is_collapsible:
            logger.warning(f"Column '{column_name}' is not collapsible")
            return

        if not slot.is_visible:
            logger.debug(f"Column '{column_name}' already hidden")
            return

        logger.info(f"🔍 hide_column('{column_name}'): fixed_width={slot.fixed_width}, current_width={slot.container.style.width}, current_flex={slot.container.style.flex}")

        # Hide by setting width to 0 on BOTH container and content_box
        # The content_box needs width=0 too, otherwise its flex=1 will fight the parent's width=0
        slot.container.style.update(width=0, flex=0)
        slot.content_box.style.update(width=0, flex=0)
        slot.is_visible = False
        logger.info(f"🔒 Hiding column '{column_name}' (set width=0, flex=0 on both container and content_box)")
        logger.info(f"🔍 After hide: fixed_width still={slot.fixed_width} (preserved in slot)")

    def _find_slot_by_name(self, column_name: str) -> Optional[ViewSlot]:
        """Find a ViewSlot by its column name."""
        for slot in self.view_slots.values():
            if slot.column_name == column_name:
                return slot
        return None

    def get_column_visibility(self, column_name: str) -> bool:
        """Get visibility state of a column."""
        slot = self._find_slot_by_name(column_name)
        return slot.is_visible if slot else False

    def toggle_slot(self, slot_id: str) -> bool:
        """
        Toggle visibility of a slot by ID (useful for slots in vertical splits).

        Args:
            slot_id: ID of slot to toggle

        Returns:
            New visibility state (True = visible, False = hidden)
        """
        slot = self.view_slots.get(slot_id)
        if not slot:
            logger.warning(f"Slot '{slot_id}' not found")
            return False

        # Toggle visibility
        new_state = not slot.is_visible
        if new_state:
            self.show_slot(slot_id)
        else:
            self.hide_slot(slot_id)

        return new_state

    def show_slot(self, slot_id: str):
        """Show a previously hidden slot."""
        slot = self.view_slots.get(slot_id)
        if not slot:
            logger.warning(f"Slot '{slot_id}' not found")
            return

        if slot.is_visible:
            logger.debug(f"Slot '{slot_id}' already visible")
            return

        # Remove all constraints that might have been set during hide
        # Use del to remove style properties, not None
        try:
            del slot.container.style.height
        except (AttributeError, KeyError):
            pass  # Property might not be set
        try:
            del slot.container.style.width
        except (AttributeError, KeyError):
            pass  # Property might not be set

        # Restore flex ratio
        slot.container.style.flex = slot.flex
        slot.is_visible = True

        # Force layout refresh for native views (like NSTableView in CollectionView)
        if hasattr(slot.view, 'container'):
            try:
                # Try to refresh the native widget if it exists
                if hasattr(slot.view.container, 'refresh'):
                    slot.view.container.refresh()
                # Force container to re-layout
                slot.container.refresh()
            except (AttributeError, Exception) as e:
                logger.debug(f"Could not refresh view container: {e}")

        logger.info(f"✅ Showing slot '{slot_id}'")

    def hide_slot(self, slot_id: str):
        """Hide a slot in a vertical split (top/bottom).

        For vertical splits, we hide by setting height=0.
        This is different from hide_column() which uses width=0 for horizontal columns.
        """
        slot = self.view_slots.get(slot_id)
        if not slot:
            logger.warning(f"Slot '{slot_id}' not found")
            return

        if not slot.is_visible:
            logger.debug(f"Slot '{slot_id}' already hidden")
            return

        # For vertical splits (top/bottom), hide using height=0 only
        # Do NOT set width=0 as that's for horizontal columns
        slot.container.style.update(height=0, flex=0)
        slot.is_visible = False
        logger.info(f"🔒 Hiding slot '{slot_id}' in vertical split")

    @property
    def container(self) -> toga.Widget:
        """Get the root container for this layout (SplitContainer on desktop, Box on mobile)"""
        return self.root_container
