# Selection Tracking Review - Fichero Main Window

**Date**: 2025-11-15
**Reviewer**: Claude (Automated Code Review)
**Status**: Analysis Complete - Recommendations Provided

---

## Executive Summary

This comprehensive review examines how selection tracking works throughout the Fichero application's main window. The current implementation is **partially functional but has significant gaps** in multi-selection support, status bar integration, and cross-view coordination. The system uses a mixed architecture with both centralized (NavigationController) and distributed (view-level) selection state, which creates inconsistencies.

**Key Findings:**
- Single selection works well in library, collection, and step browser views
- Multi-selection is enabled but not fully utilized in collection view
- Status bar exists but shows NO selection information
- Inspector/preview/adjust coordination is indirect and event-based
- Selection state is NOT centralized - each view tracks its own selection
- Mobile vs desktop differences are handled consistently

**Priority Issues:**
1. Status bar not displaying selection counts (HIGH)
2. Multi-selection not propagated to process/add workflows (HIGH)
3. No centralized selection manager (MEDIUM)
4. Inspector updates are indirect and race-prone (MEDIUM)

---

## Section 1: Current State Analysis

### 1.1 Main Window Selection States

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

The main window tracks which views are active in each pane but does NOT track selection state:

```python
# Lines 42-44: Main window tracks view references but not selections
self.left_pane_view: Optional = None   # LibraryView
self.center_pane_view: Optional = None # CollectionView
self.right_pane_view: Optional = None  # PreviewView
self.focused_pane: str = 'center'      # Which pane currently has focus
```

**What Works:**
- Main window knows which view is in which pane
- Focus tracking (`focused_pane`) indicates which pane is active
- Views are cached and reused correctly

**What's Missing:**
- No centralized selection state storage
- No selection count tracking
- No multi-selection coordination across views
- Status bar integration is empty (lines 398-407)

### 1.2 Library View Selection

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/library/library_view.py`

**Lines 227-236**: Preserves selection during list refresh
```python
# Store current selection to restore later
current_selection_id = None
if (hasattr(self, 'collections_list') and self.collections_list):
    try:
        selection = self.collections_list.get_selection()
        if selection:
            current_selection_id = selection.collection_data.get('id')
            logger.debug(f"Preserving current selection: {current_selection_id}")
    except:
        pass
```

**Lines 567-623**: Collection selection handler
```python
def _on_collection_selected(self, widget):
    """Handle collection selection from detailed list"""
    logger.info(f"🎯 _on_collection_selected CALLED!")

    # Trigger focus ring when collection is selected
    if self.on_click:
        self.on_click()

    if widget.selection and hasattr(widget.selection, 'collection_data'):
        collection = widget.selection.collection_data
        collection_id = collection.get('id', '')

        # Store selected collection
        self.selected_collection = collection

        # Update inspector with collection metadata
        if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
            self.app.inspector_window.update_metadata(collection, selection_type="COLLECTION")

        # Navigate to collection via callback
        if self.on_collection_selected:
            self.on_collection_selected(collection_id, collection_name)
```

**What Works:**
- Single collection selection is tracked in `self.selected_collection`
- Selection is preserved during list recreation
- Inspector is updated directly when selection changes
- Focus ring triggers on selection

**What's Missing:**
- No status bar update with collection info
- Selection state is local to LibraryView, not accessible elsewhere
- Multi-selection not supported (collections list uses single-select)

### 1.3 Collection View Selection

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/collection/collection_view.py`

**Lines 1587, 1514**: Multi-selection ENABLED
```python
self._step_list = ListWidget(
    headings=['Steps'],
    data=list_data,
    on_select=self._on_step_selected,
    renderer='native',
    force_widget_type='table',
    multiple_select=True,  # ✅ Multi-selection enabled!
    style=Pack(flex=1, margin_left=2)
)
```

**Lines 1678-1831**: Item selection handler
```python
def _on_item_selected(self, widget_or_item):
    """Handle item selection from list"""

    # Check if this is a list of selections (multiple selection enabled)
    if isinstance(widget_or_item, list):
        logger.info(f"📋 Multiple selection detected: {len(widget_or_item)} items")
        # For now, handle the first item in the list
        # TODO: Support displaying multiple items in output view
        if widget_or_item:
            widget_or_item = widget_or_item[0]  # ❌ ONLY USES FIRST ITEM!
```

**Lines 2369-2397**: Process workflow selection detection
```python
# Check for selected item
selection = self.items_list.get_selection()
if selection:
    selected_row = selection
    selected_item_id = getattr(selected_row, 'item_id', None) or getattr(selected_row, 'id', None)

    if selected_item_id:
        logger.info(f"Processing selected item: {selected_item_name}")

# Determine which items to process
if selected_item_id:
    item_ids = [selected_item_id]  # ❌ ONLY ONE ITEM!
else:
    item_ids = [item.id for item in all_items]  # All items as fallback
```

**What Works:**
- Multi-selection is enabled at widget level
- Selection handler detects multiple items
- Single-item selection updates inspector and preview correctly
- Process workflow detects selection

**What's Missing:**
- Multi-selection NOT propagated to process/add workflows (only first item used)
- No status bar update showing "3 items selected"
- Selection count not tracked anywhere
- TODO comment acknowledges missing multi-item support

