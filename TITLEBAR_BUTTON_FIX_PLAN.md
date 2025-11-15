# Titlebar Button Fix Plan

**Date:** 2025-11-15
**Issue:** Titlebar buttons duplicated, icon path warnings
**Root Cause:** Commands added from both registry query AND pending list in `_initialize_toolbar()`

---

## Fix 1: Prevent Button Duplication

### Strategy

**Remove the registry query approach and rely solely on the pending list mechanism.**

**Rationale:**
- Pending list was designed for commands registered before window ready
- Registry query was added later and creates duplication
- Pending list approach is cleaner and more dynamic
- Preserves the "register anytime" design pattern

### Code Changes

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/commands/mac_toolbar_manager.py`

**Change 1: Remove Registry Query Block**

**Location:** Lines 460-476

**Old Code:**
```python
        # Add titlebar accessories from ALL commands (not just filtered ones)
        # Query CommandManager for all commands with show_in_titlebar=True
        if command_manager:
            logger.debug("Looking for titlebar commands...")
            # Get ALL registered commands
            all_commands = command_manager.registry.list_all()
            logger.debug(f"Total registered commands: {len(all_commands)}")

            # Filter for titlebar commands (no view_id filtering)
            titlebar_commands = [
                cmd for cmd in all_commands
                if getattr(cmd, 'show_in_titlebar', False)
            ]
            logger.debug(f"Found {len(titlebar_commands)} titlebar commands: {[cmd.id for cmd in titlebar_commands]}")

            if titlebar_commands:
                self._add_titlebar_accessories(titlebar_commands)
```

**New Code:**
```python
        # Titlebar accessories are added via pending list processing below
        # (No registry query needed - pending list captures all titlebar commands)
```

**Explanation:**
- Remove lines 460-476 entirely
- Replace with explanatory comment
- Titlebar accessories will still be added via `_process_pending_titlebar_commands()` on line 481

**Change 2: Update Comment for Pending Processing**

**Location:** Line 478-482

**Old Code:**
```python
        # Process any titlebar commands that were registered before initialization
        if command_manager:
            window_id = id(self.window)
            command_manager._process_pending_titlebar_commands(window_id)
            logger.debug("Processed pending titlebar commands")
```

**New Code:**
```python
        # Process titlebar commands from pending list
        # (Titlebar commands are added to pending list during registration)
        if command_manager:
            window_id = id(self.window)
            command_manager._process_pending_titlebar_commands(window_id)
            logger.info("✅ Processed pending titlebar commands")
```

**Explanation:**
- Update comment to reflect that ALL titlebar commands come from pending list
- Change debug to info for visibility

### Verification Steps

**Step 1:** Remove registry query block (lines 460-476)

**Step 2:** Update pending processing comment (line 478)

**Step 3:** Run application

**Expected Result:**
- Titlebar shows exactly 3 buttons (not 6)
- Buttons appear once each: Sidebar, Collection, Adjust
- No console warnings about duplicate additions

**Test Cases:**

1. **Initial Launch:**
   - Verify 3 titlebar buttons appear (Sidebar on left, Collection and Adjust on right)
   - Click each button and verify it works
   - Check console for no duplication warnings

2. **Window Reopen:**
   - Close window
   - Reopen window
   - Verify buttons still appear once (not duplicated)

3. **Dynamic Registration (Future):**
   - If new commands with `show_in_titlebar=True` are registered after initialization
   - Verify they appear via pending list mechanism
   - Verify no duplicates

---

## Fix 2: Fix Icon Resolution (If Needed)

### Investigation First

**Before implementing fix, verify the problem exists:**

**Step 1:** Run application with debug logging

```bash
cd /Users/dtubb/code/fichero_main/fichero
briefcase dev 2>&1 | tee /tmp/fichero_debug.log
```

**Step 2:** Search for icon warnings

```bash
grep -i "can't find icon\|WARNING.*icon\|folder.fill\|slider.horizontal" /tmp/fichero_debug.log
```

**Step 3:** Analyze results

If warnings appear:
- Note exact line numbers from traceback
- Check if icons actually fail to display (visual test)
- Identify code path that generates warnings

If no warnings appear:
- Icon issue may be historical or already fixed
- Skip Fix 2 entirely

### Strategy (If Warnings Confirmed)

**Improve SF Symbol detection in `_load_icon()` method**

**Problem:** Line 715 check treats SF Symbol names as file extensions

```python
if '/' in icon_path or icon_path.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.tiff')):
```

**Issue:** `"folder.fill"` ends with `.fill` which looks like an extension

### Code Changes (If Needed)

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/commands/mac_toolbar_manager.py`

