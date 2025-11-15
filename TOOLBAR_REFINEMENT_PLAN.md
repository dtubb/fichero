# Toolbar Refinement Plan

## Overview
Refine the LibraryView toolbar to match the existing menu structure and improve layout organization.

---

## Task 1: Fix Import Menu Items
**Goal:** Import dropdown menu should use the same commands as File > Import menu (not create duplicates)

**Current State:**
- Import menu has hardcoded menu items in LibraryView
- File menu likely has separate import commands defined
- Duplicate command definitions = maintenance problem

**Target State:**
- Import toolbar button references existing File > Import commands
- Single source of truth for import actions
- Menu items pulled from command registry

**Changes Needed:**
1. Find existing File > Import menu commands
2. Update Import toolbar button to reference those commands (not recreate them)
3. Remove duplicate action methods if they exist elsewhere

---

## Task 2: Fix Toolbar Layout & Organization
**Goal:** Reorganize toolbar items with proper grouping and spacing

**Current Layout:**
```
[Library] [Collection] [Adjust] [Import] [FlexSpace]
```

**Target Layout:**
```
[Collection] [FlexSpace] [New Collection | Import] [FlexSpace] [Adjust]
                          └─ NSToolbarItemGroup ─┘
```

**Layout Requirements:**
1. **Collection toggle** - Far left (navigational=True)
2. **Flexible space** - After Collection
3. **Action group** - Center (NSToolbarItemGroup)
   - New Collection button
   - Import dropdown menu
4. **Flexible space** - After action group
5. **Adjust toggle** - Far right

**Changes Needed:**
1. Remove Library button from toolbar (or clarify its purpose vs Collection)
2. Move Collection to leftmost position
3. Create NSToolbarItemGroup for New Collection + Import
4. Add flexible spaces for proper positioning
5. Move Adjust to rightmost position

---

## Implementation Phases

### Phase 1: Fix Import Menu Items
**Agent 1 - Implementation:**
- Search for existing File > Import menu commands
- Identify command IDs and structure
- Update Import toolbar button to reference existing commands
- Remove duplicate definitions

**Agent 2 - Review:**
- Verify import commands are properly referenced
- Check no duplicate command definitions
- Confirm menu items match File menu

**Agent 3 - Revision:**
- Fix any issues found in review
- Ensure single source of truth for import commands

---

### Phase 2: Fix Toolbar Layout
**Agent 1 - Implementation:**
- Update toolbar layout order in MacToolbarManager
- Create NSToolbarItemGroup for New Collection + Import
- Add flexible spaces for positioning
- Update Collection button with navigational=True
- Position Adjust button on far right

**Agent 2 - Review:**
- Verify toolbar layout matches target
- Check NSToolbarItemGroup creation
- Confirm flexible spaces work correctly
- Verify Collection is navigational

**Agent 3 - Revision:**
- Fix any layout issues
- Adjust visibility priorities if needed
- Ensure proper spacing and grouping

---

## Success Criteria

### Import Menu Items
- ✅ Import menu items reference existing File > Import commands
- ✅ No duplicate command definitions
- ✅ Single source of truth for import actions
- ✅ Menu items match File > Import menu exactly

### Toolbar Layout
- ✅ Collection toggle on far left (navigational=True)
- ✅ New Collection + Import in center group (NSToolbarItemGroup)
- ✅ Adjust toggle on far right
- ✅ Flexible spaces create proper spacing
- ✅ Toolbar is customizable and items movable
- ✅ Layout matches ULTIMATE demo quality

---

## Files to Modify

### Phase 1 (Import Menu):
- `src/fichero/windows/main/views/library/library_view.py` - Update Import command definition
- Possibly other files with File menu commands

### Phase 2 (Toolbar Layout):
- `src/fichero/shared/commands/mac_toolbar_manager.py` - Update toolbar layout
- `src/fichero/windows/main/views/library/library_view.py` - Update command definitions
- `src/fichero/windows/main/main_window.py` - Update Collection/Adjust button properties

---

## Execution Order

1. **Phase 1a:** Agent to implement Import menu fix
2. **Phase 1b:** Agent to review Import menu fix
3. **Phase 1c:** Agent to revise Import menu (if needed)
4. **Phase 2a:** Agent to implement toolbar layout
5. **Phase 2b:** Agent to review toolbar layout
6. **Phase 2c:** Agent to revise toolbar layout (if needed)

---

## Notes

- Each phase is independent - Phase 1 can complete before Phase 2 starts
- Review agents will create reports in markdown
- Revision agents will fix issues found by review agents
- All changes must maintain backward compatibility
- Test after each phase to ensure no breakage
