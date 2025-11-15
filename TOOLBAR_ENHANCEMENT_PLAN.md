# Toolbar Enhancement Plan

## Goal
Test Fichero's declarative toolbar system by adding advanced NSToolbar features:
- Import button with dropdown submenu (replacing individual import buttons)
- Search field
- Button groups
- Flexible space dividers

## Current State
- ✅ Basic buttons working (Library, Collection, Adjust)
- ✅ `navigational=True` property working
- ✅ MacToolbarManager supports all NSToolbar item types
- ⚠️ No real-world usage of advanced features yet

## Proposed Changes

### 1. Import Dropdown Menu Button
**Replace:** Individual import buttons scattered in menus
**With:** Single "Import" toolbar button with dropdown menu

**Location:** LibraryView toolbar
**Menu Items:**
- Import Folder
- Import Files
- Import from Scanner
- Import from Camera

**Configuration:**
```python
FicheroCommand(
    id='library.import',
    label='Import',
    item_type='menu',  # Creates NSMenuToolbarItem
    menu_items=[
        {'label': 'Folder...', 'action': self._on_import_folder, 'icon': 'folder'},
        {'label': 'Files...', 'action': self._on_import_files, 'icon': 'doc'},
        {'label': 'Scanner...', 'action': self._on_import_scanner, 'icon': 'scanner'},
        {'label': 'Camera...', 'action': self._on_import_camera, 'icon': 'camera'},
    ],
    toolbar_icon='square.and.arrow.down',
    show_in_top_toolbar=True,
    visibility_priority=800,
    shows_menu_indicator=True,
    tooltip='Import files or folders'
)
```

### 2. Search Field (Optional - for testing)
**Purpose:** Test NSSearchToolbarItem implementation
**Location:** MainWindow toolbar (if we want global search)

**Configuration:**
```python
FicheroCommand(
    id='main.search',
    label='Search',
    item_type='search',
    search_placeholder='Search collections...',
    search_action=self._on_search,
    show_in_top_toolbar=True,
    visibility_priority=900
)
```

### 3. Flexible Space
**Purpose:** Push items to right side of toolbar
**Already working:** In `toolbarDefaultItemIdentifiers_()` layout array

### 4. Button Group (Optional - for testing)
**Purpose:** Test NSToolbarItemGroup implementation
**Example:** Group view mode buttons together

## Implementation Steps

### Phase 1: Add Import Menu Button
1. Add `_on_import_*` action methods to LibraryView
2. Define import menu command in LibraryView.define_commands()
3. Update toolbar layout to include import button
4. Test menu appears and actions fire

### Phase 2: Test Advanced Features (Optional)
1. Add search field to test NSSearchToolbarItem
2. Add button group to test NSToolbarItemGroup
3. Verify all features work correctly

### Phase 3: Review & Cleanup
1. Review implementation with agent
2. Fix any issues found
3. Remove test features (search, button group) if not needed
4. Keep import menu button if useful

## Files to Modify

### Primary Changes
- `src/fichero/views/library/library_view.py` - Add import command and actions
- `src/fichero/shared/commands/mac_toolbar_manager.py` - Verify menu item creation works

### Testing
- Verify menu dropdown appears
- Verify menu items trigger correct actions
- Verify icon appears on toolbar button
- Verify menu items have icons
- Verify button can be moved/customized

## Success Criteria
- ✅ Import button appears in toolbar
- ✅ Clicking button shows dropdown menu
- ✅ Menu items have correct labels and icons
- ✅ Clicking menu items triggers correct actions
- ✅ Button is movable/customizable
- ✅ No errors or crashes
- ✅ Matches ULTIMATE demo quality

## Rollback Plan
If issues arise:
1. Comment out the import command definition
2. Remove from toolbar layout
3. Original functionality remains intact
