# Phase 3 Implementation Plan: Connect Views to SelectionManager

**Date**: 2025-11-15
**Status**: READY FOR IMPLEMENTATION
**Prerequisites**: Phase 1 (SelectionManager) and Phase 2 (StatusBar) must be complete and tested

---

## Executive Summary

This plan details how to connect the three main views (LibraryView, CollectionView, StepBrowser) to the SelectionManager created in Phase 1. This is the critical integration phase that makes the entire selection tracking system functional.

**Complexity**: MEDIUM - Requires careful modification of existing callbacks without breaking inspector/preview integration
**Risk Level**: MEDIUM - Existing functionality (inspector, preview, workflows) must continue to work
**Estimated Effort**: 2-3 hours of implementation + 1 hour testing

**Key Principle**: We're ADDING SelectionManager calls to existing callbacks, not replacing them. All existing functionality must continue to work.

---

## 1. Architecture Analysis

### 1.1 How Selection Currently Works

**LibraryView** (`library_view.py`):
- **Selection Handler**: `_on_collection_selected(widget)` (line 567)
- **Selection Storage**: `self.selected_collection` (line 586)
- **Selection Source**: `widget.selection.collection_data` (line 579)
- **Current Behavior**:
  - Stores selected collection in instance variable
  - Updates inspector directly (line 594)
  - Triggers navigation callback (line 607)
  - Enables/disables inspector button (lines 601, 618)

**CollectionView** (`collection_view.py`):
- **Selection Handler**: `_on_item_selected(widget_or_item)` (line 1678)
- **Selection Storage**: None - selection stored in widget state only
- **Selection Source**: Complex - handles multiple widget types (DetailedList, Tree, ListWidget)
- **Multi-selection**: ENABLED (line 1684 detects lists) but only uses first item (line 1689)
- **Current Behavior**:
  - Extracts item data from widget/selection
  - Updates inspector asynchronously (line 1194 in review doc example)
  - Loads preview/output view
  - Enables/disables inspector button

**StepBrowser** (`step_browser.py`):
- **Selection Handler**: `_on_step_selected(widget, **kwargs)` (line 171)
- **Selection Storage**: `self.current_index` (line 187)
- **Selection Source**: `kwargs.get('selected_data')` (line 175)
- **Current Behavior**:
  - Stores current step index
  - Triggers callback to parent (PreviewView) (line 191)

### 1.2 ListWidget Selection Callback API

**From `base.py` line 439-542**:

```python
def _handle_select(self, widget_or_item) -> None:
    """
    Unified selection handler.

    For native renderers: widget_or_item is a Toga widget, get selection from widget.selection
    For custom renderers: widget_or_item is the item data directly
    """
```

**Key Points**:
- `widget_or_item` can be:
  1. A Toga widget (Table/Tree/DetailedList) - access `widget.selection`
  2. Direct item data (dict) from custom renderer
  3. A list (if `multiple_select=True`)
- `widget.selection` returns:
  - Single Row/Node object (single selection)
  - List of Row/Node objects (multi-selection)
  - None (no selection)

**From `base.py` line 621-630**:

```python
def get_selection(self) -> Any:
    """Get currently selected item(s) - returns Row object or list of Rows"""
    if isinstance(self.widget, (toga.Table, toga.Tree, toga.DetailedList)):
        return self.widget.selection
    return None
```

### 1.3 Current Selection State Storage

| View | Attribute | Type | Usage |
|------|-----------|------|-------|
| LibraryView | `self.selected_collection` | Dict | Inspector update, navigation |
| CollectionView | None | N/A | Selection stored in widget only |
| StepBrowser | `self.current_index` | int | Parent callback |

**Analysis**:
- LibraryView has local state that should be preserved temporarily
- CollectionView has NO local state - we need to add it for backwards compatibility
- StepBrowser has minimal state - safe to keep

---

## 2. Integration Strategy

### 2.1 Design Principles

1. **Additive, Not Destructive**: Add SelectionManager calls to existing code, don't replace it
2. **Backwards Compatible**: Keep existing `selected_*` attributes for now
3. **Defensive Programming**: Handle None, missing app, missing selection_manager
4. **Multi-Selection First**: Design for multi-selection, even if only one item selected
5. **Metadata Rich**: Include all relevant metadata for status bar/inspector

### 2.2 Integration Points

**For Each View**:
1. Add SelectionManager call to existing selection handler
2. Extract item IDs from selection (handle single/multi)
3. Build metadata list (one dict per selected item)
4. Call `app.selection_manager.set_selection(context, item_ids, metadata)`
5. Keep existing behavior (inspector update, navigation, etc.)

### 2.3 Access to SelectionManager

**How views access SelectionManager**:

All views have access to `self.app` which contains `app.selection_manager`.

**Defensive check pattern**:
```python
if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
    self.app.selection_manager.set_selection(...)
else:
    logger.warning("SelectionManager not available in app")
```

### 2.4 Handling Selection Clearing

**When selection is cleared** (user clicks empty space, deselects all):
- `widget_or_item` will be None or empty list
- Must call `set_selection(context, [])` to clear selection
- Status bar will update to show total count instead of selection count