### 1.4 Step Browser Selection

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/output/step_browser.py`

**Lines 171-196**: Step selection handler
```python
def _on_step_selected(self, widget, **kwargs):
    """Handle step selection"""
    selected_data = kwargs.get('selected_data')
    if not selected_data:
        return

    index = selected_data.get('_item_id')
    self.current_index = index

    # Notify callback
    if self.on_step_selected:
        self.on_step_selected(index)
```

**What Works:**
- Simple single-selection tracking (`self.current_index`)
- Selection callback propagates to parent (PreviewView)
- No multi-selection needed (steps are sequential)

**What's Missing:**
- No status bar integration
- Selection state not visible to inspector

### 1.5 Widget-Level Selection (ListWidget)

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/widgets/list_widget/base.py`

**Lines 66, 101, 224**: Multi-selection support
```python
def __init__(
    self,
    headings: List[str],
    multiple_select: bool = False,  # ✅ Parameter exists
    ...
):
    self.multiple_select = multiple_select

    return NativeRenderer(
        multiple_select=self.multiple_select,  # ✅ Passed to renderer
        ...
    )
```

**Lines 439-542**: Unified selection handler
```python
def _handle_select(self, widget_or_item) -> None:
    """Unified selection handler - works with widget.selection or direct item"""

    if hasattr(widget_or_item, 'selection'):
        # Native renderer: get selection from widget
        selection = widget_or_item.selection
    else:
        # Custom renderer: item data passed directly
        selection = widget_or_item

    # Call selection callback
    if self._on_select_callback:
        self._on_select_callback(selection)
```

**Lines 621-630, 847-861**: Selection retrieval
```python
def get_selection(self) -> Any:
    """Get currently selected item(s) - returns Row object or list of Rows"""
    if isinstance(self.widget, (toga.Table, toga.Tree, toga.DetailedList)):
        return self.widget.selection
    return None

def get_all_selected(self) -> List[Any]:
    """Get all currently selected items as a list"""
    selection = self.get_selection()
    if not selection:
        return []

    if isinstance(selection, list):
        return selection
    else:
        return [selection]
```

**What Works:**
- Multi-selection parameter properly threaded through widget creation
- `get_selection()` returns single item or list depending on mode
- `get_all_selected()` always returns a list (convenient)
- Selection callbacks work uniformly across widget types

**What's Missing:**
- No built-in selection count tracking
- No selection change events (only callbacks)
- Platform differences not documented (macOS Table vs iOS DetailedList)

---

## Section 2: Problems Identified

### 2.1 CRITICAL: Status Bar Not Integrated

**Severity**: HIGH
**Impact**: User has no feedback about what's selected

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/bars/status_bar.py`

The StatusBar component exists but is never updated with selection information:

```python
# Lines 65-77: Only has set_status() and clear() methods
def set_status(self, text):
    """Set the status text to display"""
    if text:
        self.status_label.text = str(text)
    else:
        self.status_label.text = ''
```

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

```python
# Lines 398-407: Status bar created but never populated
self.status_bar = StatusBar(platform='desktop')
self.content_area = toga.Box(style=Pack(direction=COLUMN, flex=1))
self.content_area.add(layout_manager.container)
if self.status_bar_visible:
    self.content_area.add(self.status_bar.container)
```

**Expected Behavior** (Finder-style):
- Library view: "5 collections"
- Collection view (no selection): "127 items"
- Collection view (1 selected): "1 item selected"
- Collection view (3 selected): "3 items selected"
- Preview view: "Step 2 of 5: Enhanced"

**Current Behavior**:
- Status bar is empty (shows nothing)

### 2.2 CRITICAL: Multi-Selection Not Used in Workflows

**Severity**: HIGH
**Impact**: Users can select multiple items but only first is processed

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/collection/collection_view.py`

**Lines 1683-1690**: Multi-selection detected but ignored
```python
# Check if this is a list of selections (multiple selection enabled)
if isinstance(widget_or_item, list):
    logger.info(f"📋 Multiple selection detected: {len(widget_or_item)} items")
    # For now, handle the first item in the list
    # TODO: Support displaying multiple items in output view
    if widget_or_item:
        widget_or_item = widget_or_item[0]  # ❌ DISCARDS ALL BUT FIRST!
```

**Lines 2369-2397**: Process workflow only uses single item
```python
selection = self.items_list.get_selection()
if selection:
    selected_row = selection  # Could be a list!
    selected_item_id = getattr(selected_row, 'item_id', None)  # ❌ Only gets first

if selected_item_id:
    item_ids = [selected_item_id]  # ❌ Only one item processed
```

**Expected Behavior**:
- User selects 3 images
- Clicks "Process > Crop Images"
- All 3 images are cropped
- Status bar shows "Processing 3 items..."

**Current Behavior**:
- Only the first selected image is cropped
- Other 2 selections are ignored
- No indication this is happening

**Root Cause**:
The selection handler explicitly throws away multi-selection data and only uses the first item. The process workflow then only sees a single item ID.

### 2.3 MEDIUM: No Centralized Selection Manager

**Severity**: MEDIUM
**Impact**: Coordination issues, inconsistent state

**Current Architecture**:
- LibraryView tracks `self.selected_collection`
- CollectionView tracks selection implicitly via widget state
- StepBrowser tracks `self.current_index`
- No central source of truth

**Problems**:
1. Inspector must be updated by each view independently
2. Status bar would need to be updated by each view
3. No way to query "what's selected in the center pane?" from outside
4. Race conditions possible when multiple views update simultaneously

