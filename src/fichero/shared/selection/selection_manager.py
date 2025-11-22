"""
Centralized selection state management service.

Tracks selection across all views and emits events when selection changes.
This allows views to be stateless and components to react to selection changes.

Architecture:
- SelectionManager is a singleton service created in app.py
- Views call set_selection() to update their selection state
- Components subscribe to SELECTION_CHANGED events to react to changes
- All selection state is tracked centrally in one place

Usage Example:
    # In CollectionView
    self.app.selection_manager.set_selection(
        'collection',
        ['item-id-1', 'item-id-2'],
        metadata=[{...}, {...}]
    )

    # In StatusBar (Phase 2)
    from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
    subscribe_to_navigation("SELECTION_CHANGED", self._on_selection_changed)

    def _on_selection_changed(self, event):
        count = event.data.get('count', 0)
        view_id = event.data.get('view_id')
        # Update status bar text...
"""

import logging
import time
from typing import List, Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass

from fichero.shared.navigation.navigation_event_bus import emit_navigation_event, NavigationEvents

logger = logging.getLogger(__name__)


class SelectionContext(Enum):
    """Types of views/contexts that can have selections"""
    LIBRARY = "library"           # Collections in library view
    COLLECTION = "collection"     # Items in collection view
    PREVIEW = "preview"           # Preview panes in output view
    ADJUST = "adjust"             # Adjust pane controls


@dataclass
class SelectionState:
    """
    Immutable snapshot of selection state at a point in time.

    This is returned by get_state_snapshot() and can be used for:
    - Debugging (logging complete state)
    - State comparison (did selection change?)
    - State persistence (saving for restoration)
    """
    view_id: str                      # View identifier (e.g., "collection")
    item_ids: List[str]               # List of selected item IDs
    metadata: List[Dict[str, Any]]    # Metadata for each selected item
    timestamp: float                  # When this state was captured
    context: SelectionContext         # Which context this belongs to

    @property
    def count(self) -> int:
        """Number of selected items"""
        return len(self.item_ids)

    @property
    def has_selection(self) -> bool:
        """True if any items are selected"""
        return len(self.item_ids) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'view_id': self.view_id,
            'item_ids': self.item_ids.copy(),
            'metadata': [m.copy() for m in self.metadata],
            'timestamp': self.timestamp,
            'context': self.context.value,
            'count': self.count,
            'has_selection': self.has_selection
        }