---

## 3. Detailed Implementation Steps

### STEP 1: LibraryView Integration

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/library/library_view.py`

**Location**: `_on_collection_selected()` method, line 567

**Current Code** (lines 567-623):
```python
def _on_collection_selected(self, widget):
    """Handle collection selection from detailed list"""
    logger.info(f"🎯 _on_collection_selected CALLED!")

    # Trigger focus ring when collection is selected
    if self.on_click:
        self.on_click()

    try:
        if widget.selection and hasattr(widget.selection, 'collection_data'):
            collection = widget.selection.collection_data
            collection_id = collection.get('id', '')
            collection_name = collection.get('name', '')

            # Store selected collection
            self.selected_collection = collection

            # Update inspector
            if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                self.app.inspector_window.update_metadata(collection, selection_type="COLLECTION")

            # Enable inspector button
            if hasattr(self, 'commands') and 'show_inspector' in self.commands:
                self.commands['show_inspector'].enable()

            # Navigate to collection
            if self.on_collection_selected:
                self.on_collection_selected(collection_id, collection_name)
        else:
            # No selection - clear
            # ... clearing logic ...
```

**Modified Code** (ADD after line 586, before inspector update):

```python
def _on_collection_selected(self, widget):
    """Handle collection selection from detailed list"""
    logger.info(f"🎯 _on_collection_selected CALLED!")

    # Trigger focus ring when collection is selected
    if self.on_click:
        self.on_click()

    try:
        if widget.selection and hasattr(widget.selection, 'collection_data'):
            collection = widget.selection.collection_data
            collection_id = collection.get('id', '')
            collection_name = collection.get('name', '')

            # Store selected collection (keep for backwards compatibility)
            self.selected_collection = collection

            # PHASE 3: Update SelectionManager with collection selection
            if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
                # Build metadata for status bar display
                item_count = collection.get('item_count', 0)
                metadata = [{
                    'collection_id': collection_id,
                    'collection_name': collection_name,
                    'item_count': item_count,
                    'type': collection.get('type', 'external'),
                    'source': collection.get('source', ''),
                }]

                # Set selection in manager (single collection)
                self.app.selection_manager.set_selection(
                    view_id='library',
                    item_ids=[collection_id],
                    metadata=metadata
                )
                logger.debug(f"✅ SelectionManager updated: library → {collection_name}")
            else:
                logger.warning("⚠️ SelectionManager not available - selection not tracked")

            # Update inspector (existing behavior)
            if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                self.app.inspector_window.update_metadata(collection, selection_type="COLLECTION")

            # ... rest of existing code ...
        else:
            # No selection - clear
            # PHASE 3: Clear SelectionManager selection
            if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
                self.app.selection_manager.clear_selection('library')
                logger.debug("✅ SelectionManager cleared: library")

            # ... existing clearing logic ...
```

**What Changes**:
- Adds SelectionManager call after storing `self.selected_collection`
- Builds metadata dict with collection info for status bar
- Clears SelectionManager when selection is cleared
- Keeps ALL existing behavior (inspector, navigation, buttons)

**Testing**:
```python
# Expected behavior:
# 1. Select collection → SelectionManager has ['collection-id-123']
# 2. Status bar shows "1 collection" (via Phase 2 event handler)
# 3. Inspector still updates (existing code still runs)
# 4. Navigation still works (existing callback still fires)
```

---

### STEP 2: CollectionView Integration

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/collection/collection_view.py`

**Location**: `_on_item_selected()` method, line 1678

**Challenge**: This method is complex (160+ lines) and handles multiple widget types. We need to extract item IDs/metadata for ALL selected items, not just the first.

**Current Code** (simplified, lines 1678-1750):
```python
def _on_item_selected(self, widget_or_item):
    """Handle item selection from list"""
    try:
        # Check if this is a list of selections (multiple selection enabled)
        if isinstance(widget_or_item, list):
            logger.info(f"📋 Multiple selection: {len(widget_or_item)} items")
            # For now, handle the first item in the list
            # TODO: Support displaying multiple items in output view
            if widget_or_item:
                widget_or_item = widget_or_item[0]  # ❌ ONLY USES FIRST!

        # Extract item data from widget/selection
        if widget_or_item is None:
            selected_data = None
        elif hasattr(widget_or_item, 'selection'):
            # Extract from widget.selection (Row/Node object)
            selected_row = widget_or_item.selection
            collection_data = getattr(selected_row, '_collection_data', None)
            if collection_data:
                selected_data = { 'id': collection_data.get('id'), ... }
            else:
                selected_data = { 'id': getattr(selected_row, 'id'), ... }
        else:
            # Direct item data (dict or Node)
            selected_data = extract_from_dict_or_node(widget_or_item)

        # ... (120 more lines updating inspector, preview, etc.)
```

**Modified Code** (REPLACE lines 1678-1750):

