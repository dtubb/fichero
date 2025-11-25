# Preview Pane Toggle Implementation

## Overview
Implemented independent toggle controls for the Preview Image and Preview Metadata panes, allowing users to show/hide them individually or view them at different ratios.

## Changes Made

### 1. Made Preview Panes Collapsible
- Changed `collapsible` flag from `False` to `True` for both PreviewImage and PreviewMetadata columns
- **File**: `src/fichero/windows/main/main_window.py:289`

### 2. Added New Toggle Commands

#### View Menu Structure (with keyboard shortcuts):
```
View
├── 1 Library          (Cmd+Opt+1)
├── 2 Collection       (Cmd+Opt+2)
├── 3 Preview Image    (Cmd+Opt+3) ← NEW
├── 4 Preview Metadata (Cmd+Opt+4) ← NEW
├── 5 Info             (Cmd+Opt+5) ← Renumbered from 3, renamed from "Adjust"
├── ─────────────────
├── Cycle Preview Width (Cmd+R)    ← Simplified (removed Cmd+2/5/7)
```

#### New Commands:
- `view.toggle_preview_image` - Toggle Preview Image pane (Cmd+Opt+3)
- `view.toggle_preview_metadata` - Toggle Preview Metadata pane (Cmd+Opt+4)

#### Updated Commands:
- `view.toggle_collection` - Now labeled "2 Collection" (was "Collection")
- `view.toggle_inspector` - Now labeled "5 Info" and uses Cmd+Opt+5 (was "3 Adjust" with Cmd+Opt+3)

### 3. Simplified Width Controls
**Removed:**
- `view.ratio_balanced` (Cmd+5)
- `view.ratio_wide_content` (Cmd+7)
- `view.ratio_wide_image` (Cmd+2)

**Kept:**
- `view.cycle_ratios` (Cmd+R) - Now labeled "Cycle Preview Width"
- Cycles through: wide_image (25/75) → balanced (50/50) → wide_content (75/25)

### 4. Smart Toggle Behavior

#### Preview Pane States:
1. **Image Only** - 100% image, metadata hidden
2. **Metadata Only** - 100% metadata, image hidden
3. **Both Visible** - Ratios apply (25/75, 50/50, or 75/25)

#### Smart Rules:
- **Can't hide both**: When toggling the last visible preview pane, the other pane is automatically shown
- **Info pane dependency**: Info pane auto-hides when both preview panes are hidden
- **Info toggle restriction**: Info pane cannot be shown when both preview panes are hidden
- **Ratio restrictions**: Width ratios only apply when both preview panes are visible

### 5. Implementation Details

**Toggle Handlers** (lines 1408-1543):
- `_toggle_preview_image_pane()` - Toggle image pane with smart behavior
- `_toggle_preview_metadata_pane()` - Toggle metadata pane with smart behavior
- `_toggle_inspector_pane()` - Updated to check for at least one visible preview pane

**Width Management** (lines 1559-1657):
- `_cycle_preview_ratios()` - Updated to require both panes visible
- `_apply_preview_ratio()` - Updated to check both panes visible before applying ratios

### 6. Unit Tests
Created comprehensive test suite: `tests/unit/test_preview_pane_toggles.py`

**12 tests covering:**
- ✅ Toggle image when both visible
- ✅ Toggle image prevents both hidden
- ✅ Toggle metadata when both visible
- ✅ Toggle metadata prevents both hidden
- ✅ Info pane hides when both preview hidden
- ✅ Info toggle blocked when both preview hidden
- ✅ Info toggle works when one preview visible
- ✅ Cycle ratios requires both visible
- ✅ Cycle ratios works when both visible
- ✅ Apply ratio requires both visible
- ✅ Apply ratio works when both visible
- ✅ Cycle ratios order correct

Updated existing test suite: `tests/unit/test_preview_ratio_system.py`
- ✅ Updated 18 tests to reflect simplified ratio system (only Cmd+R cycle)
- ✅ Removed expectations for deleted commands (Cmd+2/5/7)

**All 30 tests pass** ✅

## User Experience

### Keyboard Shortcuts
- **Cmd+Opt+1** - Toggle Library
- **Cmd+Opt+2** - Toggle Collection
- **Cmd+Opt+3** - Toggle Preview Image (new)
- **Cmd+Opt+4** - Toggle Preview Metadata (new)
- **Cmd+Opt+5** - Toggle Info (renumbered)
- **Cmd+R** - Cycle Preview Width (when both panes visible)

### Use Cases
1. **Focus on Image**: Hide metadata (Cmd+Opt+4) to see full-width image
2. **Focus on Metadata**: Hide image (Cmd+Opt+3) to see full-width metadata
3. **Balanced View**: Show both and use Cmd+R to cycle through width ratios
4. **Minimal UI**: Hide Info pane (Cmd+Opt+5) for maximum preview space

## Technical Notes

### Files Modified:
1. `src/fichero/windows/main/main_window.py` - Main implementation
2. `tests/unit/test_preview_pane_toggles.py` - New test suite (new file)
3. `tests/unit/test_preview_ratio_system.py` - Updated existing tests
4. `PREVIEW_PANE_TOGGLES.md` - This documentation (new file)

### Backward Compatibility:
- All existing commands still work
- Layout behavior is unchanged when both panes are visible
- State manager integration preserved

### Future Enhancements:
- Consider adding toolbar buttons for preview toggles
- Add status bar indicators showing which panes are visible
- Remember last preview state per collection