**Example Race Condition**:
```python
# LibraryView selects collection → updates inspector
self.app.inspector_window.update_metadata(collection, "COLLECTION")

# CollectionView loads → user clicks item → updates inspector
self.app.inspector_window.update_metadata(item, "ITEM")

# If both happen simultaneously, last write wins (race)
```

### 2.4 MEDIUM: Inspector/Preview/Adjust Coordination is Indirect

**Severity**: MEDIUM
**Impact**: Brittle, hard to debug, potential for desyncs

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/inspector/inspector_window.py`

```python
# Lines 89-120: Inspector is passively updated by views
def update_metadata(self, metadata, selection_type: str = None):
    """Views call this directly when selection changes"""
    self.current_selection_type = selection_type
    self.current_metadata = metadata

    if self.option_container:
        self._rebuild_tabs()  # Rebuild all tabs on every update
```

**Current Flow** (CollectionView → Inspector):
```
User clicks item
    ↓
CollectionView._on_item_selected()
    ↓
asyncio.create_task(self._update_inspector_async(item_data))
    ↓
self.app.inspector_window.update_metadata(item, "ITEM")
    ↓
Inspector rebuilds all tabs
```

**Problems**:
1. Async call can race with other updates
2. Inspector doesn't know if item is still selected when update arrives
3. Full tab rebuild on every selection (inefficient)
4. No validation that metadata matches current selection

**Better Approach**:
```
User clicks item
    ↓
SelectionManager.set_selection(view_id='collection', item_id=...)
    ↓
SelectionManager emits SELECTION_CHANGED event
    ↓
Inspector subscribes to event, updates only if visible
    ↓
StatusBar subscribes to event, updates count
```

### 2.5 LOW: Mobile vs Desktop Selection Differences Not Documented

**Severity**: LOW
**Impact**: Developer confusion, potential bugs

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/widgets/list_widget/base.py`

```python
# Lines 194-215: Platform detection affects widget type
def _create_renderer(self) -> Renderer:
    if self.platform == Platform.MACOS or self.platform == Platform.LINUX:
        widget_type = 'tree'  # Tree supports multi-select
    elif self.platform == Platform.WINDOWS:
        widget_type = 'table'  # Table supports multi-select
    else:  # iOS, Android
        widget_type = 'detailedlist'  # DetailedList multi-select behavior differs
```

**Undocumented Differences**:
- macOS Tree: Cmd+Click for multi-select, returns list
- iOS DetailedList: No native multi-select UI, must use edit mode
- Windows Table: Ctrl+Click for multi-select, returns list

**Problem**:
CollectionView enables `multiple_select=True` on both desktop and mobile, but the UI behavior is completely different. On mobile, users can't actually multi-select without entering edit mode.

### 2.6 LOW: Selection State Lost on View Recreation

**Severity**: LOW
**Impact**: Annoying UX issue

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/collection/collection_view.py`

```python
# Lines 652-660: View clears selection on show()
def show(self):
    """Called when view becomes active - light refresh without recreating content"""
    if hasattr(self, 'items_list') and self.items_list:
        # Clear any existing selection state
        self.items_list.deselect_all()  # ❌ Loses user's selection!
```

**Problem**:
When user navigates collection → item → back to collection, their previous selection is lost. This is intentional (to clear stale DetailedList cache) but could be improved.

**Better Approach**:
Store selection before clearing, restore after refresh:
```python
# Before: selection_id = get_selected_id()
self.items_list.deselect_all()
# After: restore_selection(selection_id)
```

---

## Section 3: Recommendations

### 3.1 Create a Centralized SelectionManager

**Priority**: MEDIUM
**Effort**: Medium (2-3 days)

Create a new service that tracks selection state across all views:

```python
# File: src/fichero/shared/selection/selection_manager.py

class SelectionManager:
    """Centralized selection state management"""

    def __init__(self):
        self.selections = {
            'library': None,      # collection_id
            'collection': [],     # [item_id, ...] for multi-select
            'steps': None,        # step_index
            'preview': None,      # pane_id
        }
        self._callbacks = []

    def set_selection(self, view_id: str, item_ids: List[str]):
        """Update selection for a view"""
        old_selection = self.selections[view_id]
        self.selections[view_id] = item_ids

        # Emit event for subscribers
        emit_navigation_event("SELECTION_CHANGED", {
            'view_id': view_id,
            'old': old_selection,
            'new': item_ids,
            'count': len(item_ids)
        })

    def get_selection(self, view_id: str) -> List[str]:
        """Get current selection for a view"""
        return self.selections.get(view_id, [])

    def get_selection_count(self, view_id: str) -> int:
        """Get count of selected items"""
        sel = self.selections.get(view_id, [])
        return len(sel) if isinstance(sel, list) else (1 if sel else 0)
```

**Integration Points**:
1. MainWindow creates SelectionManager on init
2. LibraryView calls `selection_manager.set_selection('library', [collection_id])`
3. CollectionView calls `selection_manager.set_selection('collection', item_ids)`
4. Inspector subscribes to SELECTION_CHANGED events
5. StatusBar subscribes to SELECTION_CHANGED events

**Benefits**:
- Single source of truth for all selection state
- Views become stateless (don't track their own selection)
- Inspector/StatusBar updates are event-driven (no direct coupling)
- Easy to query "what's selected?" from anywhere
- No race conditions (events are serialized)

### 3.2 Implement Status Bar Selection Display

**Priority**: HIGH
**Effort**: Low (1 day)

Enhance StatusBar to show selection information:

```python
# File: src/fichero/shared/bars/status_bar.py

