# Phase 1 Implementation Plan: SelectionManager Service

**Date**: 2025-11-15
**Status**: Ready for Implementation
**Phase**: 1 of 4 (SelectionManager Service)

---

## Executive Summary

This document provides a detailed, step-by-step implementation plan for creating a centralized SelectionManager service to track selection state across all views in the Fichero application. This plan is based on the comprehensive review in `SELECTION_TRACKING_REVIEW.md` and follows the existing architecture patterns established by NavigationController and the event bus system.

**Key Goals:**
1. Create a centralized SelectionManager service that tracks selection state
2. Integrate it with the existing event bus system (emit SELECTION_CHANGED events)
3. Provide a clean API for views to update and query selection state
4. Maintain backwards compatibility with existing selection code

**What This Phase Does NOT Include:**
- Status bar integration (Phase 2)
- Multi-selection workflow fixes (Phase 3)
- Selection preservation across navigation (Phase 4)

---

## 1. Architecture Design

### 1.1 File Structure

```
src/fichero/shared/selection/
├── __init__.py              # NEW - Package exports
└── selection_manager.py     # NEW - Main SelectionManager class
```

### 1.2 Class Structure

```python
# File: src/fichero/shared/selection/selection_manager.py

class SelectionContext(Enum):
    """Contexts where selection can occur"""
    LIBRARY = "library"           # Collections in library view
    COLLECTION = "collection"     # Items in collection view
    STEPS = "steps"               # Processing steps in step browser
    PREVIEW = "preview"           # Preview panes
    ADJUST = "adjust"             # Adjust pane controls

@dataclass
class SelectionState:
    """Immutable selection state snapshot"""
    view_id: str                  # e.g., "collection"
    item_ids: List[str]           # Selected item IDs (empty = no selection)
    metadata: List[Dict[str, Any]]  # Metadata for each selected item
    timestamp: float              # When selection was made
    context: SelectionContext     # Which context this belongs to

class SelectionManager:
    """Centralized selection state manager"""

    # Core state
    _selections: Dict[str, List[str]]  # view_id → list of item IDs
    _metadata: Dict[str, List[Dict]]   # view_id → list of metadata dicts

    # Public API
    def set_selection(view_id: str, item_ids: List[str], metadata: Optional[List[Dict]] = None)
    def get_selection(view_id: str) -> List[str]
    def get_selection_count(view_id: str) -> int
    def get_selection_metadata(view_id: str) -> List[Dict[str, Any]]
    def clear_selection(view_id: str)
    def clear_all_selections()
    def get_state_snapshot(view_id: str) -> Optional[SelectionState]
```

### 1.3 Event Types

Following the pattern in `navigation_event_bus.py`, we'll add a new event type:

```python
# In navigation_event_bus.py, add to NavigationEvents class:
SELECTION_CHANGED = "selection_changed"  # NEW - Emitted when any selection changes
```

**Event Payload Structure:**
```python
{
    'view_id': str,                    # "library", "collection", etc.
    'context': str,                    # SelectionContext enum value
    'old_selection': List[str],        # Previous item IDs
    'new_selection': List[str],        # New item IDs
    'count': int,                      # len(new_selection)
    'metadata': List[Dict[str, Any]],  # Metadata for selected items
    'timestamp': float                 # time.time()
}
```

### 1.4 Integration Points

**Where SelectionManager Lives:**
- Created in: `src/fichero/app.py` (during app initialization)
- Stored as: `app.selection_manager`
- Accessed from: Any view via `self.app.selection_manager`

**Who Uses SelectionManager:**

| Component | Role | How |
|-----------|------|-----|
| `app.py` | Creator | Initializes `SelectionManager()` |
| `main_window.py` | Reference Holder | Stores `self.selection_manager = app.selection_manager` |
| `library_view.py` | Publisher | Calls `set_selection('library', [collection_id])` |
| `collection_view.py` | Publisher | Calls `set_selection('collection', item_ids)` |
| `step_browser.py` | Publisher | Calls `set_selection('steps', [step_index])` |
| `status_bar.py` | Subscriber | (Phase 2) Listens to SELECTION_CHANGED events |
| `inspector_window.py` | Subscriber | (Future) Could listen to SELECTION_CHANGED events |

---