**Change: Improve File Path Detection**

**Location:** Lines 714-730

**Old Code:**
```python
        # Try loading as file first (PNG, JPEG, etc.)
        if '/' in icon_path or icon_path.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.tiff')):
            # Validate path to prevent path traversal attacks
            try:
                app_base_path = Path(self.app.paths.app).resolve()
            except Exception as e:
                logger.warning(f"Could not resolve app base path: {e}")
                app_base_path = None
            # It's a file path - try multiple possible locations
            possible_paths = [
                icon_path,  # Absolute path
                os.path.join(os.getcwd(), icon_path),  # Relative to CWD
                Path(self.app.paths.app) / icon_path,  # Relative to app
                os.path.join(os.path.dirname(__file__), icon_path),  # Relative to this file
                os.path.join(os.path.dirname(__file__), '..', '..', icon_path),  # Up two levels
            ]
```

**New Code:**
```python
        # Detect if this is a file path or SF Symbol name
        # SF Symbols: Simple names with dots (e.g., "folder.fill", "house.circle.fill")
        # File paths: Contain "/" or end with image extensions
        is_file_path = (
            '/' in icon_path or
            icon_path.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.tiff', '.gif', '.svg'))
        )

        # Additional check: SF Symbols never contain "/", "\\", or end with common extensions
        # If icon_path is just "word.word" without path separators, treat as SF Symbol
        if '/' not in icon_path and '\\' not in icon_path:
            # Check if it looks like an SF Symbol (letters, dots, underscores only)
            import re
            if re.match(r'^[a-z0-9._]+$', icon_path):
                # Likely an SF Symbol, skip file loading
                logger.debug(f"Detected SF Symbol (not file path): {icon_path}")
                is_file_path = False

        # Try loading as file first (PNG, JPEG, etc.)
        if is_file_path:
            # Validate path to prevent path traversal attacks
            try:
                app_base_path = Path(self.app.paths.app).resolve()
            except Exception as e:
                logger.warning(f"Could not resolve app base path: {e}")
                app_base_path = None
            # It's a file path - try multiple possible locations
            possible_paths = [
                icon_path,  # Absolute path
                os.path.join(os.getcwd(), icon_path),  # Relative to CWD
                Path(self.app.paths.app) / icon_path,  # Relative to app
                os.path.join(os.path.dirname(__file__), icon_path),  # Relative to this file
                os.path.join(os.path.dirname(__file__), '..', '..', icon_path),  # Up two levels
            ]
```

**Explanation:**
- Add heuristic detection for SF Symbols vs file paths
- SF Symbols are lowercase alphanumeric with dots/underscores
- SF Symbols never contain path separators
- Skip file loading for detected SF Symbols
- Fall through to SF Symbol API (line 760)

**Alternative Simpler Fix:**

If the heuristic is too complex, use a simpler approach:

**Old Code (Line 715):**
```python
if '/' in icon_path or icon_path.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.tiff')):
```

**New Code:**
```python
# Only treat as file path if it contains "/" or ends with known image extensions
# (Exclude single-dot patterns like "folder.fill" which are SF Symbols)
if '/' in icon_path or icon_path.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.tiff', '.gif', '.svg')):
```