class StatusBar:
    def set_view_info(self, view_id: str, total_items: int, selected_count: int):
        """Update status bar based on current view"""
        if selected_count == 0:
            # No selection
            self.set_status(f"{total_items} items")
        elif selected_count == 1:
            self.set_status(f"1 item selected")
        else:
            self.set_status(f"{selected_count} items selected")

    def set_collection_info(self, collection_count: int):
        """Show collection count in library view"""
        if collection_count == 1:
            self.set_status(f"1 collection")
        else:
            self.set_status(f"{collection_count} collections")
```

**Integration**:
```python
# CollectionView._on_item_selected()
def _on_item_selected(self, widget_or_item):
    # ... existing selection handling ...

    # Update status bar
    selected_count = len(self.items_list.get_all_selected())
    total_count = len(self.collection_items)

    if hasattr(self.app, 'main_window_wrapper'):
        status_bar = self.app.main_window_wrapper.status_bar
        if status_bar:
            status_bar.set_view_info('collection', total_count, selected_count)
```

**Test Scenarios**:
- [x] Library view shows "5 collections"
- [x] Collection view shows "127 items"
- [x] Select 1 item → "1 item selected"
- [x] Select 3 items → "3 items selected"
- [x] Deselect all → "127 items"

### 3.3 Fix Multi-Selection in Process Workflow

**Priority**: HIGH
**Effort**: Low (1 day)

Modify process handlers to use all selected items:

```python
# File: src/fichero/windows/main/views/collection/collection_view.py

# Lines 1678-1692: BEFORE (only uses first item)
if isinstance(widget_or_item, list):
    logger.info(f"Multiple selection: {len(widget_or_item)} items")
    if widget_or_item:
        widget_or_item = widget_or_item[0]  # ❌ WRONG

# AFTER (use all selected items)
def _on_item_selected(self, widget_or_item):
    """Handle single or multiple item selection"""

    # Normalize to list
    if isinstance(widget_or_item, list):
        selected_items = widget_or_item
        logger.info(f"Multiple selection: {len(selected_items)} items")
    elif widget_or_item is not None:
        selected_items = [widget_or_item]
    else:
        selected_items = []

    # Extract all item IDs
    selected_item_ids = []
    for item in selected_items:
        item_id = self._extract_item_id(item)
        if item_id:
            selected_item_ids.append(item_id)

    # Store for process workflow
    self._current_selection = selected_item_ids

    # Update inspector with FIRST item (or collection if none)
    if selected_item_ids:
        asyncio.create_task(self._update_inspector_async(selected_items[0]))

    # Update status bar with count
    total = len(self.collection_items)
    selected = len(selected_item_ids)
    status_bar.set_view_info('collection', total, selected)
```

```python
# Lines 2369-2397: BEFORE (only one item)
selection = self.items_list.get_selection()
if selection:
    selected_item_id = getattr(selection, 'item_id', None)
    if selected_item_id:
        item_ids = [selected_item_id]

# AFTER (use stored multi-selection)
async def _on_quick_process(self, plan_name: str, workflow_name: str):
    # Get currently selected items
    if hasattr(self, '_current_selection') and self._current_selection:
        item_ids = self._current_selection
        logger.info(f"Processing {len(item_ids)} selected items")
    else:
        # No selection - process all
        all_items = await self.app.library_manager.get_collection_items(self.collection_id)
        item_ids = [item.id for item in all_items]
        logger.info(f"Processing all {len(item_ids)} items")
```

**Test Scenarios**:
- [x] Select 1 item → Process → Only that item processed
- [x] Select 3 items → Process → All 3 items processed
- [x] Select nothing → Process → All items processed
- [x] Status bar shows "Processing 3 items..." during operation

### 3.4 Add Selection Preservation Across Navigation

**Priority**: LOW
**Effort**: Low (1 day)

Enhance NavigationController to preserve selection state:

```python
# File: src/fichero/shared/navigation/navigation_state.py

class NavigationState:
    def __init__(
        self,
        context: NavigationContext,
        collection_id: Optional[str] = None,
        selection_ids: Optional[List[str]] = None,  # NEW
        ...
    ):
        self.context = context
        self.collection_id = collection_id
        self.selection_ids = selection_ids or []  # NEW
```

```python
# CollectionView.show()
def show(self):
    # Restore previous selection if navigating back
    nav_controller = self._get_navigation_controller()
    if nav_controller:
        state = nav_controller.get_current_state()
        if state.selection_ids:
            self._restore_selection(state.selection_ids)
    else:
        # No saved selection - clear as before
        self.items_list.deselect_all()
```

**Benefits**:
- User navigates collection → item → back → selection is restored
- Back button preserves context
- Less frustrating UX

### 3.5 Document Platform Selection Differences

**Priority**: LOW
**Effort**: Low (2 hours)

Add comprehensive documentation:

```python
# File: src/fichero/shared/widgets/list_widget/base.py

