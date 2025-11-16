# PHASE 2: IMPLEMENTATION PLAN - Collection Rename & Delete

## Overview

This plan details the exact code changes needed to implement:
1. Double-click to rename collections
2. "Delete Collection" command in File menu

Both features will integrate with existing LibraryManager backend methods.

---

## PART A: Collection Rename via Double-Click

### A1. Wire `on_activate` to ListWidget

**File:** `src/fichero/windows/main/views/library/library_view.py`
**Location:** `_recreate_detailed_list()` method, around line 318

**Current code:**
```python
self.collections_list = ListWidget(
    headings=['Collections'],
    data=tree_data,
    on_select=self._on_tree_select,  # Use wrapper for selection
    style=Pack(
        flex=1,
        margin_left=2  # Small left margin so focus ring is visible
    ),
    renderer='sidebar'  # Custom sidebar renderer for narrow Library column
)
```

**Change to:**
```python
self.collections_list = ListWidget(
    headings=['Collections'],
    data=tree_data,
    on_select=self._on_tree_select,  # Single-click selection
    on_activate=self._on_collection_activate,  # Double-click rename
    style=Pack(
        flex=1,
        margin_left=2  # Small left margin so focus ring is visible
    ),
    renderer='sidebar'  # Custom sidebar renderer for narrow Library column
)
```

### A2. Create Activation Handler

**File:** `src/fichero/windows/main/views/library/library_view.py`
**Location:** Add new method after `_on_tree_select()` (around line 480)

**New method:**
```python
def _on_collection_activate(self, selection):
    """
    Handle double-click on collection (activate event).

    Opens rename dialog for the selected collection.

    Args:
        selection: The activated item from ListWidget
    """
    try:
        logger.info(f"Collection activated (double-click): {selection}")

        # Extract collection data from selection
        collection_data = None
        if isinstance(selection, dict):
            collection_data = selection
        elif hasattr(selection, '_collection_data'):
            collection_data = selection._collection_data
        elif hasattr(selection, '__dict__'):
            # Try to extract from Row/Node attributes
            collection_id = getattr(selection, 'id', None) or getattr(selection, 'collection_id', None)
            if collection_id and hasattr(self, '_tree_data_map'):
                collection_data = self._tree_data_map.get(collection_id)

        if not collection_data:
            logger.warning("Could not extract collection data from activation")
            return

        # Open rename dialog
        self._show_rename_dialog(collection_data)

    except Exception as e:
        logger.error(f"Error handling collection activation: {e}", exc_info=True)
```

### A3. Create Rename Dialog

**File:** `src/fichero/windows/main/views/library/library_view.py`
**Location:** Add new method after `_on_collection_activate()` (around line 520)

**New method:**
```python
def _show_rename_dialog(self, collection_data: Dict[str, Any]):
    """
    Show dialog to rename a collection.

    Args:
        collection_data: Collection data dict with 'id' and 'name' keys
    """
    try:
        collection_id = collection_data.get('id')
        current_name = collection_data.get('name', 'Unnamed')

        if not collection_id:
            logger.error("Cannot rename: collection ID missing")
            self.app.main_window.error_dialog(
                "Error",
                "Cannot rename collection: Invalid collection data"
            )
            return

        logger.info(f"Showing rename dialog for collection '{current_name}' (ID: {collection_id})")

        # Show input dialog (async)
        async def show_dialog():
            try:
                new_name = await self.app.main_window.question_dialog(
                    _("Rename Collection"),
                    f"{_('Enter new name for')}: {current_name}"
                )

                if new_name and new_name.strip():
                    new_name = new_name.strip()

                    # Validate name is different
                    if new_name == current_name:
                        logger.debug("Name unchanged, skipping rename")
                        return

                    # Call LibraryManager to rename
                    success = await self.library_service.rename_collection(
                        collection_id, new_name
                    )

                    if success:
                        logger.info(f"Collection renamed: '{current_name}' → '{new_name}'")

                        # Refresh collections list to show new name
                        await self.refresh_collections()

                        # Show success message
                        await self.app.main_window.info_dialog(
                            _("Success"),
                            _("Collection renamed to '{}'").format(new_name)
                        )
                    else:
                        logger.error(f"Failed to rename collection '{current_name}'")
                        await self.app.main_window.error_dialog(
                            _("Error"),
                            _("Failed to rename collection. Please try again.")
                        )
                elif new_name is not None:
                    # User entered empty name
                    logger.warning("Empty collection name rejected")
                    await self.app.main_window.error_dialog(
                        _("Invalid Name"),
                        _("Collection name cannot be empty.")
                    )
                # else: User cancelled dialog (new_name is None)

            except Exception as e:
                logger.error(f"Error in rename dialog: {e}", exc_info=True)
                await self.app.main_window.error_dialog(
                    _("Error"),
                    _("An error occurred while renaming: {}").format(str(e))
                )

        # Schedule async dialog
        import asyncio
        asyncio.create_task(show_dialog())

    except Exception as e:
        logger.error(f"Error showing rename dialog: {e}", exc_info=True)
```