**Explanation:**
- Remove the problematic `.fill` match by being more specific about file extensions
- SF Symbols use dots as separators (e.g., `folder.fill`, `house.circle.fill`)
- Real image files end with known extensions (`.png`, `.jpg`, etc.)

**However:** This simple fix won't fully solve it because `icon_path.endswith()` checks if the string ends with ANY of the tuple values, not just exact extensions.

**Best Fix:** Skip file loading entirely if icon_path doesn't contain "/" AND doesn't end with a known extension:

```python
# Only try file loading if icon_path looks like a file path
# (Contains "/" OR ends with known image extension)
is_likely_file = '/' in icon_path or any(icon_path.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf', '.tiff', '.gif', '.svg'])

if is_likely_file:
    # File loading code...
```

### Verification Steps (If Fix Applied)

**Step 1:** Apply icon detection fix

**Step 2:** Run application with logging

```bash
cd /Users/dtubb/code/fichero_main/fichero
briefcase dev 2>&1 | grep -i "icon\|symbol" | head -50
```

**Expected Result:**
- No warnings about "Can't find icon .../folder.fill"
- Log shows "Detected SF Symbol: folder.fill"
- Log shows "Loaded SF Symbol: folder.fill"
- Icons display correctly in titlebar

**Test Cases:**

1. **SF Symbol Icons:**
   - Verify `folder.fill` loads without warnings
   - Verify `slider.horizontal.3` loads without warnings
   - Verify `sidebar.left` loads without warnings
   - Icons appear correctly in titlebar buttons

2. **File-Based Icons (If Any):**
   - Verify file paths still work
   - Verify relative paths resolve correctly
   - No regressions for existing file-based icons

---

## Fix 3: Code Cleanup

### Remove Obsolete Method (Optional)

**Method:** `_add_titlebar_accessories()` (lines 1233-1362)

**Status:** May become obsolete after Fix 1

**Decision:** **KEEP for now**

**Rationale:**
- Method may be used by other code paths
- Removing requires thorough testing
- Can be deprecated in future release
- No harm in keeping it

### Add Deduplication Guard (Belt and Suspenders)

**Even after Fix 1, add safety check to prevent future duplicates**

**File:** `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/commands/mac_toolbar_manager.py`

**Location:** Line 1364 (inside `add_titlebar_accessory()`)

**Add at beginning of method:**

```python
def add_titlebar_accessory(self, command: Any) -> None:
    """
    Add a single titlebar accessory button dynamically.
    """
    if not RUBICON_AVAILABLE:
        logger.warning("Cannot add titlebar accessory: rubicon not available")
        return

    if not self.window:
        logger.warning("Cannot add titlebar accessory: no window")
        return

    # Check for duplicate (prevent adding same command twice)
    if hasattr(self, '_titlebar_accessories'):
        existing_ids = [acc['command_id'] for acc in self._titlebar_accessories]
        if command.id in existing_ids:
            logger.warning(f"⚠️ Titlebar accessory already exists, skipping: {command.id}")
            return

    try:
        logger.debug(f"Adding titlebar accessory for command: {command.id}")
        # ... rest of method
```

**Explanation:**
- Check if command already exists in `_titlebar_accessories` list
- Skip if duplicate detected
- Log warning for debugging
- Prevents accidental double-addition in future

---

## Testing Plan

### Pre-Fix Testing

**Verify Current State:**

1. Launch application
2. Count titlebar buttons (expect 6: 3 duplicates)
3. Take screenshot of titlebar
4. Check console for icon warnings
5. Document baseline behavior

### Post-Fix Testing

**Test Fix 1 (Duplication):**

1. Apply registry query removal
2. Launch application
3. Count titlebar buttons (expect 3: no duplicates)
4. Verify buttons work correctly:
   - Sidebar button shows menu
   - Collection button toggles Collection pane
   - Adjust button toggles Adjust pane
