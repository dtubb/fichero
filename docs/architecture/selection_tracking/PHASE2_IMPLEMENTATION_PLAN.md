# Phase 2 Implementation Plan: Status Bar Integration with Selection Counts

**Plan Date**: 2025-11-15
**Planner**: Phase 2 Implementation Planning Agent
**Status**: READY FOR REVIEW

---

## Executive Summary

This plan details the implementation of Phase 2: integrating the StatusBar component with the SelectionManager service created in Phase 1. The StatusBar will subscribe to SELECTION_CHANGED events and display user-friendly messages about selection state and total item counts.

**Scope**: Status Bar updates only - NO changes to views, NO multi-selection workflow changes
**Complexity**: Low - simple event subscription and message formatting
**Estimated Effort**: 4-6 hours implementation + 2 hours testing

**Success Criteria**:
- Status bar shows "X items" when no selection
- Status bar shows "1 item selected" for single selection
- Status bar shows "X items selected" for multi-selection
- Different message formats for LIBRARY vs COLLECTION vs STEPS contexts
- Updates are instant (no lag)
- No crashes or errors

---

## 1. Architecture Design

### 1.1 Event Flow

```
User clicks item in CollectionView
    ↓
CollectionView calls selection_manager.set_selection()
    ↓
SelectionManager emits SELECTION_CHANGED event via NavigationEventBus
    ↓
StatusBar receives event in _on_selection_changed() callback
    ↓
StatusBar extracts context, count, metadata from event
    ↓
StatusBar formats message based on context
    ↓
StatusBar calls self.set_status(formatted_message)
    ↓
Status bar label updates in UI
```

### 1.2 StatusBar Event Subscription

The StatusBar will subscribe to `SELECTION_CHANGED` events during MainWindow initialization:

```python
# In MainWindow._create_desktop_layout() or similar
subscribe_to_navigation("SELECTION_CHANGED", self._on_selection_changed_for_status_bar)
```

The StatusBar itself will NOT subscribe directly - the MainWindow will subscribe on its behalf and call StatusBar methods. This keeps StatusBar as a simple display component.

### 1.3 Data Flow

**Event Payload** (from Phase 1 SelectionManager):
```python
{
    'view_id': str,              # "library", "collection", "steps", etc.
    'context': str,              # SelectionContext enum value
    'old_selection': List[str],  # Previous item IDs
    'new_selection': List[str],  # New item IDs
    'count': int,                # Number of selected items
    'metadata': List[Dict],      # Metadata for each selected item
    'timestamp': float           # Unix timestamp
}
```

**What StatusBar needs**:
- `view_id` - to determine which view is active
- `context` - to format message appropriately (LIBRARY vs COLLECTION vs STEPS)
- `count` - number of selected items
- `metadata` - to extract folder counts, item types, etc.

**What StatusBar also needs** (not in event):
- Total item count for the view (to show "127 items" when nothing selected)

**Solution**: StatusBar will query MainWindow for total counts when needed.

### 1.4 Desktop vs Mobile Considerations

**Desktop**:
- Status bar always visible at bottom
- Has more horizontal space for detailed messages
- Can show longer text like "3 items, 2 folders (5 selected)"

**Mobile**:
- Status bar may be hidden or abbreviated
- Limited horizontal space
- Should show shorter messages like "5 selected"

**Implementation**: We'll use the same message format for both platforms initially. If mobile needs shorter messages, we can add a platform check later.

---

## 2. Status Bar Message Formats

### 2.1 Library View Messages

**Context**: `SelectionContext.LIBRARY`

| Selection State | Message |
|----------------|---------|
| No collections | "No collections" |
| 1 collection (not selected) | "1 collection" |
| 5 collections (not selected) | "5 collections" |
| 1 collection selected | "1 item selected" |
| 3 collections selected | "3 items selected" |