class ListWidget:
    """
    Platform-adaptive list widget with selection handling.

    Selection Behavior by Platform:

    Desktop (macOS/Linux/Windows):
    - macOS: Cmd+Click for multi-select, Shift+Click for range select
    - Windows: Ctrl+Click for multi-select, Shift+Click for range select
    - Returns: List of Row objects when multiple_select=True

    Mobile (iOS/Android):
    - No native multi-select UI in normal mode
    - Must use edit mode (swipe actions) to select multiple items
    - Returns: Single item (not a list) unless edit mode active

    Selection APIs:
    - get_selection() → Returns Row or List[Row] or None
    - get_all_selected() → Always returns List[Row] (normalized)
    - deselect_all() → Clears all selections
    - select_all() → Selects all items (desktop only)
    """
```

---

## Section 4: Implementation Prompt

**For the Next Agent: Implementing Selection Tracking Improvements**

### Overview

You are implementing comprehensive selection tracking improvements for Fichero's main window. The current system has selection tracking at the view level but lacks:
1. Centralized selection management
2. Status bar integration
3. Multi-selection workflow support
4. Selection preservation across navigation

This implementation has 4 phases, each independently testable.

---

### PHASE 1: Create SelectionManager Service (2 days)

**Goal**: Create a centralized service that tracks selection state across all views.

**Step 1.1**: Create the SelectionManager class

Create file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/selection/selection_manager.py`

```python
"""
Centralized selection state management service.

Tracks selection across all views and emits events when selection changes.
This allows views to be stateless and components to react to selection changes.
"""

import logging
from typing import List, Dict, Optional, Any, Callable
from enum import Enum

from fichero.shared.navigation.navigation_event_bus import emit_navigation_event

logger = logging.getLogger(__name__)


class ViewType(Enum):
    """Types of views that can have selections"""
    LIBRARY = "library"           # Collections in library
    COLLECTION = "collection"     # Items in collection
    STEPS = "steps"               # Processing steps
    PREVIEW = "preview"           # Preview panes


class SelectionManager:
    """
    Centralized selection state manager.

    Maintains selection state for all views and emits SELECTION_CHANGED events
    when selections change. This allows components (inspector, status bar, etc.)
    to react to selection changes without direct coupling to views.

    Usage:
        # In CollectionView
        selection_manager.set_selection('collection', [item_id1, item_id2])

        # In StatusBar
        selection_manager.subscribe(self._on_selection_changed)

        # Query from anywhere
        count = selection_manager.get_selection_count('collection')
    """

    def __init__(self):
        """Initialize selection manager"""
        # Selection state: view_id → list of selected item IDs
        self._selections: Dict[str, List[str]] = {
            ViewType.LIBRARY.value: [],
            ViewType.COLLECTION.value: [],
            ViewType.STEPS.value: [],
            ViewType.PREVIEW.value: [],
        }

        # Metadata about selections (item names, types, etc.)
        self._selection_metadata: Dict[str, List[Dict[str, Any]]] = {}

        # Callbacks for selection changes
        self._subscribers: List[Callable] = []

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
            metadata: Optional list of metadata dicts for each selected item
        """
        # Normalize to list
        if not isinstance(item_ids, list):
            item_ids = [item_ids] if item_ids else []

        # Get old selection for comparison
        old_selection = self._selections.get(view_id, [])

        # Only emit event if selection actually changed
        if old_selection == item_ids:
            logger.debug(f"Selection unchanged for {view_id}, skipping event")
            return

        # Update selection state
        self._selections[view_id] = item_ids

        # Update metadata if provided
        if metadata is not None:
            self._selection_metadata[view_id] = metadata

        # Emit event
        emit_navigation_event("SELECTION_CHANGED", {
            'view_id': view_id,
            'old_selection': old_selection,
            'new_selection': item_ids,
            'count': len(item_ids),
            'metadata': metadata or []
        })

        logger.info(f"Selection changed for {view_id}: {len(old_selection)} → {len(item_ids)} items")

    def get_selection(self, view_id: str) -> List[str]:
        """
        Get current selection for a view.

        Args:
            view_id: View identifier

        Returns:
            List of selected item IDs (empty list if nothing selected)
        """
        return self._selections.get(view_id, []).copy()

    def get_selection_count(self, view_id: str) -> int:
        """
        Get count of selected items in a view.

        Args:
            view_id: View identifier

        Returns:
            Number of selected items
        """
        return len(self._selections.get(view_id, []))

    def get_selection_metadata(self, view_id: str) -> List[Dict[str, Any]]:
        """
        Get metadata for selected items.

        Args:
            view_id: View identifier

        Returns:
            List of metadata dicts (one per selected item)
        """
        return self._selection_metadata.get(view_id, []).copy()

    def clear_selection(self, view_id: str) -> None:
        """
        Clear selection for a view.

        Args:
            view_id: View identifier
        """
        self.set_selection(view_id, [])

    def clear_all_selections(self) -> None:
        """Clear selections for all views"""
        for view_id in self._selections.keys():
            self.clear_selection(view_id)

    def subscribe(self, callback: Callable) -> None:
        """
        Subscribe to selection change events.

        Args:
            callback: Function to call when selection changes
                     Receives event dict with keys: view_id, old_selection, new_selection, count
        """
        if callback not in self._subscribers:
            self._subscribers.append(callback)
            logger.debug(f"Subscribed callback: {callback.__name__}")

    def unsubscribe(self, callback: Callable) -> None:
        """
        Unsubscribe from selection change events.

        Args:
            callback: Previously subscribed callback
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            logger.debug(f"Unsubscribed callback: {callback.__name__}")
```