---

## PART B: Delete Collection Command

### B1. Add Delete Command Definition

**File:** `src/fichero/windows/main/views/library/library_view.py`
**Location:** In `define_commands()` method, after `new_collection_from_folder` command (around line 1596)

**Add new command:**
```python
'delete_collection': FicheroCommand(
    id=f'{self.view_id}.delete_collection',
    label=_("Delete Collection…"),
    action=self._on_delete_collection,
    shortcut=toga.Key.MOD_1 + toga.Key.BACKSPACE,  # Cmd+Backspace (macOS standard for delete)
    icon='resources/icons/toolbar/trash.png',
    description=_("Delete the selected collection"),
    group=toga.Group.FILE,  # File menu on desktop
    section=1,  # Second section (after New Collection commands)
    order=0,  # First item in delete section
    show_in_menu=True,  # Appear in File menu on desktop
    show_in_toolbar=False,  # NOT in toolbar (dangerous action)
    show_in_bottom_toolbar=False,  # Not on mobile
    desktop_only=True,  # Only on desktop
    context='normal',
    enabled=False  # Disabled by default (enabled when collection selected)
),
```

### B2. Update Command State on Selection Change

**File:** `src/fichero/windows/main/views/library/library_view.py`
**Location:** In `_on_collection_selected()` method (around line 441)

**Find the section where selection is processed and add:**

After this line (around line 476):
```python
self.selected_collection = collection_data
```

**Add:**
```python
# Enable/disable delete command based on selection
if hasattr(self, 'commands') and 'delete_collection' in self.commands:
    if collection_data:
        self.commands['delete_collection'].enable()
        logger.debug("Delete Collection command enabled")
    else:
        self.commands['delete_collection'].disable()
        logger.debug("Delete Collection command disabled")
```

### B3. Create Delete Handler

**File:** `src/fichero/windows/main/views/library/library_view.py`
**Location:** Add new method after rename dialog (around line 620)