## 2. Detailed Implementation Steps

### Step 1: Create SelectionManager Module

**File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/selection/selection_manager.py`**

Create this new file with the following complete implementation:

```python
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

from fichero.shared.navigation.navigation_event_bus import emit_navigation_event

logger = logging.getLogger(__name__)


class SelectionContext(Enum):
    """Types of views/contexts that can have selections"""
    LIBRARY = "library"           # Collections in library view
    COLLECTION = "collection"     # Items in collection view
    STEPS = "steps"               # Processing steps in step browser
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
            SelectionContext.STEPS.value: [],
            SelectionContext.PREVIEW.value: [],
            SelectionContext.ADJUST.value: [],
        }

        # Metadata about selections: view_id → list of metadata dicts
        # Each dict contains item properties like name, type, file_path, etc.
        # Indexed the same as _selections (metadata[i] corresponds to item_ids[i])
        self._metadata: Dict[str, List[Dict[str, Any]]] = {
            SelectionContext.LIBRARY.value: [],
            SelectionContext.COLLECTION.value: [],
            SelectionContext.STEPS.value: [],
            SelectionContext.PREVIEW.value: [],
            SelectionContext.ADJUST.value: [],
        }

        logger.info("✅ SelectionManager initialized")

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
            self._metadata[view_id] = [m.copy() for m in metadata]
        else:
            # Clear metadata when no metadata provided
            # (Prevents stale metadata from previous selection)
            self._metadata[view_id] = []

        # Emit event via navigation event bus
        emit_navigation_event("SELECTION_CHANGED", {
            'view_id': view_id,
            'context': context.value,
            'old_selection': old_selection,
            'new_selection': item_ids.copy(),
            'count': len(item_ids),
            'metadata': [m.copy() for m in self._metadata[view_id]],
            'timestamp': time.time()
        })

        logger.info(
            f"📌 Selection changed for {view_id}: "
            f"{len(old_selection)} → {len(item_ids)} items"
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

        logger.info("🧹 All selections cleared")

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
                'steps': SelectionContext.STEPS,
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
```

**File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/selection/__init__.py`**

Create this new file:

```python
"""Selection management services"""

from .selection_manager import SelectionManager, SelectionContext, SelectionState

__all__ = ['SelectionManager', 'SelectionContext', 'SelectionState']
```

---

### Step 2: Add SELECTION_CHANGED Event Type

**File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/navigation/navigation_event_bus.py`**

**Location:** Line 84-109 (inside `NavigationEvents` class)

**Change:** Add new event type constant

```python
class NavigationEvents:
    """Constants for navigation event types"""

    # State change events
    STATE_CHANGED = "state_changed"
    NAVIGATION_UPDATED = "navigation_updated"

    # View events
    SHOW_LIBRARY = "show_library"
    SHOW_COLLECTION = "show_collection"
    SHOW_PREVIEW = "show_preview"
    SHOW_MODAL = "show_modal"
    VIEW_FOCUSED = "view_focused"  # Phase 3.1: Layout manager view focus events

    # Selection events  # NEW - ADD THIS COMMENT
    SELECTION_CHANGED = "selection_changed"  # NEW - ADD THIS LINE

    # UI events
    BACK_BUTTON_STATE_CHANGED = "back_button_state_changed"
    BREADCRUMBS_UPDATED = "breadcrumbs_updated"

    # Error events
    NAVIGATION_ERROR = "navigation_error"

    # Library state change events
    COLLECTION_ADDED = "collection_added"
    COLLECTION_DELETED = "collection_deleted"
    COLLECTION_UPDATED = "collection_updated"
    COLLECTION_ITEMS_CHANGED = "collection_items_changed"
```

**Rationale:** This follows the existing pattern of centralizing all event type constants in one class. Makes it easy to discover all available events.

---

### Step 3: Initialize SelectionManager in App

**File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/app.py`**

**Location:** Search for where `library_manager` is initialized. Based on the review, this should be around line 150-200 during service initialization.

**Change:** Add SelectionManager initialization

Find this section (approximate):
```python
# Initialize library manager
self.library_manager = LibraryManager(...)
logger.info("✅ Library manager initialized")
```

Add immediately after:
```python
# Initialize SelectionManager
from fichero.shared.selection import SelectionManager
self.selection_manager = SelectionManager()
logger.info("✅ SelectionManager initialized")
```

**Rationale:**
- Initializes early in app startup (before views are created)
- Makes it available globally via `app.selection_manager`
- Follows same pattern as other managers (LibraryManager, etc.)

---

### Step 4: Store SelectionManager Reference in MainWindow

**File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`**

**Location:** Line 82-83 (after getting navigation_controller)

**Current code:**
```python
# Get NavigationController from app
self.navigation_controller = self._get_navigation_controller()
```

**Change:** Add after this:
```python
# Get NavigationController from app
self.navigation_controller = self._get_navigation_controller()

# Get SelectionManager from app  # NEW
self.selection_manager = getattr(self.app, 'selection_manager', None)  # NEW
if not self.selection_manager:  # NEW
    logger.warning("⚠️ SelectionManager not available in app")  # NEW
else:  # NEW
    logger.debug("✅ SelectionManager reference stored in main window")  # NEW
```

**Rationale:**
- Makes SelectionManager easily accessible to views via `self.app.selection_manager`
- Defensive programming: handles case where SelectionManager isn't initialized
- Logs warning if missing (helps debugging)

---

### Step 5: Verification Test

After implementing Steps 1-4, verify the implementation works:

**Test Script** (run in Python console during app execution):

```python
# Test 1: Check SelectionManager exists
assert hasattr(app, 'selection_manager'), "SelectionManager not in app"
print("✅ SelectionManager exists in app")

# Test 2: Check initial state is empty
sm = app.selection_manager
assert sm.get_selection_count('collection') == 0, "Initial selection should be empty"
print("✅ Initial state is empty")

# Test 3: Set selection
sm.set_selection('collection', ['item-1', 'item-2'])
assert sm.get_selection_count('collection') == 2, "Should have 2 items selected"
print("✅ set_selection() works")

# Test 4: Get selection
selected = sm.get_selection('collection')
assert selected == ['item-1', 'item-2'], "Should return correct item IDs"
print("✅ get_selection() works")

# Test 5: Clear selection
sm.clear_selection('collection')
assert sm.get_selection_count('collection') == 0, "Selection should be cleared"
print("✅ clear_selection() works")

# Test 6: Set selection with metadata
sm.set_selection(
    'collection',
    ['item-1'],
    metadata=[{'name': 'Test Item', 'type': 'pdf'}]
)
meta = sm.get_selection_metadata('collection')
assert len(meta) == 1, "Should have 1 metadata entry"
assert meta[0]['name'] == 'Test Item', "Metadata should be preserved"
print("✅ Metadata works")

# Test 7: Get state snapshot
snapshot = sm.get_state_snapshot('collection')
assert snapshot is not None, "Should return snapshot"
assert snapshot.count == 1, "Snapshot should have 1 item"
assert snapshot.has_selection == True, "Snapshot should indicate selection"
print("✅ State snapshot works")

print("\n🎉 All SelectionManager tests passed!")
```

**Expected Log Output:**
```
✅ SelectionManager initialized
✅ SelectionManager reference stored in main window
📌 Selection changed for collection: 0 → 2 items
📌 Selection changed for collection: 2 → 0 items
📌 Selection changed for collection: 0 → 1 items
```

---

## 3. Data Structures

### 3.1 SelectionState Data Class

```python
@dataclass
class SelectionState:
    """Immutable snapshot of selection state"""
    view_id: str                      # "collection", "library", etc.
    item_ids: List[str]               # ["item-1", "item-2", ...]
    metadata: List[Dict[str, Any]]    # [{'name': '...', 'type': '...'}, ...]
    timestamp: float                  # Unix timestamp (time.time())
    context: SelectionContext         # Enum value (COLLECTION, LIBRARY, etc.)

    # Computed properties
    @property
    def count(self) -> int:
        return len(self.item_ids)

    @property
    def has_selection(self) -> bool:
        return len(self.item_ids) > 0
```

**Purpose:**
- Immutable snapshot for debugging/logging
- Can be serialized for state persistence (future)
- Provides convenient computed properties

### 3.2 SelectionContext Enum

```python
class SelectionContext(Enum):
    """Types of views/contexts that can have selections"""
    LIBRARY = "library"           # Collections in library view
    COLLECTION = "collection"     # Items in collection view
    STEPS = "steps"               # Processing steps in step browser
    PREVIEW = "preview"           # Preview panes in output view
    ADJUST = "adjust"             # Adjust pane controls
```

**Purpose:**
- Type-safe context identification
- Easy to extend with new contexts
- Self-documenting (enum values match view_id strings)

### 3.3 Event Payload Structure

```python
# Emitted by SelectionManager.set_selection()
{
    'view_id': 'collection',           # Which view's selection changed
    'context': 'collection',           # SelectionContext enum value
    'old_selection': ['item-1'],       # Previous selection
    'new_selection': ['item-2', 'item-3'],  # New selection
    'count': 2,                        # len(new_selection)
    'metadata': [                      # Metadata for each selected item
        {'name': 'Item 2', 'type': 'pdf'},
        {'name': 'Item 3', 'type': 'image'}
    ],
    'timestamp': 1731700000.123        # Unix timestamp
}
```

**Purpose:**
- Subscribers get all info they need in one event
- No need to query SelectionManager again
- Includes old_selection for comparison logic
- Timestamp allows ordering/filtering events

---

## 4. Integration Plan

### 4.1 LibraryView Integration (Future - Phase 3)

**File:** `src/fichero/windows/main/views/library/library_view.py`
**Method:** `_on_collection_selected()` (line 567-623)

**Current Code:**
```python
def _on_collection_selected(self, widget):
    """Handle collection selection from detailed list"""
    # ...existing code...

    # Store selected collection
    self.selected_collection = collection  # Keep for backwards compatibility
```

**Add After:**
```python
    # Update SelectionManager (Phase 1)
    if hasattr(self.app, 'selection_manager'):
        self.app.selection_manager.set_selection(
            'library',
            [collection_id],
            metadata=[collection]
        )
```

**Why Defer:**
- Phase 1 only creates the infrastructure
- Integration happens in Phase 3 (multi-selection fixes)
- Keeps Phase 1 focused and testable

### 4.2 CollectionView Integration (Future - Phase 3)

**File:** `src/fichero/windows/main/views/collection/collection_view.py`
**Method:** `_on_item_selected()` (line 1678-1831)

**Current Code:**
```python
def _on_item_selected(self, widget_or_item):
    # Check if this is a list of selections (multiple selection enabled)
    if isinstance(widget_or_item, list):
        logger.info(f"📋 Multiple selection detected: {len(widget_or_item)} items")
        # For now, handle the first item in the list
        # TODO: Support displaying multiple items in output view
        if widget_or_item:
            widget_or_item = widget_or_item[0]  # ❌ ONLY USES FIRST ITEM!
```

**Future Change (Phase 3):**
```python
def _on_item_selected(self, widget_or_item):
    # Normalize to list
    if isinstance(widget_or_item, list):
        selected_items = widget_or_item
    elif widget_or_item is not None:
        selected_items = [widget_or_item]
    else:
        selected_items = []

    # Extract item IDs and metadata
    selected_item_ids = []
    selected_metadata = []
    for item in selected_items:
        item_id = # ...extract ID...
        metadata = # ...extract metadata...
        selected_item_ids.append(item_id)
        selected_metadata.append(metadata)

    # Update SelectionManager
    if hasattr(self.app, 'selection_manager'):
        self.app.selection_manager.set_selection(
            'collection',
            selected_item_ids,
            metadata=selected_metadata
        )
```

**Why Defer:**
- Phase 3 fixes multi-selection handling
- Phase 1 just provides the API
- Prevents scope creep

### 4.3 StepBrowser Integration (Future - Phase 3)

**File:** `src/fichero/windows/main/views/output/step_browser.py`
**Method:** `_on_step_selected()` (line 171-196)

**Future Change (Phase 3):**
```python
def _on_step_selected(self, widget, **kwargs):
    """Handle step selection"""
    selected_data = kwargs.get('selected_data')
    if not selected_data:
        return

    index = selected_data.get('_item_id')
    self.current_index = index

    # Update SelectionManager
    if hasattr(self.app, 'selection_manager'):
        self.app.selection_manager.set_selection(
            'steps',
            [str(index)],
            metadata=[{'index': index, 'step_data': selected_data}]
        )

    # Notify callback (existing)
    if self.on_step_selected:
        self.on_step_selected(index)
```

### 4.4 InspectorWindow Integration (Future - Could Replace Direct Updates)

**Current Pattern (Review Section 2.4):**
```python
# CollectionView directly updates Inspector
self.app.inspector_window.update_metadata(item_data, "ITEM")
```

**Future Pattern (Event-Driven):**
```python
# InspectorWindow subscribes to SELECTION_CHANGED
from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation

class InspectorWindow:
    def __init__(self, ...):
        # Subscribe to selection changes
        subscribe_to_navigation("SELECTION_CHANGED", self._on_selection_changed)

    def _on_selection_changed(self, event):
        view_id = event.data.get('view_id')
        metadata = event.data.get('metadata', [])

        if metadata:
            # Update inspector with first selected item
            self.update_metadata(metadata[0], f"{view_id.upper()}_ITEM")
        else:
            # Clear inspector or show parent
            # ...
```

**Benefits:**
- Inspector decoupled from views
- Views don't need to know about Inspector
- No race conditions (events are serialized)
- Easier to test Inspector in isolation

**Why Defer:**
- Inspector redesign is out of scope for Phase 1
- Current direct update pattern works fine
- Can migrate incrementally later

### 4.5 StatusBar Integration (Phase 2)

**This is the main integration for Phase 2!**

See Phase 2 plan for details, but high-level:

```python
# In MainWindow.__init__ or StatusBar.__init__
from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation

subscribe_to_navigation("SELECTION_CHANGED", self._on_selection_changed)

def _on_selection_changed(self, event):
    view_id = event.data.get('view_id')
    count = event.data.get('count')

    # Get total items from view
    total = # ...query from view...

    # Update status bar text
    if count == 0:
        self.status_bar.set_status(f"{total} items")
    elif count == 1:
        self.status_bar.set_status("1 item selected")
    else:
        self.status_bar.set_status(f"{count} items selected")
```

---

## 5. Backwards Compatibility

### 5.1 Keep Existing `selected_*` Attributes (Temporarily)

**Why:** Many views currently store selection locally:
- `LibraryView.selected_collection`
- `StepBrowser.current_index`

**Strategy:** Keep them during Phase 1, deprecate in Phase 4

**Example (LibraryView):**
```python
def _on_collection_selected(self, widget):
    # ... existing code ...

    # BACKWARDS COMPATIBILITY: Keep existing attribute
    self.selected_collection = collection  # Keep for now

    # NEW: Also update SelectionManager
    if hasattr(self.app, 'selection_manager'):
        self.app.selection_manager.set_selection(
            'library',
            [collection_id],
            metadata=[collection]
        )
```

**Migration Path:**
1. Phase 1: SelectionManager exists, views don't use it yet
2. Phase 2-3: Views update SelectionManager AND keep old attributes
3. Phase 4: Deprecate old attributes, add warnings
4. Phase 5: Remove old attributes entirely

### 5.2 No Changes to Existing Selection Callbacks

**What Stays the Same:**
- `_on_collection_selected()` callback signature
- `_on_item_selected()` callback signature
- `on_file_preview_requested` callback pattern

**Why:** Phase 1 is additive only. No breaking changes.

### 5.3 Deprecation Warnings (Phase 4)

**Future:**
```python
# In LibraryView
@property
def selected_collection(self):
    warnings.warn(
        "selected_collection is deprecated, use app.selection_manager.get_selection('library')",
        DeprecationWarning,
        stacklevel=2
    )
    return self._selected_collection
```

---

## 6. Success Criteria

### 6.1 Phase 1 Complete When:

- [ ] SelectionManager class created in `src/fichero/shared/selection/selection_manager.py`
- [ ] Package exports defined in `src/fichero/shared/selection/__init__.py`
- [ ] SELECTION_CHANGED event type added to `NavigationEvents` class
- [ ] SelectionManager initialized in `app.py` during startup
- [ ] MainWindow stores reference to SelectionManager
- [ ] All verification tests pass (see Step 5)
- [ ] Logs show "SelectionManager initialized" on app startup
- [ ] No errors or warnings in console during normal app usage
- [ ] App still works exactly as before (no regressions)

### 6.2 Test Scenarios

**Manual Testing:**
1. Launch app → Check logs for "SelectionManager initialized"
2. Open Python console → Verify `app.selection_manager` exists
3. Run verification test script → All tests pass
4. Use app normally → No errors, works as before

**Regression Testing:**
1. Library view: Select collection → Works as before
2. Collection view: Select item → Inspector updates
3. Collection view: Multi-select items → First item shown (expected for Phase 1)
4. Process workflow: Process single item → Works
5. Process workflow: Process all items → Works

### 6.3 What NOT to Test Yet

- [ ] Status bar showing selection counts (Phase 2)
- [ ] Multi-selection actually used in workflows (Phase 3)
- [ ] Selection preserved on back navigation (Phase 4)

---

## 7. Notes for Next Agent (Review Agent)

### 7.1 Assumptions Made

1. **Event Bus Pattern is Stable**
   - Assumed `navigation_event_bus.py` pattern is final
   - Assumed `emit_navigation_event()` is the right way to emit events
   - If event bus changes, SelectionManager needs updates

2. **App Initialization Order**
   - Assumed `library_manager` is initialized before views are created
   - SelectionManager must be initialized at same time
   - If initialization order changes, update Step 3

3. **View IDs Are Consistent**
   - Assumed view_id strings: "library", "collection", "steps", "preview"
   - If views use different IDs, update `_get_context_for_view()` mapping

4. **Single-Threaded Execution**
   - Assumed Toga apps are single-threaded (no thread safety needed)
   - If multi-threading is added later, SelectionManager needs locks

### 7.2 Design Decisions & Rationale

**Why Lists Instead of Sets for item_ids?**
- Lists preserve selection order (useful for "process in order")
- Lists allow duplicates (if needed for edge cases)
- Lists are JSON-serializable (sets are not)
- Performance: selection lists are small (<100 items)

**Why Separate _metadata Dict?**
- Keeps _selections dict simple (just IDs)
- Metadata is optional (not always provided)
- Easier to debug (can inspect IDs separately)
- Prevents bloating SelectionState with unused data

**Why Emit Events Even When Metadata Changes?**
- Decided NOT to emit if only metadata changes (item_ids are same)
- Rationale: Prevents event spam when metadata is updated separately
- Trade-off: Subscribers might miss metadata-only updates

**Why Store Context in SelectionState?**
- Makes snapshots self-contained (for logging/debugging)
- Allows future filtering: "get all selections in PREVIEW context"
- Minimal overhead (just an enum value)

### 7.3 Potential Risks & Concerns

**Risk 1: Event Spam**
- If views call `set_selection()` in a loop, many events emitted
- Mitigation: Compare old vs new selection, skip if unchanged
- Still a risk if views call with different metadata repeatedly

**Risk 2: Memory Leaks**
- If metadata contains large objects, memory could accumulate
- Mitigation: Use `.copy()` to prevent references to original objects
- Still a risk if metadata itself contains large binary data

**Risk 3: Metadata/ID Mismatch**
- If caller passes metadata with wrong length, data is inconsistent
- Mitigation: Validate metadata length matches item_ids, log warning
- Still a risk if caller ignores warning and proceeds

**Risk 4: View ID Collisions**
- If two views use same view_id, selections will conflict
- Mitigation: Use context-specific view_ids (e.g., "collection:123")
- Current design assumes one collection view at a time

**Risk 5: Stale Event Subscribers**
- If views don't unsubscribe, callbacks persist after view is destroyed
- Mitigation: NavigationEventBus already handles this (see review)
- Still a risk if callbacks reference destroyed views

### 7.4 Questions for Review Agent

1. **Event Payload Design:**
   - Is the event payload structure complete?
   - Should we include `view_name` (human-readable) in addition to `view_id`?
   - Should we include `change_type` enum (ADDED, REMOVED, REPLACED)?

2. **Backwards Compatibility:**
   - Is the migration path clear enough?
   - Should we add deprecation warnings in Phase 1 or wait until Phase 4?
   - Should we keep `selected_collection` attribute forever (for debugging)?

3. **Testing:**
   - Are the verification tests sufficient?
   - Should we add unit tests for SelectionManager?
   - Should we add integration tests for SELECTION_CHANGED events?

4. **Performance:**
   - Is copying lists/dicts too expensive?
   - Should we use weak references for metadata?
   - Should we add a max metadata size limit?

5. **Future-Proofing:**
   - Should SelectionState be serializable (for state persistence)?
   - Should we support undo/redo of selections?
   - Should we support selection "transactions" (batch updates)?

6. **Error Handling:**
   - What if `emit_navigation_event()` raises an exception?
   - Should `set_selection()` be defensive and catch all errors?
   - Should we log every selection change or only errors?

### 7.5 Recommended Review Checklist

When reviewing this plan, check:

- [ ] **Architecture**: Does SelectionManager fit with existing patterns?
- [ ] **Event Design**: Is SELECTION_CHANGED event payload complete?
- [ ] **Integration**: Are all integration points identified?
- [ ] **Backwards Compatibility**: Is migration path clear and safe?
- [ ] **Testing**: Are success criteria measurable and complete?
- [ ] **Documentation**: Are all design decisions explained?
- [ ] **Edge Cases**: Are error paths handled (None values, empty lists, etc.)?
- [ ] **Performance**: Will this scale to 1000+ items in a collection?
- [ ] **Code Quality**: Is the implementation code clean and well-documented?

### 7.6 Out of Scope for Phase 1

The following are explicitly NOT included in this phase:

1. Status bar integration (Phase 2)
2. Multi-selection workflow fixes (Phase 3)
3. Selection preservation on navigation (Phase 4)
4. Inspector window event-driven updates (Future)
5. Selection undo/redo (Future)
6. Selection state persistence (Future)
7. Selection filtering/searching (Future)
8. Keyboard shortcuts for selection (Future)

---

## Appendix A: File Changes Summary

### New Files Created

1. `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/selection/selection_manager.py` (400 lines)
2. `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/selection/__init__.py` (3 lines)

### Existing Files Modified

1. `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/navigation/navigation_event_bus.py`
   - Line 97: Add `SELECTION_CHANGED = "selection_changed"`

2. `/Users/dtubb/code/fichero_main/fichero/src/fichero/app.py`
   - After library_manager init (~line 180): Add SelectionManager initialization (4 lines)

3. `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`
   - Line 84: Add SelectionManager reference storage (6 lines)

**Total Changes:** 2 new files, 3 modified files, ~410 lines added

---

## Appendix B: Implementation Timeline

### Estimated Effort

| Task | Estimated Time | Notes |
|------|---------------|-------|
| Create SelectionManager class | 2 hours | 400 lines, well-defined spec |
| Add event type constant | 5 minutes | One line change |
| Initialize in app.py | 10 minutes | Simple initialization |
| Store reference in main_window.py | 10 minutes | Simple reference storage |
| Write verification tests | 30 minutes | 7 test cases |
| Manual testing & debugging | 1 hour | Verify no regressions |
| Documentation review | 30 minutes | Ensure all docs accurate |
| **Total** | **~4.5 hours** | For experienced developer |

### Implementation Order

1. Create SelectionManager class (can develop/test in isolation)
2. Add event type constant (prerequisite for step 1 to emit events)
3. Initialize in app.py (makes manager available)
4. Store reference in main_window.py (makes it accessible to views)
5. Run verification tests (validates implementation)
6. Manual regression testing (ensures no breakage)

---

## Appendix C: Code Review Questions

When reviewing the implementation, ask:

### Correctness
- Does `set_selection()` correctly detect changes?
- Does `get_selection()` return a copy (prevent mutation)?
- Does event payload include all necessary data?
- Are None values handled safely?

### Performance
- Is copying lists/dicts performant for 100+ items?
- Are events only emitted when necessary (not on every call)?
- Is metadata stored efficiently (no duplicates)?

### Reliability
- What if `emit_navigation_event()` fails?
- What if view calls `set_selection()` with invalid data?
- What if metadata length mismatches item_ids length?

### Maintainability
- Is the code well-documented?
- Are method signatures clear?
- Would a new developer understand the architecture?
- Are naming conventions consistent?

### Future-Proofing
- Can we add new contexts easily?
- Can we extend metadata without breaking changes?
- Can we support new event types?

---

**End of Phase 1 Implementation Plan**

This plan is ready for review and implementation. All design decisions have been documented, all integration points have been identified, and all risks have been assessed.