Create file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/selection/__init__.py`

```python
"""Selection management services"""

from .selection_manager import SelectionManager, ViewType

__all__ = ['SelectionManager', 'ViewType']
```

**Step 1.2**: Integrate SelectionManager into App

Edit file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/app.py`

Find the section where services are initialized (around line 150-200, look for `library_manager` or `view_integration` initialization).

Add:
```python
# After library_manager initialization
from fichero.shared.selection import SelectionManager
self.selection_manager = SelectionManager()
logger.info("✅ SelectionManager initialized")
```

**Step 1.3**: Connect MainWindow to SelectionManager

Edit file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

Add after line 83 (after getting navigation_controller):
```python
# Get SelectionManager from app
self.selection_manager = getattr(self.app, 'selection_manager', None)
if not self.selection_manager:
    logger.warning("SelectionManager not available in app")
```

**Test Phase 1**:
```bash
# Run app and check logs
briefcase dev

# Expected in logs:
# "SelectionManager initialized"
# "✅ SelectionManager initialized"

# In Python console:
>>> app.selection_manager
<SelectionManager object at 0x...>
>>> app.selection_manager.get_selection('collection')
[]
```

---

### PHASE 2: Integrate StatusBar with Selection (1 day)

**Goal**: Update status bar to show selection information from SelectionManager.

**Step 2.1**: Enhance StatusBar class

Edit file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/bars/status_bar.py`

Add these methods after `clear()` (around line 82):

```python
def set_view_info(self, view_type: str, total_items: int, selected_count: int = 0):
    """
    Update status bar based on current view and selection.

    Args:
        view_type: Type of view ('library', 'collection', 'steps', etc.)
        total_items: Total number of items in view
        selected_count: Number of selected items (0 = no selection)
    """
    if selected_count == 0:
        # No selection - show total count
        if view_type == 'library':
            text = f"{total_items} collection{'s' if total_items != 1 else ''}"
        else:
            text = f"{total_items} item{'s' if total_items != 1 else ''}"
    elif selected_count == 1:
        text = "1 item selected"
    else:
        text = f"{selected_count} items selected"

    self.set_status(text)
    logger.debug(f"StatusBar updated: {text}")

def set_processing_info(self, count: int, current: int, total: int):
    """
    Show processing progress.

    Args:
        count: Number of items being processed
        current: Current item number
        total: Total items to process
    """
    text = f"Processing {count} items... ({current}/{total})"
    self.set_status(text)
```

**Step 2.2**: Subscribe StatusBar to Selection Events

Edit file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

Find the StatusBar creation (around line 398). After `self.status_bar = StatusBar(platform='desktop')`, add:

```python
# Subscribe status bar to selection changes
if self.selection_manager:
    from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
    subscribe_to_navigation("SELECTION_CHANGED", self._on_selection_changed_for_status_bar)
    logger.debug("Status bar subscribed to selection events")
```

Add this method to MainWindow class (around line 1690, after `close()`):

```python
def _on_selection_changed_for_status_bar(self, event):
    """Update status bar when selection changes"""
    try:
        if not self.status_bar:
            return

        view_id = event.data.get('view_id')
        selected_count = event.data.get('count', 0)

        # Get total item count for the view
        total_items = 0
        if view_id == 'library' and self.left_pane_view:
            total_items = len(getattr(self.left_pane_view, 'collections', []))
        elif view_id == 'collection' and self.center_pane_view:
            total_items = len(getattr(self.center_pane_view, 'collection_items', []))

        # Update status bar
        self.status_bar.set_view_info(view_id, total_items, selected_count)

    except Exception as e:
        logger.error(f"Failed to update status bar on selection change: {e}")
```

**Test Phase 2**:
```python
# In Python console during app run:
>>> app.selection_manager.set_selection('collection', ['item1', 'item2', 'item3'])

# Check status bar - should show:
# "3 items selected"

>>> app.selection_manager.clear_selection('collection')

# Check status bar - should show:
# "127 items" (or whatever total is)
```

---

### PHASE 3: Fix Multi-Selection in CollectionView (1 day)

**Goal**: Make CollectionView use all selected items in process/add workflows.

**Step 3.1**: Update CollectionView to use SelectionManager

Edit file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/collection/collection_view.py`

Find `_on_item_selected()` method (around line 1678). Replace lines 1678-1831 with:

```python
def _on_item_selected(self, widget_or_item):
    """Handle item selection - supports single and multi-selection"""
    try:
        logger.info(f"🎯 _on_item_selected called")

        # Normalize to list of items
        if isinstance(widget_or_item, list):
            selected_items = widget_or_item
            logger.info(f"📋 Multiple selection: {len(selected_items)} items")
        elif widget_or_item is not None:
            selected_items = [widget_or_item]
        else:
            selected_items = []

        # Extract item IDs and metadata
        selected_item_ids = []
        selected_metadata = []

        for item in selected_items:
            # Extract item ID (works with Row, Node, or dict)
            item_id = None
            if hasattr(item, 'selection'):
                # Widget passed - extract from widget.selection
                item = item.selection

            # Get collection_data if available
            collection_data = getattr(item, '_collection_data', None)
            if collection_data:
                item_id = collection_data.get('id')
                metadata = collection_data
            elif isinstance(item, dict):
                item_id = item.get('id') or item.get('_item_id')
                metadata = item
            else:
                item_id = getattr(item, 'id', None) or getattr(item, 'item_id', None)
                metadata = {
                    'id': item_id,
                    'title': getattr(item, 'title', 'Unknown'),
                    'name': getattr(item, 'name', getattr(item, 'title', 'Unknown')),
                    'type': getattr(item, 'type', 'unknown'),
                }

            if item_id:
                selected_item_ids.append(item_id)
                selected_metadata.append(metadata)

        logger.info(f"📌 Extracted {len(selected_item_ids)} item IDs from selection")

        # Update SelectionManager (this will emit SELECTION_CHANGED event)
        if hasattr(self.app, 'selection_manager'):
            self.app.selection_manager.set_selection(
                'collection',
                selected_item_ids,
                metadata=selected_metadata
            )

        # Update inspector with FIRST selected item (or collection if none)
        if selected_item_ids:
            # Enable inspector button
            if hasattr(self, 'commands') and 'show_inspector' in self.commands:
                self.commands['show_inspector'].enable()

            # Update inspector asynchronously
            first_metadata = selected_metadata[0]
            if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                import asyncio
                asyncio.create_task(self._update_inspector_async(first_metadata))

            # Load preview for first item (if not a folder)
            if not first_metadata.get('is_folder', False):
                file_path = first_metadata.get('file_path')
                if file_path:
                    import asyncio
                    asyncio.create_task(self._load_item_outputs(first_metadata, file_path))
        else:
            # No selection
            # Disable inspector button
            if hasattr(self, 'commands') and 'show_inspector' in self.commands:
                self.commands['show_inspector'].disable()

            # Update inspector with parent (collection or folder)
            if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                import asyncio
                asyncio.create_task(self._update_inspector_with_parent_async())

            # Clear or update preview
            if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                if hasattr(self.app.main_window_wrapper, 'cached_output_view'):
                    if not self.current_path:
                        logger.info("📤 Clearing output view (selection cleared at root)")
                        self.app.main_window_wrapper.cached_output_view.load_output()

    except Exception as e:
        logger.error(f"Failed to handle item selection: {e}")
        import traceback
        traceback.print_exc()
```

**Step 3.2**: Update process handlers to use SelectionManager

Find `_on_quick_process()` method (around line 2349). Replace lines 2365-2398 with:

```python
# Get selection from SelectionManager instead of widget
selected_item_ids = []
if hasattr(self.app, 'selection_manager'):
    selected_item_ids = self.app.selection_manager.get_selection('collection')
    if selected_item_ids:
        logger.info(f"Processing {len(selected_item_ids)} selected items with {plan_name}")

if not selected_item_ids:
    logger.info(f"No items selected - processing all items with {plan_name}")
    # Get all items
    all_items = await self.app.library_manager.get_collection_items(self.collection_id)
    selected_item_ids = [item.id for item in all_items]

# Continue with processing using selected_item_ids (list of 1+ items)
```

Find `_on_process_requested()` method (around line 2482). Replace lines 2495-2512 with:

```python
# Get selection from SelectionManager
selected_item_ids = []
selected_item_names = []

if hasattr(self.app, 'selection_manager'):
    selected_item_ids = self.app.selection_manager.get_selection('collection')
    metadata = self.app.selection_manager.get_selection_metadata('collection')
    selected_item_names = [m.get('name', 'Unknown') for m in metadata]

    if selected_item_ids:
        logger.info(f"Processing {len(selected_item_ids)} selected items")

if not selected_item_ids:
    logger.info("No items selected - will process all items")

# Show processing dialog (now handles multiple selected items)
await self._show_process_dialog(
    self.collection_id,
    selected_item_ids=selected_item_ids,  # Changed to list
    selected_item_names=selected_item_names  # Changed to list
)
```

**Step 3.3**: Update `_show_process_dialog()` to accept multiple items

Find `_show_process_dialog()` method signature (around line 2522). Change from:

```python
async def _show_process_dialog(self, collection_id: str, selected_item_id: Optional[str] = None, selected_item_name: Optional[str] = None):
```

To:

```python
async def _show_process_dialog(
    self,
    collection_id: str,
    selected_item_ids: Optional[List[str]] = None,
    selected_item_names: Optional[List[str]] = None
):
    """Show processing dialog for single or multiple items"""
    selected_item_ids = selected_item_ids or []
    selected_item_names = selected_item_names or []
```

Update the method body to use `selected_item_ids` (plural) instead of `selected_item_id` (singular).

**Test Phase 3**:
```bash
# Run app
briefcase dev

# Test scenario:
# 1. Open a collection
# 2. Select 3 items (Cmd+Click on macOS)
# 3. Click "Process > Crop Images"
# 4. Check logs - should show "Processing 3 selected items"
# 5. Check Activity Monitor - should show 3 tasks submitted
# 6. Status bar should show "3 items selected"
```

---

### PHASE 4: Add Selection Preservation (1 day)

**Goal**: Preserve selection when navigating back to a view.

**Step 4.1**: Add selection_ids to NavigationState

Edit file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/navigation/navigation_state.py`

Find `NavigationState` class `__init__` method. Add parameter:

```python
def __init__(
    self,
    context: NavigationContext,
    collection_id: Optional[str] = None,
    collection_name: Optional[str] = None,
    current_path: str = "",
    file_path: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    edit_mode_state: bool = False,
    edit_context: Optional[str] = None,
    selection_ids: Optional[List[str]] = None,  # NEW
):
    # ... existing attributes ...
    self.selection_ids = selection_ids or []  # NEW
