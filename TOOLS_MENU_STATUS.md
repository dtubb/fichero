# Tools Menu Implementation Status

## ✅ Completed

### Phase 1: Menu Structure
- ✅ Created `ToolsMenuManager` class in `tools_menu_manager.py`
- ✅ Integrated with Toga's Command system (not custom Menu/MenuItem)
- ✅ Three submenus implemented:
  - **Adjust** - Section 0 (opens inspector for tool parameters)
  - **Go To** - Section 1 (navigates to step outputs)
  - **Process** - Section 2 (runs tools on current item)

### Phase 2: OutputView Integration
- ✅ `ToolsMenuManager` initialized in OutputView.__init__()
- ✅ `_setup_tools_menu()` method added to OutputView
- ✅ Menu state updates wired to `_update_ui_from_state()`
- ✅ Menu commands added to app.commands on initialization

### Phase 3: Initial Commands (Rotate Focus)
- ✅ **Adjust Rotate...** - Opens inspector with rotation parameters
- ✅ **Go To Original Image** - Navigates to step 0
- ✅ **Rotate Image...** - Process dialog (placeholder for now)

## Implementation Details

### How It Works

1. **Command Registration**: Commands are added to `app.commands` using Toga's `Command` class
2. **Groups**: All commands use custom `Tools` group (order=50)
3. **Sections**:
   - Section 0: Adjust commands
   - Section 1: Go To commands
   - Section 2: Process commands
4. **State Updates**: Commands enable/disable based on current step and item selection

### Files Modified

```
src/fichero/windows/main/views/output/
├── tools_menu_manager.py          # NEW: Menu management
└── output_view.py                  # MODIFIED: Integration

Documentation:
├── TOOLS_MENU_IMPLEMENTATION_PLAN.md  # Complete specification
└── TOOLS_MENU_STATUS.md              # This file
```

### Example: Adjust Rotate Command

```python
cmd = toga.Command(
    action=lambda widget: self._on_adjust('rotate'),
    text='Adjust Rotate...',
    tooltip='Adjust rotation parameters',
    group=tools_group,         # Custom "Tools" group
    section=0,                 # Adjust section
    order=0
)
app.commands.add(cmd)
```

When clicked:
1. Finds step with `tool_name == 'rotate'`
2. Navigates to that step
3. Opens inspector with rotate parameters from renderer

### Menu State Management

Commands automatically update enabled/disabled state when:
- Item changes (`_update_ui_from_state()`)
- Step changes (`_update_ui_from_state()`)
- User navigates (`_on_step_state_changed()`)

**Example logic:**
```python
# Adjust Rotate enabled only when viewing rotate step
cmd.enabled = (current_tool == 'rotate')

# Process commands enabled only when item selected
cmd.enabled = bool(state.item_id)
```

## Testing

To test the Tools menu:

1. **Start the app** with debug logging:
   ```bash
   cd /Users/dtubb/code/fichero_main/fichero
   FICHERO_LOG_LEVEL=DEBUG briefcase dev
   ```

2. **Load a rotated item**:
   - Navigate to Library
   - Find collection processed with Rotate.yml workflow
   - Select item with rotate step

3. **Test menu items**:
   - **Tools > Adjust Rotate...**
     - Should be enabled when viewing rotate step
     - Should open inspector with rotation parameters
   - **Tools > Go To Original Image**
     - Should always be enabled
     - Should navigate to step 0
   - **Tools > Rotate Image...**
     - Should be enabled when item selected
     - Should show "Process Rotate" dialog (placeholder)

4. **Check logs** for:
   ```
   INFO - ToolsMenuManager initialized
   INFO - Building Tools menu commands
   DEBUG - Added Adjust Rotate command
   DEBUG - Added Go To Original command
   DEBUG - Added Process Rotate command
   ```

## ✅ LATEST UPDATE - Manifest File Loading Added

### Recent Changes

**2025-11-04: Added manifest file loading for crop parameters**

The inspector was showing empty JSON (`{}`) because the `manifest_entry` wasn't being loaded. Fixed by:

1. **Added file system loading** in `output_view.py` (lines 989-1020):
   - Loads manifest from: `{file_path parent}/assets/{tool_name}d/{tool_name}_manifest.jsonl`
   - Example for crop: `.../EAP1740_NP_T19_1700_001_01.tif/assets/cropped/crop_manifest.jsonl`
   - Handles tool name variations (crop → cropped, rotate → rotated, etc.)