```python
def _on_item_selected(self, widget_or_item):
    """Handle item selection from list (supports single and multi-selection)"""
    try:
        logger.info(f"🎯 _on_item_selected called with: {type(widget_or_item)}")

        # ========== PHASE 3: Extract ALL selected items (not just first) ==========

        # Normalize to list of items
        selected_items = []
        if isinstance(widget_or_item, list):
            # Multi-selection: list of Row/Node objects
            selected_items = widget_or_item
            logger.info(f"📋 Multiple selection: {len(selected_items)} items")
        elif widget_or_item is not None:
            # Single selection: one Row/Node object
            selected_items = [widget_or_item]
            logger.info(f"📋 Single selection: 1 item")
        else:
            # No selection (cleared)
            selected_items = []
            logger.info(f"📋 Selection cleared")

        # Extract item IDs and metadata from all selected items
        selected_item_ids = []
        selected_metadata = []

        for item in selected_items:
            # Extract item data from widget/selection/dict
            item_data = self._extract_item_data(item)

            if item_data and item_data.get('id'):
                selected_item_ids.append(item_data['id'])
                selected_metadata.append({
                    'item_id': item_data['id'],
                    'item_name': item_data.get('name', item_data.get('title', 'Unknown')),
                    'is_folder': item_data.get('is_folder', False),
                    'type': item_data.get('type', 'unknown'),
                    'file_path': item_data.get('file_path', ''),
                    'path': item_data.get('path', ''),
                })

        logger.info(f"📌 Extracted {len(selected_item_ids)} item IDs from selection")

        # PHASE 3: Update SelectionManager with ALL selected items
        if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
            self.app.selection_manager.set_selection(
                view_id='collection',
                item_ids=selected_item_ids,
                metadata=selected_metadata
            )
            logger.debug(f"✅ SelectionManager updated: collection → {len(selected_item_ids)} items")
        else:
            logger.warning("⚠️ SelectionManager not available - selection not tracked")

        # ========== Keep existing behavior (inspector, preview, buttons) ==========

        # Update inspector with FIRST selected item (existing behavior)
        # (Inspector can only show one item at a time currently)
        if selected_item_ids:
            first_item_data = self._extract_item_data(selected_items[0])

            # Enable inspector button
            if hasattr(self, 'commands') and 'show_inspector' in self.commands:
                self.commands['show_inspector'].enable()

            # Update inspector asynchronously (existing code)
            if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                import asyncio
                asyncio.create_task(self._update_inspector_async(first_item_data))

            # Load preview for first item if not a folder (existing code)
            if not first_item_data.get('is_folder', False):
                file_path = first_item_data.get('file_path')
                if file_path:
                    import asyncio
                    asyncio.create_task(self._load_item_outputs(first_item_data, file_path))
        else:
            # No selection - existing clearing logic
            if hasattr(self, 'commands') and 'show_inspector' in self.commands:
                self.commands['show_inspector'].disable()

            # Update inspector with parent (existing code)
            if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                import asyncio
                asyncio.create_task(self._update_inspector_with_parent_async())

            # ... existing preview clearing logic ...

    except Exception as e:
        logger.error(f"Failed to handle item selection: {e}")
        import traceback
        traceback.print_exc()
```

**New Helper Method** (ADD after `_on_item_selected()`, around line 1850):

```python
def _extract_item_data(self, widget_or_item) -> Optional[Dict[str, Any]]:
    """
    Extract item data from widget selection, Row/Node object, or dict.

    Handles all selection formats:
    - Toga widget (has .selection attribute)
    - Row object (from Table/DetailedList)
    - Node object (from Tree, has ._collection_data)
    - Dict (from custom renderer)

    Args:
        widget_or_item: Widget, Row, Node, or dict

    Returns:
        Dict with keys: id, name, title, type, is_folder, path, file_path
        Returns None if data cannot be extracted
    """
    try:
        # Case 1: Widget with .selection attribute
        if hasattr(widget_or_item, 'selection'):
            if widget_or_item.selection is None:
                return None
            return self._extract_item_data(widget_or_item.selection)

        # Case 2: Node object with ._collection_data attribute (Tree widget)
        collection_data = getattr(widget_or_item, '_collection_data', None)
        if collection_data:
            return {
                'id': collection_data.get('id', ''),
                'title': collection_data.get('title', 'Unknown Item'),
                'name': collection_data.get('name', collection_data.get('title', 'Unknown')),
                'type': collection_data.get('type', 'unknown'),
                'is_folder': collection_data.get('is_folder', False),
                'path': collection_data.get('path', ''),
                'file_path': collection_data.get('file_path', '')
            }

        # Case 3: Dict (from custom renderer or already extracted)
        if isinstance(widget_or_item, dict):
            return {
                'id': widget_or_item.get('id', widget_or_item.get('_item_id', '')),
                'title': widget_or_item.get('title', 'Unknown Item'),
                'name': widget_or_item.get('name', widget_or_item.get('title', 'Unknown')),
                'type': widget_or_item.get('type', 'unknown'),
                'is_folder': widget_or_item.get('is_folder', False),
                'path': widget_or_item.get('path', ''),
                'file_path': widget_or_item.get('file_path', '')
            }

        # Case 4: Row object (from Table/DetailedList) - extract attributes
        return {
            'id': getattr(widget_or_item, 'id', ''),
            'title': getattr(widget_or_item, 'title', 'Unknown Item'),
            'name': getattr(widget_or_item, 'name', getattr(widget_or_item, 'title', 'Unknown')),
            'type': getattr(widget_or_item, 'type', 'unknown'),
            'is_folder': getattr(widget_or_item, 'is_folder', False),
            'path': getattr(widget_or_item, 'path', ''),
            'file_path': getattr(widget_or_item, 'file_path', '')
        }

    except Exception as e:
        logger.error(f"Failed to extract item data: {e}")
        return None
```

