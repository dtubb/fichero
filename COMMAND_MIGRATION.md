# OutputView Command Migration - Old vs New

## Summary
Documenting all commands from the old output_view.py to ensure nothing is lost in the Phase 4 refactoring.

## OLD SYSTEM Commands (output_view.py)

### TOOLS MENU - Image Edit Commands (context='edit')
**All showed in bottom toolbar in edit mode:**

1. **rotate_left** - ⌘L
   - Group: tools_group (order=50)
   - Section: 0, Order: 0
   - Icon: rotate.left@10x.png
   - Toolbar: left position, "Rotate\nLeft"
   - Context: 'edit' (only in edit mode)

2. **rotate_right** - ⌘R
   - Group: tools_group
   - Section: 0, Order: 1
   - Icon: rotate.right@10x.png
   - Toolbar: left position, "Rotate\nRight"
   - Context: 'edit'

3. **crop** - ⌘K
   - Group: tools_group
   - Section: 0, Order: 2
   - Icon: crop.png
   - Toolbar: left position, "Crop"
   - Context: 'edit'

4. **reset** - ⌘0
   - Group: tools_group
   - Section: 0, Order: 3
   - Icon: arrow.up.left.and.arrow.down.right@10x.png
   - Toolbar: left position, "Reset"
   - Context: 'edit'

### VIEW MENU - Zoom Commands (context='normal')

5. **zoom_in** - ⌘+
   - Group: toga.Group.VIEW
   - Section: 0, Order: 0

6. **zoom_out** - ⌘-
   - Group: toga.Group.VIEW
   - Section: 0, Order: 1

7. **zoom_fit** - ⌘9
   - Group: toga.Group.VIEW
   - Section: 0, Order: 2

8. **actual_size** - ⌘0
   - Group: toga.Group.VIEW
   - Section: 0, Order: 3

9. **fit_width** - ⌘⇧0
   - Group: toga.Group.VIEW
   - Section: 0, Order: 4

10. **fit_height** - ⌘⇧9
    - Group: toga.Group.VIEW
    - Section: 0, Order: 5

11. **zoom_selection** - ⌘⇧8
    - Group: toga.Group.VIEW
    - Section: 0, Order: 6

### GO MENU - Navigation Commands (context='normal')

12. **prev_step** - ⌘←
    - Group: go_group (order=40)
    - Section: 0, Order: 0

13. **next_step** - ⌘→
    - Group: go_group
    - Section: 0, Order: 1

14. **prev_file** - ⌘↑
    - Group: go_group
    - Section: 1, Order: 0

15. **next_file** - ⌘↓
    - Group: go_group
    - Section: 1, Order: 1

### MOBILE TOOLBAR - Inspector Button

16. **show_inspector** - No shortcut
    - Show in top toolbar (mobile only)
    - Icon: info.circle@10x.png
    - Position: right, Order: 99
    - Mobile only, context='normal'

---

## NEW SYSTEM Commands (output_view_refactored.py)

### Currently Implemented:

1. **zoom_in** - ⌘+ ✅
2. **zoom_out** - ⌘- ✅
3. **zoom_fit** - ⌘9 ✅
4. **actual_size** - ⌘0 ✅
5. **prev_step** - ⌘← ✅
6. **next_step** - ⌘→ ✅
7. **prev_file** - ⌘↑ ✅
8. **next_file** - ⌘↓ ✅

### MISSING Commands (Need to Add):

✅ **rotate_left** - ⌘L (Tools menu, edit mode) - ADDED
✅ **rotate_right** - ⌘R (Tools menu, edit mode) - ADDED
✅ **crop** - ⌘K (Tools menu, edit mode) - ADDED (handler TODO: implement crop UI)
✅ **reset** - ⌘⇧R (Tools menu, edit mode) - ADDED (shortcut changed to avoid conflict)
✅ **fit_width** - ⌘⇧0 (View menu) - ADDED
✅ **fit_height** - ⌘⇧9 (View menu) - ADDED (handler TODO: implement fit_height calculation)
✅ **zoom_selection** - ⌘⇧8 (View menu) - ADDED (handler TODO: implement selection UI)
✅ **show_inspector** - Mobile top toolbar - ADDED

---

## KEY DIFFERENCES

### Menu Groups
- **Old**: Custom groups `go_group` (order=40), `tools_group` (order=50)
- **New**: Only using toga.Group.VIEW for zoom commands

### Toolbar Context System
- **Old**: Uses `context='edit'` vs `context='normal'` to show different toolbar buttons
- **New**: No context switching implemented yet

### Keyboard Shortcut CONFLICT
- **OLD**:
  - `⌘0` = "Reset to Original" (Tools menu, edit context)
  - But also has "Actual Size" command
- **NEW**:
  - `⌘0` = "Actual Size" (View menu)

**Resolution needed**: Change reset shortcut or make context-aware

### Mobile Features
- **Old**: `show_inspector` button in mobile top toolbar
- **New**: Inspector toggle exists but not exposed in toolbar

---

## ACTION PLAN

1. ✅ **DONE** - Add missing zoom commands (fit_width, fit_height, zoom_selection)
2. ✅ **DONE** - Add Tools menu group (order=50)
3. ✅ **DONE** - Add image edit commands (rotate_left, rotate_right, crop, reset)
4. ✅ **DONE** - Resolve ⌘0 shortcut conflict (changed reset to ⌘⇧R)
5. ✅ **DONE** - Add mobile inspector button
6. ⏳ **TODO** - Implement context switching for edit mode toolbar (commands defined, need UI support)
7. ⚠️ **PARTIAL** - Wire up rotation/crop handlers to OutputPane methods:
   - ✅ rotate_left, rotate_right, reset - WORKING (use existing OutputPane methods)
   - ⏳ crop, fit_height, zoom_selection - Need UI implementation in OutputPane

## MIGRATION STATUS

**Commands Added: 16/16** ✅

All commands from the old system have been added to the refactored output_view_refactored.py!

**Next Steps:**
- Implement crop UI in OutputPane
- Implement fit_height calculation in OutputPane
- Implement zoom_selection with selection UI in OutputPane
- Add context switching support to show/hide edit mode toolbar buttons