class SelectionManager:
    """
    Centralized selection state manager.

    Maintains selection state for all views and emits SELECTION_CHANGED events
    when selections change. This allows components (inspector, status bar, etc.)
    to react to selection changes without direct coupling to views.

    State Management:
    - Each view_id (e.g., "collection") has its own independent selection state
    - Selection state is a list of item IDs (empty list = no selection)
    - Metadata is optional and stored separately (one dict per selected item)
    - Events are only emitted when selection actually changes (prevents spam)

    Event Flow:
    1. View calls set_selection(view_id, item_ids, metadata)
    2. SelectionManager compares with old state
    3. If changed, updates internal state
    4. Emits SELECTION_CHANGED event via navigation event bus
    5. Subscribers (StatusBar, Inspector) receive event and update

    Thread Safety:
    - This class is NOT thread-safe
    - All methods must be called from the main UI thread
    - Toga apps are single-threaded, so this is safe
    """

    def __init__(self):
        """Initialize selection manager with empty state"""
        # Selection state: view_id → list of selected item IDs
        self._selections: Dict[str, List[str]] = {
            SelectionContext.LIBRARY.value: [],
            SelectionContext.COLLECTION.value: [],
            SelectionContext.PREVIEW.value: [],
            SelectionContext.ADJUST.value: [],
        }

        # Metadata about selections: view_id → list of metadata dicts
        # Each dict contains item properties like name, type, file_path, etc.
        # Indexed the same as _selections (metadata[i] corresponds to item_ids[i])
        self._metadata: Dict[str, List[Dict[str, Any]]] = {
            SelectionContext.LIBRARY.value: [],
            SelectionContext.COLLECTION.value: [],
            SelectionContext.PREVIEW.value: [],
            SelectionContext.ADJUST.value: [],
        }

        logger.info("SelectionManager initialized")

    def set_selection(
        self,
        view_id: str,
        item_ids: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Update selection for a view.

        Args:
            view_id: View identifier (e.g., 'collection', 'library')
            item_ids: List of selected item IDs (empty list = no selection)
            metadata: Optional list of metadata dicts (one per item)
                     If provided, must have same length as item_ids

        Emits:
            SELECTION_CHANGED event if selection actually changed

        Example:
            # Single item selection
            manager.set_selection('collection', ['item-123'])

            # Multi-item selection with metadata
            manager.set_selection(
                'collection',
                ['item-1', 'item-2'],
                metadata=[
                    {'name': 'Document 1', 'type': 'pdf'},
                    {'name': 'Document 2', 'type': 'pdf'}
                ]
            )

            # Clear selection
            manager.set_selection('collection', [])
        """
        # Normalize inputs
        if not isinstance(item_ids, list):
            # Convert single item to list
            item_ids = [item_ids] if item_ids else []

        # Remove None values from item_ids
        item_ids = [id for id in item_ids if id is not None]

        # Validate metadata matches item_ids length
        if metadata is not None:
            if len(metadata) != len(item_ids):
                logger.warning(
                    f"Metadata length ({len(metadata)}) doesn't match "
                    f"item_ids length ({len(item_ids)}) - ignoring metadata"
                )
                metadata = None

        # Get old selection for comparison
        old_selection = self._selections.get(view_id, []).copy()

        # Check if selection actually changed
        if old_selection == item_ids:
            logger.debug(f"Selection unchanged for {view_id}, skipping event")
            return

        # Determine context from view_id
        context = self._get_context_for_view(view_id)

        # Update selection state
        self._selections[view_id] = item_ids.copy()

        # Update metadata if provided, otherwise clear it
        if metadata is not None:
            # ADDRESSING REVIEW ISSUE #4: Deep copy metadata to prevent mutation
            self._metadata[view_id] = [m.copy() for m in metadata]
        else:
            # Clear metadata when no metadata provided
            # (Prevents stale metadata from previous selection)
            self._metadata[view_id] = []

        # ADDRESSING REVIEW ISSUE #1: Add try/except around emit_navigation_event()
        try:
            # Emit event via navigation event bus (using constant for consistency)
            emit_navigation_event(NavigationEvents.SELECTION_CHANGED, {
                'view_id': view_id,
                'context': context.value,
                'old_selection': old_selection,
                'new_selection': item_ids.copy(),
                'count': len(item_ids),
                'metadata': [m.copy() for m in self._metadata[view_id]],
                'timestamp': time.time()
            })
        except Exception as e:
            logger.error(f"Failed to emit SELECTION_CHANGED event: {e}")
            # State is still updated, just event didn't go out

        logger.info(
            f"Selection changed for {view_id}: "
            f"{len(old_selection)} -> {len(item_ids)} items"
        )

    def get_selection(self, view_id: str) -> List[str]:
        """
        Get current selection for a view.

        Args:
            view_id: View identifier

        Returns:
            List of selected item IDs (empty list if nothing selected)
            Returns a COPY to prevent external mutation

        Example:
            selected_ids = manager.get_selection('collection')
            if selected_ids:
                print(f"Processing {len(selected_ids)} items...")
        """
        return self._selections.get(view_id, []).copy()

    def get_selection_count(self, view_id: str) -> int:
        """
        Get count of selected items in a view.

        Args:
            view_id: View identifier

        Returns:
            Number of selected items (0 if nothing selected)

        Example:
            count = manager.get_selection_count('collection')
            status_text = f"{count} items selected" if count > 0 else "No items selected"
        """
        return len(self._selections.get(view_id, []))

    def get_selection_metadata(self, view_id: str) -> List[Dict[str, Any]]:
        """
        Get metadata for selected items.

        Args:
            view_id: View identifier

        Returns:
            List of metadata dicts (one per selected item)
            Returns a COPY to prevent external mutation

        Example:
            metadata = manager.get_selection_metadata('collection')
            for item_meta in metadata:
                print(f"Selected: {item_meta.get('name')}")
        """
        # Return deep copy to prevent mutation
        return [m.copy() for m in self._metadata.get(view_id, [])]

    def clear_selection(self, view_id: str) -> None:
        """
        Clear selection for a view.

        Args:
            view_id: View identifier

        Example:
            manager.clear_selection('collection')
        """
        self.set_selection(view_id, [])

    def clear_all_selections(self) -> None:
        """
        Clear selections for all views.

        Useful when resetting application state or logging out.

        Example:
            # On app exit
            manager.clear_all_selections()
        """
        for view_id in list(self._selections.keys()):
            self.clear_selection(view_id)

        logger.info("All selections cleared")

    def get_state_snapshot(self, view_id: str) -> Optional[SelectionState]:
        """
        Get immutable snapshot of current selection state.

        Args:
            view_id: View identifier

        Returns:
            SelectionState snapshot or None if view_id doesn't exist

        Example:
            snapshot = manager.get_state_snapshot('collection')
            if snapshot and snapshot.has_selection:
                print(f"Selected {snapshot.count} items at {snapshot.timestamp}")
        """
        if view_id not in self._selections:
            return None

        context = self._get_context_for_view(view_id)

        return SelectionState(
            view_id=view_id,
            item_ids=self._selections[view_id].copy(),
            metadata=[m.copy() for m in self._metadata.get(view_id, [])],
            timestamp=time.time(),
            context=context
        )

    def _get_context_for_view(self, view_id: str) -> SelectionContext:
        """
        Map view_id to SelectionContext enum.

        Args:
            view_id: View identifier string

        Returns:
            Corresponding SelectionContext enum value

        Example:
            context = _get_context_for_view('collection')  # → SelectionContext.COLLECTION
        """
        # Try exact match first
        try:
            return SelectionContext(view_id)
        except ValueError:
            # Fallback: try to find context from known mappings
            view_to_context = {
                'library': SelectionContext.LIBRARY,
                'collection': SelectionContext.COLLECTION,
                'preview': SelectionContext.PREVIEW,
                'output': SelectionContext.PREVIEW,  # Alias: output → preview
                'adjust': SelectionContext.ADJUST,
            }
            return view_to_context.get(view_id, SelectionContext.COLLECTION)

    def debug_print_state(self) -> None:
        """Print current state for debugging (logger output)"""
        logger.debug("=== SelectionManager State ===")
        for view_id, item_ids in self._selections.items():
            count = len(item_ids)
            metadata_count = len(self._metadata.get(view_id, []))
            logger.debug(f"  {view_id}: {count} items, {metadata_count} metadata")
            if count > 0:
                logger.debug(f"    IDs: {item_ids[:3]}{'...' if count > 3 else ''}")
        logger.debug("=============================")