**What Changes**:
- Handles multi-selection properly (processes ALL items, not just first)
- Extracts item IDs and metadata for all selected items
- Adds SelectionManager call with full metadata list
- Keeps existing inspector/preview behavior (still uses first item)
- Adds helper method to normalize item data extraction

**Testing**:
```python
# Expected behavior:
# 1. Select 1 item → SelectionManager has ['item-123']
# 2. Select 3 items (Cmd+Click) → SelectionManager has ['item-123', 'item-456', 'item-789']
# 3. Status bar shows "3 items selected" (via Phase 2)
# 4. Inspector still shows first item (existing behavior)
# 5. Preview still shows first item (existing behavior)
```

---

### STEP 3: StepBrowser Integration

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/output/step_browser.py`

**Location**: `_on_step_selected()` method, line 171

**Current Code** (lines 171-196):
```python
def _on_step_selected(self, widget, **kwargs):
    """Handle step selection"""
    try:
        # ListWidget passes the selected item data in kwargs
        selected_data = kwargs.get('selected_data')
        if not selected_data:
            self.logger.warning("StepBrowser: No selected_data in callback")
            return

        # Get the index from _item_id
        index = selected_data.get('_item_id')
        if index is None:
            self.logger.warning("StepBrowser: No _item_id in selected_data")
            return

        self.logger.info(f"StepBrowser: Step selected at index {index}")
        self.current_index = index

        # Notify callback
        if self.on_step_selected:
            self.on_step_selected(index)

    except Exception as e:
        self.logger.error(f"Error handling step selection: {e}")
```

**Modified Code** (REPLACE lines 171-196):

```python
def _on_step_selected(self, widget, **kwargs):
    """Handle step selection"""
    try:
        # ListWidget passes the selected item data in kwargs
        selected_data = kwargs.get('selected_data')
        if not selected_data:
            self.logger.warning("StepBrowser: No selected_data in callback")

            # PHASE 3: Clear selection when no data
            if hasattr(self, 'app') and hasattr(self.app, 'selection_manager'):
                if self.app.selection_manager:
                    self.app.selection_manager.clear_selection('steps')
                    self.logger.debug("✅ SelectionManager cleared: steps")
            return

        # Get the index from _item_id
        index = selected_data.get('_item_id')
        if index is None:
            self.logger.warning("StepBrowser: No _item_id in selected_data")
            return

        self.logger.info(f"StepBrowser: Step selected at index {index}")

        # Store current index (keep for backwards compatibility)
        self.current_index = index

        # PHASE 3: Update SelectionManager with step selection
        if hasattr(self, 'app') and hasattr(self.app, 'selection_manager'):
            if self.app.selection_manager:
                # Build metadata for status bar
                step_name = selected_data.get('step', 'Unknown Step')
                step_status = selected_data.get('status', 'unknown')
                tool_name = selected_data.get('tool', '')

                metadata = [{
                    'step_id': f"step_{index}",
                    'step_index': index,
                    'step_name': step_name,
                    'status': step_status,
                    'tool': tool_name,
                }]

                # Set selection (use step ID as string)
                self.app.selection_manager.set_selection(
                    view_id='steps',
                    item_ids=[f"step_{index}"],
                    metadata=metadata
                )
                self.logger.debug(f"✅ SelectionManager updated: steps → {step_name}")
        else:
            self.logger.warning("⚠️ SelectionManager not available - step selection not tracked")

        # Notify callback (existing behavior)
        if self.on_step_selected:
            self.on_step_selected(index)

    except Exception as e:
        self.logger.error(f"Error handling step selection: {e}")
        import traceback
        self.logger.error(traceback.format_exc())
