# Phase 1: Selection Integration - Implementation Report

## Overview

This document describes the implementation of Phase 1: Selection Integration for the Fichero Preview system. The goal was to make the preview pane automatically update when items are selected in the collection view.

## Implementation Date

2025-11-15

## Changes Made

### 1. Added SELECTION_CHANGED Subscription for Preview Updates

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

**Location:** Line 446 in `_subscribe_to_events()` method

Added subscription to SELECTION_CHANGED events specifically for preview updates:

```python
# Phase 1: Subscribe to selection changes for preview updates
subscribe_to_navigation(NavigationEvents.SELECTION_CHANGED, self._handle_preview_selection_changed)
logger.debug("Preview pane subscribed to selection events")
```

### 2. Implemented `_handle_preview_selection_changed` Handler

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

**Location:** Lines 1729-1748

This handler processes SELECTION_CHANGED events and determines whether to update the preview:

```python
def _handle_preview_selection_changed(self, event):
    """
    Handle SELECTION_CHANGED events to update preview pane.

    Responds to selections from collection view and library sidebar,
    automatically loading the selected item in the preview/inspector pane.
    """
    try:
        # Extract event data
        view_id = event.data.get('view_id', '')
        item_ids = event.data.get('new_selection', [])  # SelectionManager emits 'new_selection'
        metadata = event.data.get('metadata', [])

        logger.info(f"🔍 Preview selection change from view: {view_id}, items: {len(item_ids)}")

        # Only respond to collection view selections (not library, not preview itself)
        if view_id != 'collection':
            logger.debug(f"Ignoring selection from {view_id} (preview only responds to collection)")
            return

        # If no selection, clear preview
        if not item_ids or not metadata:
            logger.info("Empty selection, clearing preview")
            self._clear_preview()
            return

        # Load first selected item (multi-select shows first item)
        first_item_meta = metadata[0]
        self._load_preview_from_selection(first_item_meta, metadata)

    except Exception as e:
        logger.error(f"Failed to handle preview selection change: {e}", exc_info=True)
```

**Key Features:**
- Only responds to collection view selections (filters by `view_id == 'collection'`)
- Clears preview when no items are selected
- Loads the first item when multiple items are selected
- Comprehensive error handling and logging

### 3. Implemented `_load_preview_from_selection` Helper Method

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

**Location:** Lines 1750-1810

This method loads an item in the preview pane from selection metadata:

```python
def _load_preview_from_selection(self, item_meta: dict, all_metadata: list):
    """
    Load item in preview pane from selection metadata.

    Args:
        item_meta: Metadata for the selected item
        all_metadata: Full list of selected items (for navigation)
    """
    try:
        # Extract file path (prefer local_path for downloaded files)
        file_path = item_meta.get('local_path') or item_meta.get('file_path')
        item_id = item_meta.get('id')

        if not file_path:
            logger.warning(f"No file path in selection metadata: {item_meta}")
            return

        logger.info(f"📄 Loading preview for: {file_path}")

        # Check if item has processing outputs via library_manager
        output_data = None
        if hasattr(self.app, 'library_manager') and item_id:
            try:
                # Get processing outputs for this item
                library_manager = self.app.library_manager
                item = library_manager.storage.get_item(item_id)

                if item and item.metadata.get('output_path'):
                    output_path = item.metadata['output_path']
                    logger.info(f"📊 Item has processing outputs: {output_path}")

                    # Create output_data structure expected by _on_show_preview
                    output_data = {
                        'has_outputs': True,
                        'output_path': output_path,
                        # OutputsManager will discover steps when preview loads
                    }
            except Exception as e:
                logger.debug(f"Could not check for outputs: {e}")

        # Trigger existing preview loading mechanism via SHOW_PREVIEW event
        from fichero.shared.navigation.navigation_event_bus import emit_navigation_event, NavigationEvent, NavigationEvents

        preview_event_data = {
            'file_path': file_path,
            'item_id': item_id,
            'output_data': output_data,
            'file_metadata': item_meta,
            'collection_items': all_metadata,  # For prev/next navigation
            'item_index': 0,  # First selected item
        }

        emit_navigation_event(
            NavigationEvents.SHOW_PREVIEW,
            preview_event_data
        )

        logger.info(f"✅ Preview event emitted for {file_path}")

    except Exception as e:
        logger.error(f"Failed to load preview from selection: {e}", exc_info=True)
```

**Key Features:**
- Extracts file path from metadata (prefers `local_path` for downloaded files)
- Checks for processing outputs via LibraryManager
- Emits SHOW_PREVIEW event to trigger existing preview loading logic
- Passes collection items for prev/next navigation
- Comprehensive error handling

### 4. Implemented `_clear_preview` Method

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

**Location:** Lines 1812-1822

This method clears the preview pane when no item is selected:

```python
def _clear_preview(self):
    """Clear the preview pane when no item is selected"""
    try:
        if self.cached_output_view:
            logger.info("📤 Clearing preview pane (no selection)")
            # Call load_output with no arguments to clear
            self.cached_output_view.load_output()
        else:
            logger.debug("No cached output view to clear")
    except Exception as e:
        logger.error(f"Failed to clear preview: {e}", exc_info=True)
```

### 5. Added Deduplication Logic

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

**Location:** Lines 926-936 in `_on_show_preview()` method

Added logic to prevent loading the same item twice:

```python
# Track last loaded item to prevent duplicates
if not hasattr(self, '_last_preview_item_id'):
    self._last_preview_item_id = None

# Skip if this item is already loaded
current_item_id = item_id
if current_item_id and current_item_id == self._last_preview_item_id:
    logger.debug(f"Item {current_item_id} already loaded in preview, skipping")
    return

self._last_preview_item_id = current_item_id
```