5. Close and reopen window
6. Verify buttons still appear once (no regression)

**Test Fix 2 (Icons - If Applied):**

1. Check console for icon warnings (expect none)
2. Verify icons display correctly in buttons
3. Take screenshot of titlebar
4. Compare icons to expected SF Symbols
5. Verify no visual regressions

**Regression Testing:**

1. Test menu commands still work
2. Test keyboard shortcuts still work
3. Test toolbar (if any) still works
4. Test Settings window (uses different mechanism)
5. Test all view toggle actions work correctly

### Success Criteria

**Must Have:**
- ✅ Exactly 3 titlebar buttons (not 6)
- ✅ Each button works correctly
- ✅ No duplicate button errors
- ✅ No console warnings about icon loading (if Fix 2 applied)
- ✅ Icons display correctly

**Nice to Have:**
- ✅ Deduplication guard prevents future duplicates
- ✅ Clean console logs with info messages
- ✅ Code cleanup removes obsolete comments

---

## Implementation Order

**Phase 1: Fix Duplication (Critical)**
1. Remove registry query block (lines 460-476)
2. Update pending processing comment (line 478)
3. Test thoroughly

**Phase 2: Investigate Icons (If Needed)**
1. Run app with logging
2. Confirm icon warnings exist
3. If yes, apply Fix 2
4. If no, skip Fix 2

**Phase 3: Add Guards (Safety)**
1. Add deduplication check to `add_titlebar_accessory()`
2. Test edge cases (double registration, etc.)

**Phase 4: Cleanup (Optional)**
1. Review obsolete code
2. Remove unused methods (if any)
3. Update documentation

---

## Rollback Plan

**If Fix 1 Breaks:**
- Revert registry query removal
- Add deduplication check instead:
  ```python
  # Track which commands we've already added
  if not hasattr(self, '_added_titlebar_command_ids'):
      self._added_titlebar_command_ids = set()

  # Deduplicate before adding
  titlebar_commands = [
      cmd for cmd in titlebar_commands
      if cmd.id not in self._added_titlebar_command_ids
  ]

  # Add to tracker
  for cmd in titlebar_commands:
      self._added_titlebar_command_ids.add(cmd.id)
  ```

**If Fix 2 Breaks:**
- Revert `_load_icon()` changes
- Use explicit file extension check
- Or skip file loading for SF Symbols entirely

---

## Risk Assessment

**Fix 1 (Duplication Removal):**
- **Risk:** LOW
- **Impact:** HIGH (fixes critical bug)
- **Reversibility:** HIGH (simple revert)
- **Dependencies:** None

**Fix 2 (Icon Resolution):**
- **Risk:** MEDIUM (changes icon loading logic)
- **Impact:** MEDIUM (fixes warnings, may improve performance)
- **Reversibility:** HIGH (simple revert)
- **Dependencies:** None

**Fix 3 (Cleanup):**
- **Risk:** LOW
- **Impact:** LOW (code quality improvement)
- **Reversibility:** HIGH
- **Dependencies:** None

---

## Timeline Estimate

**Fix 1:** 15 minutes
- 5 min: Remove code
- 10 min: Test

**Fix 2:** 30 minutes (if needed)
- 10 min: Investigate
- 10 min: Implement
- 10 min: Test

**Fix 3:** 15 minutes
- 10 min: Add guard
- 5 min: Test

**Total:** 30-60 minutes (depending on whether Fix 2 is needed)

---

## Post-Implementation

**Documentation Updates:**
- Update `TOOLBAR_INTEGRATION_PLAN.md` to reflect fix
- Add note about pending list mechanism
- Document deduplication guard

**Code Review:**
- Review changes with team
- Verify no side effects
- Check for similar patterns elsewhere

**Future Prevention:**
- Add unit test for titlebar accessory deduplication
- Add integration test for titlebar button count
- Document pending list pattern for future developers