```

**What Changes**:
- Adds SelectionManager call after storing `self.current_index`
- Builds metadata dict with step info
- Uses string ID format `"step_{index}"` for consistency
- Clears SelectionManager when selection is cleared
- Keeps ALL existing behavior (index storage, parent callback)

**Testing**:
```python
# Expected behavior:
# 1. Select step 2 → SelectionManager has ['step_2']
# 2. Status bar shows "1 step selected" (via Phase 2)
# 3. Parent callback still fires (existing behavior)
# 4. Preview still updates (existing behavior)
```

---

### STEP 4: Multi-Selection Support

**Goal**: Ensure all views handle multi-selection correctly.

**LibraryView**:
- ✅ Already single-selection only (collections list doesn't support multi-select)
- No changes needed beyond Step 1

**CollectionView**:
- ✅ Already handles multi-selection in Step 2 above
- `_extract_item_data()` helper processes all items
- SelectionManager receives ALL selected item IDs

**StepBrowser**:
- ✅ Single-selection only (steps are sequential)
- No changes needed beyond Step 3

**ListWidget**:
- ✅ Already supports multi-selection via `multiple_select=True` parameter
- No changes needed to widget itself

---

## 4. Metadata Structure Design

### 4.1 LIBRARY Context Metadata

**Context**: User selects a collection in library view

**Metadata Structure**:
```python
{
    'collection_id': 'abc-123-def-456',         # UUID of collection
    'collection_name': 'My Documents',          # Display name
    'item_count': 127,                          # Number of items in collection
    'type': 'external',                         # Type: 'external' or 'internal'
    'source': '/path/to/source',                # Source path (external) or None
}
```

**Usage**:
- Status bar: "My Documents (127 items)" when hovered
- Inspector: Shows collection metadata
- Workflows: Can process entire collection

**Source**: `widget.selection.collection_data` dict from LibraryView

---

### 4.2 COLLECTION Context Metadata

**Context**: User selects one or more items in collection view

**Metadata Structure** (single item):
```python
{
    'item_id': 'xyz-789-abc-012',               # UUID of item
    'item_name': 'Document_001.jpg',            # Display name/filename
    'is_folder': False,                         # True if folder, False if file
    'type': 'image',                            # File type: image, pdf, folder, etc.
    'file_path': '/path/to/file.jpg',           # Full filesystem path
    'path': 'subfolder/file.jpg',               # Relative path in collection
}
```

**Metadata Structure** (multi-selection):
```python
[
    {
        'item_id': 'item-1',
        'item_name': 'Document_001.jpg',
        'is_folder': False,
        'type': 'image',
        'file_path': '/path/to/001.jpg',
        'path': '001.jpg',
    },
    {
        'item_id': 'item-2',
        'item_name': 'Document_002.jpg',
        'is_folder': False,
        'type': 'image',
        'file_path': '/path/to/002.jpg',
        'path': '002.jpg',
    },
    # ... more items
]
```

**Usage**:
- Status bar: "3 items selected" (count)
- Inspector: Shows first item metadata
- Workflows: Process all selected items
- Phase 2 status bar: Can show "3 items, 1 folder" by analyzing metadata

**Source**: Extracted from Row/Node objects via `_extract_item_data()` helper

---

### 4.3 STEPS Context Metadata

**Context**: User selects a processing step in step browser

**Metadata Structure**:
```python
{
    'step_id': 'step_2',                        # String ID: "step_{index}"
    'step_index': 2,                            # Numeric index (0-based)
    'step_name': 'Enhance Images',              # Display name
    'status': 'completed',                      # Status: pending, running, completed, failed
    'tool': 'enhance',                          # Tool name that ran this step
}
```

**Usage**:
- Status bar: "Step 2: Enhance Images (completed)"
- Inspector: Shows step metadata, outputs
- Adjust view: Shows controls for this step's tool

**Source**: `kwargs.get('selected_data')` from ListWidget callback

---

## 5. Backwards Compatibility

### 5.1 Preserve Existing Attributes

**Keep these attributes temporarily** (for views that currently use them):

| View | Attribute | Reason to Keep |
|------|-----------|----------------|
| LibraryView | `self.selected_collection` | Used by other methods, navigation |
| StepBrowser | `self.current_index` | Used by parent PreviewView |

**DO NOT ADD** new selection attributes to CollectionView - it never had them.

### 5.2 Dual Update Pattern

**During Phase 3**, update BOTH old and new systems:

```python
# LibraryView example:
self.selected_collection = collection  # OLD (keep for now)
self.app.selection_manager.set_selection(...)  # NEW (add)

# StepBrowser example:
self.current_index = index  # OLD (keep for now)
self.app.selection_manager.set_selection(...)  # NEW (add)
```

**Future deprecation** (Phase 4 or later):
1. Search codebase for references to `self.selected_collection`
2. Replace with `self.app.selection_manager.get_selection('library')`
3. Remove `self.selected_collection` attribute
4. Repeat for `self.current_index`

### 5.3 Migration Timeline

- **Phase 3**: Add SelectionManager calls, keep old attributes
- **Phase 4**: Review all usages of old attributes
- **Phase 5**: Migrate usages to SelectionManager API
- **Phase 6**: Remove old attributes, clean up code

---

## 6. ListWidget Integration

### 6.1 How `on_select` Works

**From `base.py` line 439**:

```python
def _handle_select(self, widget_or_item) -> None:
    """
    Unified selection handler.

    For native renderers: widget_or_item is a Toga widget
    For custom renderers: widget_or_item is the item data
    """
    # Extract selection
    if hasattr(widget_or_item, 'selection'):
        selection = widget_or_item.selection  # Native: Row/Node or list
    else:
        selection = widget_or_item  # Custom: dict or object

    # Call user callback
    if self._on_select_callback:
        self._on_select_callback(selection)