**Key Features:**
- Tracks the last loaded item ID
- Skips preview loading if the same item is already displayed
- Prevents duplicate events from causing redundant work

## Architecture Integration

### Event Flow

1. **User selects item in CollectionView**
   - CollectionView calls `selection_manager.set_selection()`
   - SelectionManager emits SELECTION_CHANGED event

2. **MainWindow receives SELECTION_CHANGED event**
   - Two handlers process the event independently:
     - `_handle_selection_changed()` - Updates status bar (existing)
     - `_handle_preview_selection_changed()` - Updates preview (new)

3. **Preview handler filters and processes event**
   - Checks if event is from collection view (ignores library/preview)
   - Extracts file path and metadata
   - Checks for processing outputs
   - Emits SHOW_PREVIEW event

4. **Existing preview loading logic takes over**
   - `_on_show_preview()` receives SHOW_PREVIEW event
   - Deduplication check prevents redundant loading
   - PreviewView loads the file

### Event Data Structure

**SELECTION_CHANGED Event (from SelectionManager):**
```python
{
    'view_id': 'collection',           # Which view the selection is from
    'context': 'collection',           # SelectionContext enum value
    'old_selection': [...],            # Previous selection
    'new_selection': [...],            # Current selection (item IDs)
    'count': 1,                        # Number of selected items
    'metadata': [{...}],               # List of metadata dicts
    'timestamp': 1234567890.123        # When selection changed
}
```

**SHOW_PREVIEW Event (emitted by our handler):**
```python
{
    'file_path': '/path/to/file.jpg',  # File to preview
    'item_id': 'item-123',             # Library item ID
    'output_data': {...},              # Processing outputs (if any)
    'file_metadata': {...},            # Item metadata
    'collection_items': [...],         # All items for navigation
    'item_index': 0                    # Current item index
}
```

## Success Criteria

- [x] SELECTION_CHANGED subscription added for preview updates
- [x] `_handle_preview_selection_changed` implemented
- [x] `_load_preview_from_selection` implemented
- [x] `_clear_preview` implemented
- [x] Deduplication logic added to prevent duplicate loading
- [x] Event filtering (only responds to collection view)
- [x] Comprehensive logging for debugging
- [x] Error handling in all methods

## Testing

### Manual Test Procedure

1. Launch the Fichero app
2. Select a collection from the Library sidebar
3. Collection view displays items
4. Click on an item in the collection view
5. **VERIFY:** Preview pane automatically loads the selected item
6. Click again to deselect the item
7. **VERIFY:** Preview pane clears

### Expected Log Messages

When selecting an item:
```
🔍 Preview selection change from view: collection, items: 1
📄 Loading preview for: /path/to/file.jpg
✅ Preview event emitted for /path/to/file.jpg
Event: Show output for /path/to/file.jpg
```

When deselecting an item:
```
🔍 Preview selection change from view: collection, items: 0
Empty selection, clearing preview
📤 Clearing preview pane (no selection)
```

When item is already loaded (deduplication):
```
Item item-123 already loaded in preview, skipping
```

### Test Script

A manual test script is provided at:
`/Users/dtubb/code/fichero_main/fichero/test_preview_selection.py`

Usage:
```bash
python test_preview_selection.py
```

## Known Limitations

1. **Multi-select behavior:** When multiple items are selected, only the first item is shown in the preview. This is intentional - showing multiple previews would require a different UI design.

2. **Library sidebar selections:** The preview does NOT update when collections are selected in the library sidebar. This is intentional - the library sidebar is for navigation, not preview.

3. **Preview pane selections:** The preview pane itself can emit selection events (e.g., when selecting panes in split view), but these are filtered out to prevent confusion.

## Future Enhancements

1. **Prev/Next Navigation:** Add arrow keys to navigate through collection items while preview is focused

2. **Multi-item Preview:** Consider a grid/gallery view when multiple items are selected

3. **Thumbnail Caching:** Cache thumbnails to speed up preview switching

4. **Keyboard Shortcuts:** Add keyboard shortcuts for preview navigation (e.g., Cmd+[ and Cmd+])

## Files Modified

1. `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`
   - Added SELECTION_CHANGED subscription for preview (line 446)
   - Implemented `_handle_preview_selection_changed()` (lines 1729-1748)
   - Implemented `_load_preview_from_selection()` (lines 1750-1810)
   - Implemented `_clear_preview()` (lines 1812-1822)
   - Added deduplication logic in `_on_show_preview()` (lines 926-936)

## Files Created

1. `/Users/dtubb/code/fichero_main/fichero/test_preview_selection.py`
   - Manual test script for selection integration

2. `/Users/dtubb/code/fichero_main/fichero/PHASE1_SELECTION_INTEGRATION_IMPLEMENTATION.md`
   - This implementation report

## Dependencies

- Existing SelectionManager (emits SELECTION_CHANGED events)
- Existing NavigationEventBus (event routing)
- Existing PreviewView (loads and displays files)
- Existing LibraryManager (provides processing output data)

## Conclusion

The implementation is complete and ready for testing. The preview pane now automatically updates when items are selected in the collection view, with proper deduplication and error handling. The architecture follows the existing event-driven pattern and integrates cleanly with the SelectionManager and NavigationEventBus.

## Next Steps

1. **Manual Testing:** Run the test script and verify the behavior matches expectations
2. **Bug Fixes:** Address any issues found during testing
3. **Phase 2:** Implement preview-initiated navigation (select item in preview, scroll to it in collection)
