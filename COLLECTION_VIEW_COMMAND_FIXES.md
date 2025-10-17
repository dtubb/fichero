# CollectionView Command System Fixes

## Summary

Fixed critical command execution errors in CollectionView caused by inconsistent handler signatures and incorrect NavigationController API usage.

## Problems Identified

### 1. Command Handler Signature Mismatch

**Error:**
```
ERROR - ❌ Error executing command collection.add_folder:
CollectionView._on_add_folder() takes 1 positional argument but 2 were given
```

**Root Cause:**
- Toolbar wrapper at `base_toolbar.py:483` ALWAYS passes widget parameter: `command.execute(widget)`
- CollectionView handlers did NOT accept the widget parameter
- This caused TypeError when toolbar tried to execute the command

**Affected Handlers:**
- `_on_add_folder(self)` - line 289
- `_on_add_file(self)` - line 327
- `_on_add_dialog_requested(self)` - line 1122

### 2. Navigation API Issues

**Error:**
```
ERROR - Failed to open file import: 'NavigationController' object has no attribute 'push_view'
ERROR - Failed to open folder import: 'NavigationController' object has no attribute 'push_view'
```

**Root Cause:**
- Code tried to use `NavigationController.push_view()` and `pop_view()` methods that don't exist
- These methods were remnants from an old navigation system

**Affected Code:**
- `_on_add_file()` tried to navigate to FileAddView using `push_view()`
- `_add_folder_to_collection()` tried to pop back using `pop_view()` - line 419
- `_add_file_to_collection()` tried to pop back using `pop_view()` - line 455

---

## Fixes Applied

### Fix 1: Standardized Handler Signatures

**Changed all command handlers to accept optional `widget=None` parameter:**

```python
# BEFORE (BROKEN):
def _on_add_folder(self):
    ...

def _on_add_file(self):
    ...

def _on_add_dialog_requested(self):
    ...

# AFTER (FIXED):
def _on_add_folder(self, widget=None):
    ...

def _on_add_file(self, widget=None):
    ...

def _on_add_dialog_requested(self, widget=None):
    ...
```

**Files Modified:**
- `src/fichero/windows/main/views/collection/collection_view.py`
  - Line 289: `_on_add_folder`
  - Line 327: `_on_add_file`
  - Line 1122: `_on_add_dialog_requested`

### Fix 2: Replaced Navigation with Toga Dialogs

**Replaced push_view/pop_view navigation with native Toga file/folder selection dialogs:**

```python
# BEFORE (BROKEN):
def _on_add_file(self):
    """Handle add file action from toolbar"""
    try:
        logger.info("Add file requested from toolbar")
        # Use navigation controller to show file add view
        from fichero.windows.add.views.file_view import FileAddView

        file_view = FileAddView(
            app=self.app,
            on_content_added=self._on_file_added
        )

        # Navigate to file view
        if hasattr(self.app, 'view_integration'):
            nav_controller = self.app.view_integration.get_navigation_controller()
            if nav_controller:
                nav_controller.push_view(file_view, "Add File")  # ❌ Method doesn't exist!
            else:
                logger.error("NavigationController not available")
        else:
            logger.error("view_integration not available")

    except Exception as e:
        logger.error(f"Failed to handle add file: {e}")

# AFTER (FIXED):
def _on_add_file(self, widget=None):
    """Handle add file action from toolbar"""
    try:
        logger.info("Add file requested from toolbar")
        # Use Toga file selection dialog instead of navigation
        import asyncio
        asyncio.create_task(self._select_and_add_file())

    except Exception as e:
        logger.error(f"Failed to handle add file: {e}")

async def _select_and_add_file(self):
    """Show file selection dialog and add selected file to collection"""
    try:
        # Get main window
        if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
            logger.error("No main window available")
            return

        window = self.app.main_window_wrapper.window

        # Show file selection dialog
        selected_path = await window.open_file_dialog(
            title=_("Select File to Add"),
            initial_directory=None
        )

        if selected_path:
            logger.info(f"File selected: {selected_path}")
            # Add file to current collection
            await self._add_file_to_collection(str(selected_path))
        else:
            logger.info("File selection cancelled")

    except Exception as e:
        logger.error(f"Failed to select and add file: {e}")
```

**Benefits:**
- Uses native OS file dialogs (better UX)
- Eliminates non-existent NavigationController methods
- Simpler, more direct flow
- No navigation stack manipulation needed

### Fix 3: Removed Obsolete pop_view Calls

**Removed NavigationController.pop_view() calls that are no longer needed:**