```

**What callback receives**:

| Widget Type | Single Selection | Multi Selection |
|-------------|------------------|-----------------|
| Table | Row object | List[Row] |
| DetailedList | Row object | List[Row] |
| Tree | Node object | List[Node] |
| Custom (Card/HTML) | Dict | List[Dict] |

### 6.2 Extracting Selected Item Data

**Challenge**: Different widget types have different selection formats.

**Solution**: `_extract_item_data()` helper (implemented in Step 2) normalizes all formats:

```python
def _extract_item_data(self, widget_or_item) -> Optional[Dict[str, Any]]:
    """Extract item data from any selection format"""
    # Handles: Widget, Row, Node, Dict
    # Returns: Normalized dict with keys: id, name, type, is_folder, path, file_path
```

**Usage in views**:
```python
# Single item
item_data = self._extract_item_data(widget_or_item)

# Multi-selection
for item in selected_items:
    item_data = self._extract_item_data(item)
```

### 6.3 Modifications to ListWidget Base Class

**Required Changes**: NONE

ListWidget already:
- ✅ Supports `multiple_select=True` parameter
- ✅ Passes selection to callback correctly
- ✅ Has `get_selection()` method for querying

**No modifications needed** to ListWidget itself. All changes are in view callbacks.

---

## 7. Testing Strategy

### 7.1 Manual Test Scenarios

**LibraryView**:
1. ✅ Select collection → `app.selection_manager.get_selection('library')` returns `['collection-id']`
2. ✅ Status bar shows "1 collection"
3. ✅ Inspector still updates with collection metadata
4. ✅ Navigation to collection still works
5. ✅ Deselect (click empty space) → `get_selection('library')` returns `[]`
6. ✅ Status bar shows "5 collections" (total count)

**CollectionView (Single Selection)**:
1. ✅ Select 1 item → `app.selection_manager.get_selection('collection')` returns `['item-id']`
2. ✅ Status bar shows "1 item selected"
3. ✅ Inspector still updates with item metadata
4. ✅ Preview still loads for item
5. ✅ Deselect → `get_selection('collection')` returns `[]`
6. ✅ Status bar shows "127 items"

**CollectionView (Multi-Selection)**:
1. ✅ Select 3 items (Cmd+Click) → `get_selection('collection')` returns `['id1', 'id2', 'id3']`
2. ✅ Status bar shows "3 items selected"
3. ✅ Inspector still shows FIRST item (existing behavior)
4. ✅ Preview still shows FIRST item (existing behavior)
5. ✅ Metadata list has 3 dicts, one per item
6. ✅ Deselect all → `get_selection('collection')` returns `[]`

**StepBrowser**:
1. ✅ Select step 2 → `get_selection('steps')` returns `['step_2']`
2. ✅ Status bar shows "Step 2: Enhance Images" (Phase 2 feature)
3. ✅ Parent callback still fires (existing behavior)
4. ✅ `self.current_index` still updated (backwards compatibility)
5. ✅ Preview updates (existing behavior)

### 7.2 Multi-Selection Edge Cases

**Test Scenarios**:
1. ✅ Select all items in collection (Cmd+A) → All IDs in SelectionManager
2. ✅ Select 1 folder + 2 files → Metadata correctly marks folder with `is_folder: True`
3. ✅ Rapidly click different items → SelectionManager updates each time
4. ✅ Select item, navigate away, come back → Selection cleared (expected)
5. ✅ Select 3 items, deselect 1 (Cmd+Click) → SelectionManager has 2 items

### 7.3 Regression Tests

**Must Verify These Still Work**:

1. ✅ **Inspector Updates**:
   - Select collection → inspector shows collection metadata
   - Select item → inspector shows item metadata
   - Select multiple items → inspector shows FIRST item (not broken)

2. ✅ **Preview/Output Loading**:
   - Select item → preview loads item outputs
   - Select folder → preview clears (folders have no preview)
   - Select multiple items → preview shows FIRST item

3. ✅ **Navigation**:
   - Select collection → navigates to collection view
   - Double-click folder → navigates into folder
   - Back button → returns to previous view

4. ✅ **Toolbar Buttons**:
   - Select item → "Show Inspector" enabled
   - Deselect → "Show Inspector" disabled
   - Select collection → "Show Inspector" enabled

5. ✅ **Process Workflows** (deferred to future phase):
   - This phase ONLY adds SelectionManager calls
   - Workflows will be updated in a future phase to USE multi-selection
   - For now, they can continue using first item only

### 7.4 Event Emission Tests

**Verify SELECTION_CHANGED events are emitted**:

```python
# Test in Python console:
from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation

# Create a test listener
def test_listener(event):
    print(f"SELECTION_CHANGED: view={event.data['view_id']}, count={event.data['count']}")

subscribe_to_navigation("SELECTION_CHANGED", test_listener)