**New method:**
```python
def _on_delete_collection(self, widget=None):
    """
    Handle delete collection command.

    Shows confirmation dialog, then deletes the selected collection.

    Args:
        widget: Toga widget that triggered the command (unused)
    """
    try:
        if not self.selected_collection:
            logger.warning("Delete collection called but no collection selected")
            return

        collection_id = self.selected_collection.get('id')
        collection_name = self.selected_collection.get('name', 'Unnamed')

        if not collection_id:
            logger.error("Cannot delete: collection ID missing")
            self.app.main_window.error_dialog(
                _("Error"),
                _("Cannot delete collection: Invalid collection data")
            )
            return

        logger.info(f"Delete requested for collection '{collection_name}' (ID: {collection_id})")

        # Show confirmation dialog (async)
        async def confirm_and_delete():
            try:
                # Confirmation dialog
                confirm = await self.app.main_window.confirm_dialog(
                    _("Delete Collection"),
                    _("Are you sure you want to delete '{}'?\n\n"
                      "This will permanently remove the collection and all its items. "
                      "This cannot be undone.").format(collection_name)
                )

                if not confirm:
                    logger.debug("Collection delete cancelled by user")
                    return

                # Call LibraryManager to delete
                success = await self.library_service.delete_collection(collection_id)

                if success:
                    logger.info(f"Collection deleted: '{collection_name}'")

                    # Clear selection
                    self.selected_collection = None

                    # Refresh collections list
                    await self.refresh_collections()

                    # Navigate to library view (clear collection view)
                    # This handles the edge case where we deleted the currently viewed collection
                    from fichero.shared.navigation.navigation_event_bus import emit_navigation_event
                    emit_navigation_event("navigate_to_library", {})

                    # Show success message
                    await self.app.main_window.info_dialog(
                        _("Deleted"),
                        _("Collection '{}' has been deleted.").format(collection_name)
                    )
                else:
                    logger.error(f"Failed to delete collection '{collection_name}'")
                    await self.app.main_window.error_dialog(
                        _("Error"),
                        _("Failed to delete collection. Please try again.")
                    )

            except Exception as e:
                logger.error(f"Error in delete confirmation: {e}", exc_info=True)
                await self.app.main_window.error_dialog(
                    _("Error"),
                    _("An error occurred while deleting: {}").format(str(e))
                )

        # Schedule async confirmation
        import asyncio
        asyncio.create_task(confirm_and_delete())

    except Exception as e:
        logger.error(f"Error handling delete collection: {e}", exc_info=True)
```

---

## Testing Plan

### Rename Testing:
1. Launch app and navigate to Library view
2. Double-click a collection
3. Verify rename dialog appears with current name
4. Enter new name and confirm
5. Verify collection list refreshes with new name
6. Verify collection is still selected
7. Test edge cases:
   - Empty name (should show error)
   - Cancel dialog (should do nothing)
   - Same name (should skip rename)

### Delete Testing:
1. Launch app and navigate to Library view
2. Select a collection
3. Verify "Delete Collection…" is enabled in File menu
4. Press Cmd+Backspace (or use File menu)
5. Verify confirmation dialog appears
6. Cancel → verify nothing deleted
7. Confirm → verify collection deleted from list
8. Verify app navigates to library view
9. Test with no selection:
   - Verify command is disabled
10. Test deleting currently viewed collection:
    - Open collection view
    - Delete collection from Library sidebar
    - Verify app navigates back to Library view

---

## File Summary

**Files to modify:** 1
- `src/fichero/windows/main/views/library/library_view.py`

**New methods to add:** 3
1. `_on_collection_activate()` - Handle double-click
2. `_show_rename_dialog()` - Show rename input dialog
3. `_on_delete_collection()` - Handle delete command with confirmation

**Modified methods:** 2
1. `_recreate_detailed_list()` - Add `on_activate` parameter
2. `_on_collection_selected()` - Enable/disable delete command
3. `define_commands()` - Add delete command definition

**Estimated line additions:** ~200 lines
**Estimated line modifications:** ~20 lines

---

## Risk Assessment

### Low Risk:
- Backend methods already exist and tested
- No changes to data model
- No changes to navigation system (except navigate_to_library after delete)
- Commands follow established patterns

### Medium Risk:
- Dialog async handling (need to ensure proper error handling)
- Selection state management after delete
- List refresh after rename/delete

### Mitigations:
- Extensive try/except blocks with logging
- Clear error messages to user
- Refresh collections list after both operations
- Navigate to library view after delete to avoid stale state

---

## Implementation Order

1. **First:** Implement rename (lower risk, simpler)
   - Add `on_activate` parameter
   - Add `_on_collection_activate()` method
   - Add `_show_rename_dialog()` method
   - Test thoroughly

2. **Second:** Implement delete (needs command state management)
   - Add `delete_collection` command definition
   - Add `_on_delete_collection()` method
   - Modify `_on_collection_selected()` for command state
   - Test thoroughly

3. **Third:** Integration testing
   - Test both features together
   - Test edge cases
   - Test on different platforms if possible

---

## Next Step

Proceed to PHASE 3: Implementation