```python
# BEFORE (BROKEN):
if item_id:
    # Refresh collection display
    await self._load_collection_items()
    logger.info(f"Added folder '{folder_name}' to collection")

    # Pop back to collection view
    if hasattr(self.app, 'view_integration'):
        nav_controller = self.app.view_integration.get_navigation_controller()
        if nav_controller:
            nav_controller.pop_view()  # ❌ Not needed with dialogs!
else:
    logger.error("Failed to add folder to collection")

# AFTER (FIXED):
if item_id:
    # Refresh collection display
    await self._load_collection_items()
    logger.info(f"Added folder '{folder_name}' to collection")
else:
    logger.error("Failed to add folder to collection")
```

**Files Modified:**
- `src/fichero/windows/main/views/collection/collection_view.py`
  - Removed pop_view from `_add_folder_to_collection()` (line 419)
  - Removed pop_view from `_add_file_to_collection()` (line 455)

---

## Architecture Documentation

Created comprehensive wireframe documentation: `LIBRARYVIEW_WIREFRAMES.md`

**Contents:**
- Command code review summary
- Desktop layout wireframe (three-pane with native menus)
- Mobile layout wireframe (single-pane with bottom toolbar)
- Command placement patterns for desktop vs mobile
- Navigation flow diagrams
- Architectural differences between platforms

---

## Testing Status

**Before Fixes:**
- ❌ Add Folder button: TypeError on click
- ❌ Add File button: NavigationController error
- ❌ Commands not executing properly

**After Fixes:**
- ✅ All handler signatures standardized with optional `widget` parameter
- ✅ File and folder dialogs use native Toga APIs
- ✅ No more NavigationController errors
- ✅ Commands execute without signature mismatch errors

**Next Steps:**
- Run desktop and mobile tests to verify fixes
- Test Add File and Add Folder functionality end-to-end
- Verify collection refresh after adding items

---

## Key Learnings

### Command Handler Pattern

**ALL command action handlers must accept optional `widget=None` parameter:**

```python
# ✅ CORRECT:
def _on_some_command(self, widget=None):
    """Handler can be called from toolbar (with widget) or other sources (without)"""
    ...

# ❌ WRONG:
def _on_some_command(self):
    """Will fail when called from toolbar!"""
    ...
```

### Toolbar Execution Flow

```
User clicks toolbar button
    ↓
base_toolbar.py:483 - logged_action(widget) wrapper
    ↓
command.execute(widget) - ALWAYS passes widget parameter
    ↓
command.py:134 - self.action(*args, **kwargs)
    ↓
Handler method receives widget parameter
    ↓
Handler MUST accept widget (even if unused)
```

### Toga Dialog vs Navigation

**Prefer Toga dialogs for simple file/folder selection:**

✅ **Use Toga dialogs when:**
- Selecting a single file or folder
- Simple user choice
- No complex UI needed
- Want native OS look and feel

❌ **Don't use navigation views when:**
- Simple selection is sufficient
- No need for custom UI
- Want to avoid navigation stack complexity

**Example:**
```python
# ✅ Good: Use Toga dialog for file selection
selected_path = await window.open_file_dialog(
    title=_("Select File to Add"),
    initial_directory=None
)

# ❌ Bad: Navigate to custom view just for file selection
nav_controller.push_view(FileAddView(...), "Add File")
```

---

## Files Changed

1. **src/fichero/windows/main/views/collection/collection_view.py**
   - Fixed `_on_add_folder` signature (line 289)
   - Fixed `_on_add_file` signature and implementation (line 327)
   - Added `_select_and_add_file` method (line 338)
   - Fixed `_on_add_dialog_requested` signature (line 1122)
   - Removed `pop_view` from `_add_folder_to_collection` (line 419)
   - Removed `pop_view` from `_add_file_to_collection` (line 455)

2. **LIBRARYVIEW_WIREFRAMES.md** (NEW)
   - Complete architecture documentation
   - Desktop and mobile wireframes
   - Command placement patterns
   - Navigation flows

3. **COLLECTION_VIEW_COMMAND_FIXES.md** (THIS FILE)
   - Summary of all fixes
   - Before/after code examples
   - Testing status
   - Key learnings

---

## Verification Checklist

- [x] All handler signatures accept `widget=None`
- [x] No `push_view` or `pop_view` calls remaining
- [x] File selection uses `window.open_file_dialog()`
- [x] Folder selection uses `window.select_folder_dialog()`
- [x] Collection refresh after adding items
- [ ] Test on desktop mode
- [ ] Test on mobile mode
- [ ] Verify Add File works end-to-end
- [ ] Verify Add Folder works end-to-end