# Now interact with UI:
# Select collection → Should print: "SELECTION_CHANGED: view=library, count=1"
# Select 3 items → Should print: "SELECTION_CHANGED: view=collection, count=3"
# Deselect → Should print: "SELECTION_CHANGED: view=collection, count=0"
```

---

## 8. Success Criteria

### 8.1 Functional Requirements

- ✅ LibraryView selection updates SelectionManager with collection ID
- ✅ CollectionView selection updates SelectionManager with item ID(s)
- ✅ StepBrowser selection updates SelectionManager with step ID
- ✅ Multi-selection in CollectionView captures ALL selected items
- ✅ Deselection (clearing) updates SelectionManager with empty list
- ✅ Metadata is populated for all contexts (library, collection, steps)
- ✅ Status bar updates via Phase 2 event handler (existing code)

### 8.2 Backwards Compatibility

- ✅ Inspector still updates correctly in all views
- ✅ Preview/output still loads correctly
- ✅ Navigation still works (select collection, navigate to folder, back button)
- ✅ Toolbar buttons still enable/disable based on selection
- ✅ Existing attributes (`self.selected_collection`, `self.current_index`) still updated
- ✅ NO REGRESSIONS in existing functionality

### 8.3 Code Quality

- ✅ All SelectionManager calls wrapped in defensive checks (`hasattr`, `if app.selection_manager`)
- ✅ Logging added for debug visibility ("SelectionManager updated", "SelectionManager cleared")
- ✅ Error handling preserves existing behavior (try/except doesn't break inspector/preview)
- ✅ No breaking changes to method signatures
- ✅ Code is readable and maintainable

### 8.4 Performance

- ✅ No noticeable lag when selecting items
- ✅ Multi-selection of 100+ items completes in < 100ms
- ✅ SelectionManager updates don't block UI

---

## 9. Notes for Review Agent

### 9.1 Key Design Decisions

**Decision 1: Keep Existing Attributes**
- **Rationale**: Safer to keep `self.selected_collection` and `self.current_index` during Phase 3
- **Risk**: If we remove them now, we might break unknown code paths
- **Mitigation**: Search codebase in Phase 4 before removing

**Decision 2: Inspector Shows First Item Only**
- **Rationale**: Inspector UI can only show one item at a time currently
- **Risk**: User selects 3 items but inspector shows only first - might be confusing
- **Mitigation**: Future enhancement - inspector could show multi-selection summary
- **Acceptable for Phase 3**: Keep existing behavior, don't break inspector

**Decision 3: Extract Helper Method in CollectionView**
- **Rationale**: Item data extraction is complex (4 different formats), needs to be reusable
- **Risk**: Helper method might not cover all edge cases
- **Mitigation**: Defensive programming - return None if extraction fails
- **Benefit**: Makes `_on_item_selected()` much more readable

**Decision 4: Use String IDs for Steps**
- **Rationale**: SelectionManager uses `List[str]` for item_ids, but steps use int indices
- **Solution**: Convert to string: `f"step_{index}"`
- **Risk**: Might need to convert back to int in some places
- **Mitigation**: Metadata includes both `step_id` (string) and `step_index` (int)

### 9.2 Potential Risks

**Risk 1: Race Conditions**
- **Scenario**: Selection changes while inspector is updating asynchronously
- **Impact**: Inspector might show stale data
- **Likelihood**: LOW (Toga is single-threaded, async tasks are serialized)
- **Mitigation**: Already handled by existing `asyncio.create_task()` pattern

**Risk 2: Breaking Inspector Updates**
- **Scenario**: SelectionManager call throws exception, existing code doesn't run
- **Impact**: Inspector doesn't update, user sees stale metadata
- **Likelihood**: LOW (defensive checks prevent exceptions)
- **Mitigation**: Wrap SelectionManager calls in try/except, don't let them break existing flow

**Risk 3: Missing Metadata Fields**
- **Scenario**: Status bar expects `is_folder` but metadata doesn't include it
- **Impact**: Status bar can't show "3 items, 1 folder"
- **Likelihood**: MEDIUM (extraction might fail for some widget types)
- **Mitigation**: `_extract_item_data()` always returns dict with all keys (default to empty string/False)

**Risk 4: Mobile Differences**
- **Scenario**: Multi-selection behaves differently on iOS (no Cmd+Click)
- **Impact**: Multi-selection harder to use on mobile
- **Likelihood**: HIGH (iOS DetailedList doesn't have native multi-select UI)
- **Mitigation**: Document in Phase 3 testing notes - mobile needs edit mode for multi-select

### 9.3 Questions for Implementation Agent

1. **SelectionManager Access**: Should we cache `self.app.selection_manager` in view `__init__` or check `hasattr` every time?
   - **Recommendation**: Check every time (more defensive)

2. **Empty Metadata**: If metadata extraction fails, should we call `set_selection()` with empty metadata or skip the call?
   - **Recommendation**: Call with empty metadata (status bar can still show count)

3. **Logging Level**: Should SelectionManager updates be `logger.debug()` or `logger.info()`?
   - **Recommendation**: `logger.debug()` (too verbose for info level)

4. **Multi-Selection Indicator**: Should inspector/preview show a hint that multiple items are selected?
   - **Recommendation**: Deferred to future phase (Phase 4+)

### 9.4 Test Coverage Gaps

**Not Tested in Phase 3**:
1. Process workflows using multi-selection → DEFERRED to Phase 4
2. Mobile multi-selection via edit mode → DEFERRED to mobile testing
3. Selection persistence across navigation → DEFERRED to Phase 4
4. Keyboard shortcuts (Cmd+A, Shift+Click) → DEFERRED to integration testing

**Acceptable Gaps**:
- Phase 3 focuses ONLY on connecting views to SelectionManager
- Workflow integration is a separate phase
- Selection persistence is a separate feature

---

## 10. Implementation Checklist

### Pre-Implementation
- [ ] Read Phase 1 test report - verify SelectionManager is ready
- [ ] Read Phase 2 test report - verify StatusBar integration is ready
- [ ] Review this plan completely
- [ ] Understand existing selection handlers in all three views

### LibraryView (Step 1)
- [ ] Locate `_on_collection_selected()` at line 567
- [ ] Add SelectionManager call after line 586 (after `self.selected_collection = ...`)
- [ ] Build metadata dict with collection info
- [ ] Add SelectionManager clear call in else branch
- [ ] Test: Select collection → verify SelectionManager updated
- [ ] Test: Inspector still updates
- [ ] Test: Navigation still works

### CollectionView (Step 2)
- [ ] Locate `_on_item_selected()` at line 1678
- [ ] Add `_extract_item_data()` helper method after `_on_item_selected()`
- [ ] Replace lines 1684-1690 (multi-selection handling) with new code
- [ ] Extract ALL items (not just first) into `selected_items` list
- [ ] Loop through items, call `_extract_item_data()` for each
- [ ] Build `selected_item_ids` and `selected_metadata` lists
- [ ] Add SelectionManager call
- [ ] Keep existing inspector/preview logic (use first item)
- [ ] Test: Select 1 item → verify SelectionManager has 1 ID
- [ ] Test: Select 3 items → verify SelectionManager has 3 IDs
- [ ] Test: Inspector still shows first item
- [ ] Test: Preview still loads first item

### StepBrowser (Step 3)
- [ ] Locate `_on_step_selected()` at line 171
- [ ] Add SelectionManager call after line 187 (after `self.current_index = index`)
- [ ] Build metadata dict with step info
- [ ] Add SelectionManager clear call when `selected_data` is None
- [ ] Test: Select step → verify SelectionManager updated
- [ ] Test: Parent callback still fires
- [ ] Test: `self.current_index` still updated

### Integration Testing
- [ ] Run app in desktop mode
- [ ] Test all scenarios from Section 7.1
- [ ] Verify no regressions (Section 7.3)
- [ ] Test event emission (Section 7.4)
- [ ] Check logs for "SelectionManager updated" messages
- [ ] Verify status bar updates (Phase 2 integration)

### Documentation
- [ ] Update implementation log with actual changes
- [ ] Note any deviations from this plan
- [ ] Document any issues encountered
- [ ] Create test report for Phase 3

---

## 11. File Paths Reference

**Files to Modify**:
1. `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/library/library_view.py`
   - Line 567: `_on_collection_selected()` - add SelectionManager call

2. `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/collection/collection_view.py`
   - Line 1678: `_on_item_selected()` - rewrite multi-selection handling
   - Line ~1850: Add `_extract_item_data()` helper method

3. `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/output/step_browser.py`
   - Line 171: `_on_step_selected()` - add SelectionManager call

**Files to Reference** (read-only):
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/selection/selection_manager.py`
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/widgets/list_widget/base.py`
- `/Users/dtubb/code/fichero_main/fichero/docs/architecture/selection_tracking/PHASE1_TEST_REPORT.md`
- `/Users/dtubb/code/fichero_main/fichero/docs/architecture/selection_tracking/PHASE2_TEST_REPORT.md`

**No New Files**: This phase only modifies existing view files.

---

## 12. Expected Outcomes

After completing Phase 3 implementation:

1. **User Experience**:
   - Status bar shows selection counts in real-time
   - Multi-selection works correctly (all items processed, not just first)
   - Existing functionality (inspector, preview, navigation) unchanged

2. **Code Architecture**:
   - Views are connected to SelectionManager
   - Selection state is centralized (no longer scattered across views)
   - Event-driven architecture (views emit, components react)

3. **Ready for Phase 4**:
   - Process workflows can query SelectionManager to get all selected items
   - Selection preservation can read from SelectionManager
   - Inspector can be enhanced to show multi-selection summary

4. **Metrics**:
   - 3 view files modified
   - 1 helper method added (`_extract_item_data`)
   - ~100 lines of code added total
   - 0 breaking changes
   - 0 regressions

---

**END OF PHASE 3 IMPLEMENTATION PLAN**

**Ready for Implementation**: YES
**Review Status**: Pending review by next agent
**Complexity Rating**: 6/10 (Medium complexity, requires careful integration)
**Risk Rating**: 5/10 (Medium risk, potential for breaking existing functionality)

---

**Document Version**: 1.0
**Created**: 2025-11-15
**Author**: Phase 3 Implementation Planning Agent
**Next Step**: Review by implementation review agent, then implementation by coding agent