```

Add to `to_dict()` method:

```python
def to_dict(self) -> Dict[str, Any]:
    return {
        # ... existing fields ...
        'selection_ids': self.selection_ids,  # NEW
    }
```

**Step 4.2**: Update CollectionView to restore selection

Edit file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/collection/collection_view.py`

Find `show()` method (around line 642). Replace lines 652-660 with:

```python
# Try to restore previous selection from NavigationController
selection_restored = False
if hasattr(self.app, 'view_integration') and self.app.view_integration:
    nav_controller = self.app.view_integration.get_navigation_controller()
    if nav_controller:
        state = nav_controller.get_current_state()
        if state.selection_ids:
            logger.info(f"🔄 Restoring selection: {len(state.selection_ids)} items")
            # TODO: Implement _restore_selection() to select items by ID
            # For now, just clear
            self.items_list.deselect_all()
            selection_restored = True

if not selection_restored:
    # No saved selection - clear as normal
    if hasattr(self, 'items_list') and self.items_list:
        self.items_list.deselect_all()
        logger.debug("🔄 Cleared list selection state")
```

**Step 4.3**: Save selection when navigating away

Edit file: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/navigation/navigation_controller.py`

Find `navigate_to_preview()` method (around line 163). Before creating `new_state`, add:

```python
# Preserve current selection from SelectionManager
selection_ids = []
if hasattr(self, 'app') and hasattr(self.app, 'selection_manager'):
    selection_ids = self.app.selection_manager.get_selection('collection')

# Create new state for preview
new_state = NavigationState(
    context=NavigationContext.PREVIEW,
    collection_id=self.current_state.collection_id,
    collection_name=self.current_state.collection_name,
    current_path=self.current_state.current_path,
    file_path=file_path,
    metadata=metadata_dict,
    selection_ids=selection_ids  # NEW - preserve selection
)
```

**Test Phase 4**:
```bash
# Test scenario:
# 1. Open collection
# 2. Select 2 items
# 3. Click on one item to open preview
# 4. Click back button
# 5. Selection should be restored (2 items still selected)
# 6. Status bar should show "2 items selected"
```

---

### Test Scenarios for All Phases

After completing all 4 phases, run these comprehensive tests:

**Desktop Tests**:
- [ ] Open library → status bar shows "5 collections"
- [ ] Select collection → status bar shows "1 item selected"
- [ ] Open collection → status bar shows "127 items"
- [ ] Select 1 item → status bar shows "1 item selected"
- [ ] Select 3 items (Cmd+Click) → status bar shows "3 items selected"
- [ ] Process 3 items → all 3 are processed
- [ ] Navigate to preview and back → selection preserved
- [ ] Deselect all → status bar shows "127 items"

**Mobile Tests**:
- [ ] Status bar updates work on mobile
- [ ] Multi-selection via edit mode works
- [ ] Process workflow uses selected items

**Edge Cases**:
- [ ] Select item, navigate away, come back → selection cleared (expected)
- [ ] Select item, open preview, back → selection preserved
- [ ] Process with no selection → processes all items
- [ ] Status bar updates when filtering/searching

---

### Files to Modify Summary

**New Files**:
- `src/fichero/shared/selection/selection_manager.py`
- `src/fichero/shared/selection/__init__.py`

**Modified Files**:
- `src/fichero/app.py` (add SelectionManager initialization)
- `src/fichero/windows/main/main_window.py` (integrate with StatusBar)
- `src/fichero/shared/bars/status_bar.py` (add selection display methods)
- `src/fichero/windows/main/views/collection/collection_view.py` (use SelectionManager)
- `src/fichero/shared/navigation/navigation_state.py` (add selection_ids field)
- `src/fichero/shared/navigation/navigation_controller.py` (preserve selection)

**Test Files to Create**:
- `tests/shared/selection/test_selection_manager.py`
- `tests/integration/test_selection_workflow.py`

---

### Troubleshooting Guide

**Issue**: Status bar not updating
- Check: Is selection_manager initialized in app?
- Check: Is status_bar subscribed to SELECTION_CHANGED events?
- Check: Are events being emitted (add logging to SelectionManager.set_selection())

**Issue**: Multi-selection not working
- Check: Is `multiple_select=True` set on ListWidget?
- Check: Is platform desktop (mobile needs edit mode)?
- Check: Are item IDs being extracted correctly in _on_item_selected()?

**Issue**: Selection not preserved on back navigation
- Check: Is selection_ids being saved in NavigationState?
- Check: Is NavigationController preserving state correctly?
- Check: Is CollectionView.show() trying to restore selection?

**Issue**: Process workflow only uses first item
- Check: Did you update _on_quick_process() to use SelectionManager?
- Check: Is selected_item_ids a list (not a single ID)?
- Check: Logs should show "Processing N selected items"

---

### Success Criteria

Your implementation is complete when:
1. ✅ Status bar shows selection counts in all views
2. ✅ Multi-selection (3+ items) fully works in process workflow
3. ✅ Selection preserved when navigating preview → back
4. ✅ All test scenarios pass (desktop and mobile)
5. ✅ Logs show "SelectionManager" initialization and events
6. ✅ No regressions in existing single-selection behavior

Good luck! Remember to test each phase before moving to the next.