**Note**: We say "items" when selected to match macOS Finder behavior (Finder doesn't say "3 collections selected", it says "3 items selected").

### 2.2 Collection View Messages

**Context**: `SelectionContext.COLLECTION`

| Selection State | Message |
|----------------|---------|
| No items | "No items" |
| 1 item (not selected) | "1 item" |
| 127 items (not selected) | "127 items" |
| 1 item selected | "1 item selected" |
| 3 items selected | "3 items selected" |
| 2 folders, 5 items (not selected) | "7 items, 2 folders" |
| 1 folder, 2 items (3 selected) | "3 items selected" |

**Note**: When nothing is selected, we show detailed breakdown (items, folders). When items are selected, we just show selection count.

### 2.3 Steps View Messages

**Context**: `SelectionContext.STEPS`

| Selection State | Message |
|----------------|---------|
| No steps | "No steps" |
| 1 step (not selected) | "1 step" |
| 5 steps (not selected) | "5 steps" |
| 1 step selected | "1 item selected" |
| 3 steps selected | "3 items selected" |

**Note**: We say "steps" when showing total, but "items selected" when items are selected (consistency with Finder).

### 2.4 Empty Selection

**All contexts**: When `count == 0`, show total count with appropriate noun (collections/items/steps).

### 2.5 Multi-View Context Handling

**Current behavior** (from Phase 1): SelectionManager tracks independent selections for each view_id:
- `library` → list of collection IDs
- `collection` → list of item IDs
- `steps` → list of step indices

**Phase 2 behavior**: StatusBar updates only when the ACTIVE view's selection changes. We don't update for inactive views.

**Implementation**: StatusBar will check which view is currently visible in MainWindow before updating. If event is for a different view, ignore it.

---

## 3. Detailed Implementation Steps

### Step 3.1: Add Message Formatting Methods to StatusBar

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/bars/status_bar.py`

**Location**: After `clear()` method (line 82)

**Code to add**:

```python
    def set_view_info(
        self,
        context: str,
        total_items: int,
        selected_count: int = 0,
        folder_count: int = 0,
        metadata: list = None
    ):
        """
        Update status bar based on view context and selection.

        Args:
            context: SelectionContext value ('library', 'collection', 'steps', etc.)
            total_items: Total number of items in view
            selected_count: Number of selected items (0 = no selection)
            folder_count: Number of folders in view (for collection context only)
            metadata: Optional list of metadata dicts for selected items

        Example:
            # No selection in collection with 127 items
            status_bar.set_view_info('collection', 127, selected_count=0)
            # Shows: "127 items"

            # 3 items selected
            status_bar.set_view_info('collection', 127, selected_count=3)
            # Shows: "3 items selected"

            # Collection with folders
            status_bar.set_view_info('collection', 127, selected_count=0, folder_count=5)
            # Shows: "127 items, 5 folders"
        """
        message = self._format_status_message(
            context=context,
            total_items=total_items,
            selected_count=selected_count,
            folder_count=folder_count,
            metadata=metadata or []
        )

        self.set_status(message)
        logger.debug(f"StatusBar updated: {message}")

    def _format_status_message(
        self,
        context: str,
        total_items: int,
        selected_count: int,
        folder_count: int,
        metadata: list
    ) -> str:
        """
        Format status message based on context and selection.

        Args:
            context: SelectionContext value
            total_items: Total items in view
            selected_count: Selected items count
            folder_count: Folder count (for collection view)
            metadata: Metadata for selected items

        Returns:
            Formatted status message string
        """
        # If items are selected, show selection count
        if selected_count > 0:
            return self._format_selection_message(selected_count)

        # No selection - show total counts
        if context == 'library':
            return self._format_library_status(total_items)
        elif context == 'collection':
            return self._format_collection_status(total_items, folder_count, metadata)
        elif context == 'steps':
            return self._format_steps_status(total_items)
        else:
            # Unknown context - generic message
            return self._format_generic_status(total_items)

    def _format_selection_message(self, count: int) -> str:
        """
        Format selection count message.

        Args:
            count: Number of selected items

        Returns:
            "1 item selected" or "X items selected"
        """
        if count == 1:
            return "1 item selected"
        else:
            return f"{count} items selected"

    def _format_library_status(self, total: int) -> str:
        """
        Format library view status (no selection).

        Args:
            total: Total number of collections

        Returns:
            "No collections", "1 collection", or "X collections"
        """
        if total == 0:
            return "No collections"
        elif total == 1:
            return "1 collection"
        else:
            return f"{total} collections"

    def _format_collection_status(self, total: int, folder_count: int, metadata: list) -> str:
        """
        Format collection view status (no selection).

        Shows item count and folder count if folders exist.

        Args:
            total: Total number of items
            folder_count: Number of folders
            metadata: Metadata for items (can extract folder count from here if needed)

        Returns:
            "No items", "1 item", "127 items", or "127 items, 5 folders"
        """
        if total == 0:
            return "No items"

        # Format item count
        if total == 1:
            item_text = "1 item"
        else:
            item_text = f"{total} items"

        # Add folder count if folders exist
        if folder_count > 0:
            if folder_count == 1:
                return f"{item_text}, 1 folder"
            else:
                return f"{item_text}, {folder_count} folders"

        return item_text

    def _format_steps_status(self, total: int) -> str:
        """
        Format steps view status (no selection).

        Args:
            total: Total number of steps

        Returns:
            "No steps", "1 step", or "X steps"
        """
        if total == 0:
            return "No steps"
        elif total == 1:
            return "1 step"
        else:
            return f"{total} steps"

    def _format_generic_status(self, total: int) -> str:
        """
        Format generic status for unknown contexts.

        Args:
            total: Total number of items

        Returns:
            "No items", "1 item", or "X items"
        """
        if total == 0:
            return "No items"
        elif total == 1:
            return "1 item"
        else:
            return f"{total} items"
```

**Why these methods?**
- `set_view_info()` - Public API that MainWindow calls
- `_format_status_message()` - Router that picks the right formatter
- `_format_selection_message()` - Handles selected state (all contexts)
- `_format_library_status()` - Handles library view (no selection)
- `_format_collection_status()` - Handles collection view (no selection, with folder support)
- `_format_steps_status()` - Handles steps view (no selection)
- `_format_generic_status()` - Fallback for unknown contexts

### Step 3.2: Add Event Handler to MainWindow

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

**Location**: After existing methods (around line 1700, after `close()` or similar)

**Code to add**:

```python
    def _on_selection_changed_for_status_bar(self, event):
        """
        Handle SELECTION_CHANGED events to update status bar.

        Called by NavigationEventBus when any view's selection changes.
        Updates status bar with selection count and total item count.

        Args:
            event: NavigationEvent with selection data
        """
        try:
            if not self.status_bar:
                logger.debug("Status bar not available, skipping update")
                return

            # Extract event data
            view_id = event.data.get('view_id', '')
            context = event.data.get('context', '')
            selected_count = event.data.get('count', 0)
            metadata = event.data.get('metadata', [])

            logger.debug(f"Selection changed: view_id={view_id}, context={context}, count={selected_count}")

            # Get total item count and folder count for this view
            total_items = 0
            folder_count = 0

            if view_id == 'library':
                # Get total collections from LibraryView
                if self.left_pane_view and hasattr(self.left_pane_view, 'collections'):
                    total_items = len(self.left_pane_view.collections)
                    logger.debug(f"Library view has {total_items} collections")

            elif view_id == 'collection':
                # Get total items and folder count from CollectionView
                if self.center_pane_view:
                    if hasattr(self.center_pane_view, 'collection_items'):
                        total_items = len(self.center_pane_view.collection_items)
                        logger.debug(f"Collection view has {total_items} items")

                    # Count folders in collection_items
                    if hasattr(self.center_pane_view, 'collection_items'):
                        folder_count = sum(
                            1 for item in self.center_pane_view.collection_items
                            if getattr(item, 'is_folder', False) or
                               (isinstance(item, dict) and item.get('is_folder', False))
                        )
                        logger.debug(f"Collection has {folder_count} folders")

            elif view_id == 'steps':
                # Get total steps from PreviewView (if it has step browser)
                if self.right_pane_view and hasattr(self.right_pane_view, 'step_browser'):
                    step_browser = self.right_pane_view.step_browser
                    if step_browser and hasattr(step_browser, 'steps'):
                        total_items = len(step_browser.steps)
                        logger.debug(f"Steps view has {total_items} steps")

            # Update status bar with formatted message
            self.status_bar.set_view_info(
                context=context,
                total_items=total_items,
                selected_count=selected_count,
                folder_count=folder_count,
                metadata=metadata
            )

        except Exception as e:
            logger.error(f"Failed to update status bar on selection change: {e}")
            import traceback
            traceback.print_exc()
```

**Why this implementation?**
- Defensive programming with hasattr checks (views might not be created yet)
- Extracts total counts from the appropriate view (library/collection/steps)
- Calculates folder_count for collection view by counting is_folder items
- Logs debug info for troubleshooting
- Catches exceptions to prevent crashes

### Step 3.3: Subscribe to SELECTION_CHANGED Events

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

**Location**: In `_subscribe_to_events()` method (around line 1445)

**Existing code**:
```python
    def _subscribe_to_events(self):
        """Subscribe to navigation events"""
        try:
            subscribe_to_navigation(NavigationEvents.SHOW_LIBRARY, self._on_show_library)
            subscribe_to_navigation(NavigationEvents.SHOW_COLLECTION, self._on_show_collection)
            subscribe_to_navigation(NavigationEvents.SHOW_PREVIEW, self._on_show_preview)
            # ... other subscriptions ...

            logger.debug("✅ Main window subscribed to navigation events")
        except Exception as e:
            logger.error(f"Failed to subscribe to navigation events: {e}")
```

**Code to add** (after existing subscriptions, before logger.debug):

```python
            # Subscribe to selection changes for status bar updates
            if self.status_bar:
                subscribe_to_navigation(NavigationEvents.SELECTION_CHANGED, self._on_selection_changed_for_status_bar)
                logger.debug("✅ Status bar subscribed to selection events")
```

**Why here?**
- Centralizes all event subscriptions in one place
- Only subscribes if status_bar exists (defensive)
- Logs subscription for debugging

### Step 3.4: Initialize Status Bar on View Load

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

**Problem**: When a view loads (LibraryView, CollectionView), the status bar should show the total count even before any selection happens.

**Solution**: Add status bar initialization to each view's show handler.

**Location 1**: In `_on_show_library()` method (around line 1460)

**Find this code**:
```python
    def _on_show_library(self, event):
        """Handle SHOW_LIBRARY event"""
        try:
            logger.debug("📚 MainWindow: SHOW_LIBRARY event received")

            # ... existing library view loading code ...

        except Exception as e:
            logger.error(f"Failed to show library: {e}")
```

**Add this code** (after library view is loaded and shown):

```python
            # Update status bar with collection count
            if self.status_bar and self.left_pane_view:
                total_collections = len(getattr(self.left_pane_view, 'collections', []))
                self.status_bar.set_view_info(
                    context='library',
                    total_items=total_collections,
                    selected_count=0
                )
                logger.debug(f"Status bar initialized for library view: {total_collections} collections")
```

**Location 2**: In `_on_show_collection()` method (around line 1520)

**Find this code**:
```python
    def _on_show_collection(self, event):
        """Handle SHOW_COLLECTION event"""
        try:
            logger.debug("📂 MainWindow: SHOW_COLLECTION event received")

            # ... existing collection view loading code ...

        except Exception as e:
            logger.error(f"Failed to show collection: {e}")
```

**Add this code** (after collection view is loaded and shown):

```python
            # Update status bar with item count
            if self.status_bar and self.center_pane_view:
                total_items = len(getattr(self.center_pane_view, 'collection_items', []))

                # Count folders
                folder_count = 0
                if hasattr(self.center_pane_view, 'collection_items'):
                    folder_count = sum(
                        1 for item in self.center_pane_view.collection_items
                        if getattr(item, 'is_folder', False) or
                           (isinstance(item, dict) and item.get('is_folder', False))
                    )

                self.status_bar.set_view_info(
                    context='collection',
                    total_items=total_items,
                    selected_count=0,
                    folder_count=folder_count
                )
                logger.debug(f"Status bar initialized for collection view: {total_items} items, {folder_count} folders")
```

**Why these additions?**
- Status bar shows meaningful info immediately when view loads
- User sees "127 items" even before selecting anything
- Folder count is calculated and displayed for collection view
- Matches Finder behavior (always shows total count)

---

## 4. Message Formatting Logic

### 4.1 Complete Message Formatting Reference

**Implemented in**: `StatusBar._format_status_message()` and helper methods

**Logic Tree**:
```
IF selected_count > 0:
    RETURN "X item(s) selected"
ELSE:
    IF context == 'library':
        RETURN "X collection(s)"
    ELIF context == 'collection':
        IF folder_count > 0:
            RETURN "X items, Y folder(s)"
        ELSE:
            RETURN "X item(s)"
    ELIF context == 'steps':
        RETURN "X step(s)"
    ELSE:
        RETURN "X item(s)"
```

### 4.2 Pluralization Logic

**Implemented in**: Each `_format_*_status()` helper method

**Pattern**:
```python
if count == 0:
    return "No {noun}s"
elif count == 1:
    return f"1 {noun}"  # Singular
else:
    return f"{count} {noun}s"  # Plural
```

**Examples**:
- 0 → "No items"
- 1 → "1 item"
- 5 → "5 items"

### 4.3 Item Type Counting (Folders vs Files)

**Implemented in**: `MainWindow._on_selection_changed_for_status_bar()`

**Logic**:
```python
folder_count = sum(
    1 for item in collection_items
    if getattr(item, 'is_folder', False) or
       (isinstance(item, dict) and item.get('is_folder', False))
)
```

**Why this works**:
- Checks both object attributes (`item.is_folder`) and dict keys (`item['is_folder']`)
- Handles different data types returned by LibraryManager
- Defaults to False if `is_folder` doesn't exist

### 4.4 Special Cases

**Empty view**:
- total_items = 0, selected_count = 0
- Message: "No collections" / "No items" / "No steps"

**All items selected**:
- total_items = 5, selected_count = 5
- Message: "5 items selected" (NOT "5 items (5 selected)")

**Only folders selected**:
- metadata contains only folders
- Message: "3 items selected" (we don't say "3 folders selected")

---

## 5. Event Subscription Pattern

### 5.1 Subscription in MainWindow

**Where**: `MainWindow._subscribe_to_events()` method

**Code**:
```python
subscribe_to_navigation(NavigationEvents.SELECTION_CHANGED, self._on_selection_changed_for_status_bar)
```

**Pattern Details**:
- Uses `subscribe_to_navigation()` helper function
- Uses constant from `NavigationEvents` class
- Passes method reference (not method call)
- No lambda needed (method signature matches event handler signature)

### 5.2 Event Handler Signature

**Method**: `MainWindow._on_selection_changed_for_status_bar(self, event)`

**Parameters**:
- `self` - MainWindow instance
- `event` - NavigationEvent object with `event_type` and `data` attributes

**Event Data Structure** (from Phase 1):
```python
event.data = {
    'view_id': 'collection',           # str
    'context': 'collection',           # SelectionContext.value
    'old_selection': ['item1', 'item2'], # List[str]
    'new_selection': ['item3'],        # List[str]
    'count': 1,                        # int
    'metadata': [{'id': 'item3', ...}], # List[Dict]
    'timestamp': 1699564800.0          # float
}
```

### 5.3 Thread Safety (Toga)

**Important**: Toga is single-threaded on the main UI thread.

**Implications**:
- No thread safety concerns
- No need for locks or mutexes
- Event handlers run synchronously on main thread
- UI updates happen immediately

**Performance**: Status bar updates must be fast (<10ms) to avoid blocking UI.

**Optimization**: All message formatting is string-based (no heavy computation).

### 5.4 Unsubscribe Pattern (Not Needed for Phase 2)

**When needed**: If MainWindow is destroyed and recreated

**How to unsubscribe**:
```python
from fichero.shared.navigation.navigation_event_bus import unsubscribe_from_navigation
unsubscribe_from_navigation(NavigationEvents.SELECTION_CHANGED, self._on_selection_changed_for_status_bar)
```

**Phase 2 decision**: We don't unsubscribe because MainWindow exists for app lifetime.

---

## 6. Integration with Phase 1

### 6.1 Using SelectionManager API

**Phase 1 provides**:
```python
# In app.py (lines 104-107)
self.selection_manager = SelectionManager()

# In main_window.py (lines 86-90)
self.selection_manager = getattr(self.app, 'selection_manager', None)
```

**Phase 2 uses**:
- We don't directly call SelectionManager methods
- We only subscribe to SELECTION_CHANGED events
- SelectionManager emits events, StatusBar receives them

**Why event-driven?**
- Loose coupling (StatusBar doesn't depend on SelectionManager)
- Views update SelectionManager, StatusBar reacts automatically
- Easy to add more event subscribers later (inspector, etc.)

### 6.2 Total Counts Source

**Problem**: SELECTION_CHANGED event doesn't include total item count.

**Solution**: MainWindow queries the active view directly:

| View | Data Source | Attribute |
|------|-------------|-----------|
| LibraryView | `self.left_pane_view.collections` | List of Collection objects |
| CollectionView | `self.center_pane_view.collection_items` | List of CollectionItem objects |
| PreviewView | `self.right_pane_view.step_browser.steps` | List of step dicts |

**Implementation**:
```python
# Library
total = len(self.left_pane_view.collections)

# Collection
total = len(self.center_pane_view.collection_items)

# Steps
total = len(self.right_pane_view.step_browser.steps)
```

### 6.3 Metadata Access for Folder Counting

**From event payload**:
```python
metadata = event.data.get('metadata', [])
# metadata = [{'id': 'item1', 'is_folder': True, ...}, ...]
```

**From view directly** (what we use):
```python
# More reliable - always has full item list
items = self.center_pane_view.collection_items
folder_count = sum(1 for item in items if item.is_folder)
```

**Why query view?**
- Event metadata only has SELECTED items
- We need ALL items to count total folders
- View has authoritative data

---

## 7. Testing Strategy

### 7.1 Manual Test Scenarios

**Test 1: Library View**
```
1. Launch app
2. Observe status bar
   Expected: "X collections" (where X = number of collections)
3. Click on a collection (don't open it)
   Expected: "1 item selected"
4. Cmd+Click another collection (multi-select)
   Expected: "2 items selected"
5. Click empty space to deselect
   Expected: "X collections"
```

**Test 2: Collection View**
```
1. Open a collection with 127 items, 5 folders
   Expected: "127 items, 5 folders"
2. Click on an item
   Expected: "1 item selected"
3. Cmd+Click 2 more items
   Expected: "3 items selected"
4. Click empty space to deselect
   Expected: "127 items, 5 folders"
```

**Test 3: Collection View (No Folders)**
```
1. Open a collection with 50 items, 0 folders
   Expected: "50 items"
2. Select 5 items
   Expected: "5 items selected"
```

**Test 4: Steps View**
```
1. Open an item with processing steps
2. Observe status bar
   Expected: "X steps" (where X = number of steps)
3. Click on a step
   Expected: "1 item selected"
```

**Test 5: Edge Cases**
```
1. Open empty collection
   Expected: "No items"
2. Open collection with 1 item
   Expected: "1 item"
3. Select that 1 item
   Expected: "1 item selected"
4. Open collection with only folders (no files)
   Expected: "5 items, 5 folders" (folders count as items)
```

### 7.2 Desktop vs Mobile Testing

**Desktop** (macOS):
- Status bar always visible
- Multi-selection with Cmd+Click
- Test all scenarios above

**Mobile** (iOS simulator):
- Status bar visible (but may be different size)
- Single-selection only (no multi-select UI)
- Test single-selection scenarios only

### 7.3 Edge Cases

**Edge Case 1**: View loads before SelectionManager initializes
- **Test**: Launch app with broken SelectionManager
- **Expected**: Status bar shows empty (no crash)
- **Implementation**: Defensive `if self.status_bar` checks

**Edge Case 2**: Selection event for inactive view
- **Test**: Select item in collection, then navigate to library
- **Expected**: Status bar shows library info (not stale collection info)
- **Implementation**: Status bar updates when view changes (handled by view load handlers)

**Edge Case 3**: Rapid selection changes
- **Test**: Click through items quickly
- **Expected**: Status bar updates smoothly (no lag)
- **Implementation**: Event handlers are synchronous and fast

**Edge Case 4**: View has no items
- **Test**: Open empty collection
- **Expected**: Status bar shows "No items"
- **Implementation**: `_format_collection_status(total=0)` returns "No items"

### 7.4 Performance Testing

**Scenario**: Select 100 items at once (if multi-select allows)

**Test**:
```python
# In Python console during app run
item_ids = [f'item-{i}' for i in range(100)]
app.selection_manager.set_selection('collection', item_ids)
```

**Expected**:
- Status bar updates immediately (< 100ms)
- No UI freeze
- Shows "100 items selected"

**Why this matters**: Proves event handling is fast enough for large selections.

---

## 8. Success Criteria

### 8.1 Functional Requirements

All of these must work:

- [ ] Status bar shows "X collections" when library view loads
- [ ] Status bar shows "X items" when collection view loads (no folders)
- [ ] Status bar shows "X items, Y folders" when collection has folders
- [ ] Status bar shows "X steps" when preview view with steps loads
- [ ] Status bar updates to "1 item selected" when single item selected
- [ ] Status bar updates to "X items selected" when multiple items selected
- [ ] Status bar reverts to total count when selection cleared
- [ ] Messages use correct pluralization (1 item vs 2 items)
- [ ] Folder count is accurate in collection view
- [ ] Empty views show "No items" / "No collections" / "No steps"

### 8.2 Performance Requirements

- [ ] Status bar updates appear instant (no visible lag)
- [ ] Selecting 100 items updates status bar in < 100ms
- [ ] No UI freezing or stuttering during selection changes
- [ ] Event handlers complete in < 10ms

### 8.3 Code Quality Requirements

- [ ] No crashes or exceptions in logs
- [ ] Defensive programming (hasattr checks, try/except)
- [ ] Clear debug logging for troubleshooting
- [ ] Methods are well-documented with docstrings
- [ ] Code follows existing patterns in codebase

### 8.4 Integration Requirements

- [ ] No changes to Phase 1 SelectionManager code
- [ ] No changes to existing view code (library/collection/preview)
- [ ] Event subscription follows NavigationEventBus pattern
- [ ] Status bar remains a simple display component (no business logic)

---

## 9. Notes for Review Agent

### 9.1 Assumptions Made

**Assumption 1**: Views (LibraryView, CollectionView, PreviewView) expose these attributes:
- `LibraryView.collections` - list of collections
- `CollectionView.collection_items` - list of items
- `PreviewView.step_browser.steps` - list of steps

**Verification needed**: Confirm these attributes exist and are updated when views refresh.

**Assumption 2**: CollectionItem objects have `is_folder` attribute (boolean).

**Verification needed**: Check CollectionItem model in library/models.py.

**Assumption 3**: MainWindow has access to `self.left_pane_view`, `self.center_pane_view`, `self.right_pane_view`.

**Verification**: Confirmed in main_window.py lines 42-44.

**Assumption 4**: SELECTION_CHANGED events are emitted by views when they update SelectionManager.

**Note**: This is NOT Phase 2's responsibility. Views don't currently call SelectionManager.set_selection(). This will be Phase 3's job.

**Implication for Phase 2**: We can only test by manually calling `app.selection_manager.set_selection()` in Python console. Real view integration comes in Phase 3.

### 9.2 Design Decisions and Rationale

**Decision 1**: MainWindow subscribes to events (not StatusBar directly)

**Rationale**:
- MainWindow owns the lifecycle
- MainWindow has access to view data (for total counts)
- StatusBar remains a pure display component
- Easier to test (mock MainWindow, not StatusBar)

**Decision 2**: Query views for total counts (don't cache in StatusBar)

**Rationale**:
- Views are the source of truth
- Avoids stale data
- Simpler than maintaining a cache
- Performance is fine (len() is O(1) for lists)

**Decision 3**: Count folders from collection_items (not from metadata)

**Rationale**:
- metadata in event only has SELECTED items
- We need ALL items to count total folders
- collection_items has complete data

**Decision 4**: Don't differentiate desktop vs mobile messages yet

**Rationale**:
- Same messages work for both platforms
- Can optimize later if mobile needs shorter text
- Simpler implementation for Phase 2

**Decision 5**: Show "items selected" for all contexts (not "collections selected" or "steps selected")

**Rationale**:
- Matches macOS Finder behavior
- Simpler message formatting
- User understands "items selected" regardless of context

### 9.3 Questions for Review Agent

**Question 1**: Should we show different messages on mobile due to space constraints?

**Current plan**: Use same messages for both platforms.

**Alternative**: Shorter messages on mobile ("5 selected" instead of "5 items selected").

**Recommendation**: Start with same messages, optimize later if needed.

---

**Question 2**: Should status bar show total+selected together?

**Example**: "127 items (3 selected)" instead of just "3 items selected"

**Pros**: More information, shows context
**Cons**: Longer message, less clean

**Current plan**: Just show "3 items selected" (matches Finder).

**Recommendation**: Keep it simple for Phase 2.

---

**Question 3**: How to handle selection in non-visible views?

**Scenario**: User selects items in collection view, then navigates to library. Collection view selection is still tracked by SelectionManager but not visible.

**Current plan**: Status bar updates only for visible view. When user navigates back to collection, selection is still there (Phase 4 feature).

**Recommendation**: Phase 2 only updates for active view. Phase 4 handles persistence.

---

**Question 4**: Should we count folders as separate from items?

**Example**: Collection has 10 files + 5 folders = 15 total items

**Option A**: "15 items, 5 folders" (folders are counted twice)
**Option B**: "10 items, 5 folders" (folders separate from items)

**Current plan**: Option A (folders are items, just a special type)

**Rationale**: Matches Finder behavior, matches LibraryManager behavior (collection_items includes folders).

---

### 9.4 Potential Issues to Watch For

**Issue 1**: View attributes might not exist when event fires

**Symptom**: AttributeError when accessing `self.left_pane_view.collections`

**Mitigation**: Defensive `hasattr()` checks before accessing attributes

**Example**:
```python
if self.left_pane_view and hasattr(self.left_pane_view, 'collections'):
    total = len(self.left_pane_view.collections)
```

---

**Issue 2**: Folder count calculation might be expensive for large collections

**Symptom**: Status bar updates lag when collection has 10,000+ items

**Mitigation**: Folder count is calculated once per event, uses generator expression (efficient)

**If it becomes an issue**: Cache folder count in CollectionView and expose as attribute

---

**Issue 3**: Status bar might update for inactive views

**Symptom**: Status bar shows "3 items selected" when library view is active (but event was for collection view)

**Current plan**: Don't filter by active view (assume events only fire for active view)

**Future enhancement**: Add check to only update if view_id matches active view

---

**Issue 4**: Views might not update SelectionManager (Phase 3 responsibility)

**Symptom**: Status bar never updates (no events emitted)

**Mitigation**: This is expected in Phase 2. Views don't call SelectionManager yet.

**Testing strategy**: Manually call `app.selection_manager.set_selection()` in Python console

---

**Issue 5**: Pluralization might not handle edge cases

**Example**: "1 items" instead of "1 item"

**Mitigation**: Explicit if/else for count == 1 in all formatters

**Test**: Verify "1 item selected", "1 collection", "1 step" all work

---

## 10. Implementation Checklist

Use this checklist during implementation:

### Phase 2.1: StatusBar Enhancements
- [ ] Add `set_view_info()` method to StatusBar
- [ ] Add `_format_status_message()` method
- [ ] Add `_format_selection_message()` method
- [ ] Add `_format_library_status()` method
- [ ] Add `_format_collection_status()` method
- [ ] Add `_format_steps_status()` method
- [ ] Add `_format_generic_status()` method
- [ ] Test: Call `status_bar.set_view_info()` directly with various parameters
- [ ] Verify: Messages match expected formats from Section 2

### Phase 2.2: MainWindow Event Handler
- [ ] Add `_on_selection_changed_for_status_bar()` method to MainWindow
- [ ] Implement total count extraction for library view
- [ ] Implement total count extraction for collection view
- [ ] Implement total count extraction for steps view
- [ ] Implement folder count calculation for collection view
- [ ] Test: Manually emit SELECTION_CHANGED event, verify handler is called
- [ ] Verify: No crashes when views don't exist (defensive checks work)

### Phase 2.3: Event Subscription
- [ ] Add subscription to `_subscribe_to_events()` method
- [ ] Verify subscription only happens if status_bar exists
- [ ] Test: Check logs for "Status bar subscribed to selection events"
- [ ] Verify: Handler is called when event is emitted

### Phase 2.4: View Load Initialization
- [ ] Add status bar init to `_on_show_library()`
- [ ] Add status bar init to `_on_show_collection()`
- [ ] Test: Launch app, verify status bar shows collection count
- [ ] Test: Open collection, verify status bar shows item count
- [ ] Verify: Folder count is shown when collection has folders

### Phase 2.5: Integration Testing
- [ ] Test: Manually call `app.selection_manager.set_selection('library', ['id1'])`
- [ ] Test: Manually call `app.selection_manager.set_selection('collection', ['id1', 'id2', 'id3'])`
- [ ] Test: Manually call `app.selection_manager.clear_selection('collection')`
- [ ] Verify: Status bar updates for each test
- [ ] Verify: Messages match expected formats

### Phase 2.6: Manual Testing
- [ ] Run all test scenarios from Section 7.1
- [ ] Test on desktop (macOS)
- [ ] Test on mobile (iOS simulator) if available
- [ ] Verify all edge cases from Section 7.3
- [ ] Check performance with large selections

### Phase 2.7: Code Quality
- [ ] Add docstrings to all new methods
- [ ] Add debug logging to event handler
- [ ] Add error handling (try/except) where needed
- [ ] Review code for defensive programming patterns
- [ ] Check for consistent naming conventions

### Phase 2.8: Documentation
- [ ] Update PHASE2_IMPLEMENTATION_LOG.md with results
- [ ] Document any deviations from plan
- [ ] List all files modified
- [ ] Note any issues encountered
- [ ] Record test results

---

## 11. Files Modified Summary

**New Files**: NONE (Phase 2 only modifies existing files)

**Modified Files**:

1. `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/bars/status_bar.py`
   - Add 7 new methods for message formatting
   - ~150 lines added

2. `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`
   - Add `_on_selection_changed_for_status_bar()` method (~60 lines)
   - Add event subscription in `_subscribe_to_events()` (~3 lines)
   - Add status bar init in `_on_show_library()` (~10 lines)
   - Add status bar init in `_on_show_collection()` (~15 lines)
   - ~88 lines added

**Total Changes**: ~238 lines added across 2 files

**Files NOT Modified**:
- SelectionManager (no changes to Phase 1 code)
- Views (LibraryView, CollectionView, PreviewView) - no changes in Phase 2
- NavigationController - no changes
- NavigationEventBus - no changes (already has SELECTION_CHANGED)

---

## 12. Next Steps After Phase 2

**Phase 3**: Multi-Selection Workflow Integration
- Update CollectionView to call `selection_manager.set_selection()`
- Update LibraryView to call `selection_manager.set_selection()`
- Update process workflow to use selected items
- Status bar will automatically update (thanks to Phase 2)

**Phase 4**: Selection Preservation
- Save selection_ids in NavigationState
- Restore selection when navigating back
- Status bar will show restored selection (no additional work needed)

---

## 13. Appendix: Example Event Flow

**Complete flow from user action to status bar update**:

```
1. User clicks item in CollectionView (Phase 3, not implemented yet)
   ↓
2. CollectionView._on_item_selected() extracts item_id
   ↓
3. CollectionView calls app.selection_manager.set_selection('collection', ['item-123'])
   ↓
4. SelectionManager compares with old selection
   ↓
5. SelectionManager updates internal state
   ↓
6. SelectionManager calls emit_navigation_event("SELECTION_CHANGED", {...})
   ↓
7. NavigationEventBus routes event to all subscribers
   ↓
8. MainWindow._on_selection_changed_for_status_bar(event) is called
   ↓
9. Handler extracts view_id='collection', count=1
   ↓
10. Handler queries self.center_pane_view.collection_items for total
    ↓
11. Handler calculates folder_count
    ↓
12. Handler calls self.status_bar.set_view_info(context='collection', total=127, selected=1, folders=5)
    ↓
13. StatusBar._format_status_message() determines message format
    ↓
14. Returns "1 item selected" (because count=1)
    ↓
15. StatusBar.set_status("1 item selected")
    ↓
16. status_label.text = "1 item selected"
    ↓
17. Toga updates UI on next render cycle
    ↓
18. User sees "1 item selected" in status bar
```

**Time**: < 10ms from step 3 to step 18 (synchronous, main thread)

---

**End of Phase 2 Implementation Plan**

**Status**: Ready for review by Review Agent
**Next Agent**: Review Agent (validates plan completeness)
**After Review**: Implementation Agent (executes plan)