2. **Passes to RenderContext**:
   - `manifest_entry` now populated from file
   - `CropRenderer.get_editable_json()` can extract parameters
   - JSON editor displays: box coordinates, method, confidence, padding, sizes, rotation, attempts

**Status**: ✅ Completed - Generic manifest loading implemented

**Generic Data Approach** (2025-11-04):
- `CropRenderer._extract_crop_data()` now returns entire manifest_entry as-is
- No custom extraction logic needed
- Works automatically for all tool renderers
- Users can view and edit all fields without tool-specific code

---

## ✅ Simplified to Single "Adjust Current Tool..." Command

### What Changed
Following user feedback, the Tools menu was **simplified significantly**:

**OLD Design** (too complex):
- Separate menu items for each tool (Adjust Rotate..., Adjust Crop..., etc.)
- 20+ Adjust menu items (one per tool)

**NEW Design** (simple & flexible):
- **Single command**: "Adjust Current Tool..." (⌘⇧I)
- Shows/hides inspector panel for **whatever step is currently viewed**
- Works for all 20 tools automatically
- No need to rebuild menus when tools change

### Implementation Status

1. ✅ **ToolsMenuManager** - Simplified to single Adjust command
2. ✅ **OutputView Integration** - `_toggle_inspector()` method already exists
3. ✅ **Command Registration** - Commands added to app.commands
4. ✅ **Inspector Panel** - Right sidebar with JSON editor implemented

### Current Menu Structure

```
Tools
├── Adjust Current Tool... (⌘⇧I)  ← Toggles inspector for current step
├── ──────
├── Go To Original Image            ← Navigate to step 0
└── Rotate Image...                 ← Process with rotate (placeholder)
```

**How It Works**:
1. User views any tool step (crop, rotate, enhance, etc.)
2. Menu > Tools > Adjust Current Tool... (or ⌘⇧I)
3. Inspector panel slides in from right with JSON editor
4. Shows editable parameters from current step's renderer
5. User edits parameters and saves
6. Renderer applies changes via `apply_json_edits()`

## Next Steps

### Immediate
1. ✅ **Test in GUI** - Menu appears and commands visible
2. ✅ **Test inspector toggle** - Inspector opens/closes correctly
3. ✅ **Added manifest file loading** - Loads from `{file_path parent}/assets/{tool_name}d/{tool_name}_manifest.jsonl`
4. ✅ **Fixed path duplication bug** - Correctly navigates up two parent levels
5. ✅ **Implemented generic data approach** - Returns entire manifest_entry without custom extraction
6. 🔄 **READY FOR FINAL TESTING** - Restart app and verify complete crop JSON appears in inspector
7. ⏳ **Wire up Go To for all steps** - Dynamic step menu items
8. ⏳ **Implement Process dialog** - Actual tool execution UI

### Short-term (all tools)
1. ⏳ Add Adjust commands for all 20 renderers
2. ⏳ Add Process commands for all tools
3. ⏳ Organize Process menu by category (Image/AI/Documents/Metadata)
4. ⏳ Add keyboard shortcuts (Cmd+Shift+Letter, etc.)

### Long-term (enhancements)
1. ⏳ Bold text for current step on Mac (when Toga supports it)
2. ⏳ Rebuild Go To menu dynamically when item changes
3. ⏳ Renderer-specific toolbar actions
4. ⏳ Before/after comparison for enhancement tools

## Architecture Benefits

✅ **Consistent with Fichero's command system** - Uses existing Toga Commands
✅ **Extensible** - Easy to add new tools via renderer registry
✅ **Context-aware** - Menu items enable/disable based on state
✅ **Testable** - Can test without full GUI (unit tests for handlers)
✅ **Well-documented** - Clear separation of concerns

## Related Documentation

- `TOOLS_MENU_IMPLEMENTATION_PLAN.md` - Complete specification
- `ALL_RENDERERS_COMPLETE.md` - All 20 renderers implemented
- `ROTATE_RENDERER_TEST_PLAN.md` - Testing rotate renderer
- `Rotate.yml` - Workflow plan for testing

## Notes

- **Toga Version**: 0.5.2 (command system)
- **Platform**: macOS (Cocoa backend)
- **Focus Tool**: Rotate (testing framework before expanding to all 20 tools)
- **Menu Style**: Mac uses system menubar, not checkmarks (bold for current, when supported)
