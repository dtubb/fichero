# NSToolbar Feature Inventory & FicheroCommand Gap Analysis

**Generated**: 2025-11-15
**Scope**: Complete analysis of NSToolbar features across demo files and current FicheroCommand implementation

---

## Executive Summary

This document inventories ALL NSToolbar features demonstrated in two demo files and compares them against the current `FicheroCommand` class to identify implementation gaps.

**Files Analyzed**:
1. `/Users/dtubb/code/fichero_main/fichero/ULTIMATE_TOOLBAR_DEMO.py` - Ultimate NSToolbar demo
2. `/Users/dtubb/code/fichero_main/fichero/FICHERO_COMMAND_TOOLBAR_DEMO.py` - FicheroCommand-based demo
3. `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/commands/command.py` - Current FicheroCommand class

---

## 1. NSToolbar Item Types

### 1.1 Regular Button Items (NSToolbarItem)

**ULTIMATE_TOOLBAR_DEMO.py** demonstrates:
- ✅ Basic button with label and icon
- ✅ Action handler via `setTarget_()` and `setAction_()`
- ✅ Tooltips via `setToolTip()`
- ✅ Enable/disable state via `setEnabled_()`
- ✅ Label vs paletteLabel distinction
- ✅ Bordered property (`bordered = True`)

**FICHERO_COMMAND_TOOLBAR_DEMO.py** demonstrates:
- ✅ Button items with PNG icons from files
- ✅ Button items with SF Symbols
- ✅ Mixed icon sources (PNG + SF Symbols)
- ✅ Visibility priority settings
- ✅ Generic action handler pattern

**FicheroCommand Support**:
- ✅ **SUPPORTED**: Basic button functionality
- ✅ **SUPPORTED**: Action handlers (via `action` parameter)
- ✅ **SUPPORTED**: Icons (via `icon` parameter)
- ✅ **SUPPORTED**: Labels (via `label` parameter)
- ✅ **SUPPORTED**: Enable/disable (via `enabled` property)
- ✅ **SUPPORTED**: Toolbar text (via `toolbar_text` parameter)
- ✅ **SUPPORTED**: Visibility priority (via `visibility_priority` parameter, default 500)
- ✅ **SUPPORTED**: Bordered property (via `toolbar_bordered` parameter, default True)
- ❌ **NOT SUPPORTED**: Separate paletteLabel (different label for customization palette)
- ❌ **NOT SUPPORTED**: Tooltips (no `tooltip` parameter)

---

### 1.2 Search Items (NSSearchToolbarItem)

**ULTIMATE_TOOLBAR_DEMO.py** demonstrates:
```python
search_item = NSSearchToolbarItem.alloc().initWithItemIdentifier("search.bar")
search_item.setLabel("Search")
search_item.setPaletteLabel("Search")
search_item.setToolTip("Search everything")
search_item.visibilityPriority = 1000  # High priority
search_field = search_item.searchField
search_field.placeholderString = "Search..."
search_field.setTarget_(delegate)
search_field.setAction_(SEL("handleSearch:"))
```

**FICHERO_COMMAND_TOOLBAR_DEMO.py** demonstrates:
```python
FicheroCommand(
    id="demo.search",
    label="Search",
    item_type="search",
    visibility_priority=1000,
    show_in_toolbar=True
)
```

**FicheroCommand Support**:
- 🔄 **PARTIALLY SUPPORTED**: `item_type` parameter exists but not documented in `__init__`
- ❌ **NOT SUPPORTED**: Placeholder text configuration
- ❌ **NOT SUPPORTED**: Search field action handlers
- ❌ **NOT SUPPORTED**: Search-specific properties

**Gap**: No `item_type` parameter in FicheroCommand `__init__`, but used in demo. Need to add and document.

---

### 1.3 Menu Dropdown Items (NSMenuToolbarItem)

**ULTIMATE_TOOLBAR_DEMO.py** demonstrates:
```python
view_menu = NSMenuToolbarItem.alloc().initWithItemIdentifier("view.dropdown")
view_menu.setLabel("View")
view_menu.setPaletteLabel("View Options")
view_menu.setToolTip("Change view mode")
view_menu.showsIndicator = True  # Show dropdown arrow
view_menu.isBordered = True
view_menu.visibilityPriority = 600
view_menu.setImage(view_icon)

menu = NSMenu.alloc().initWithTitle("View")
# Add menu items...
view_menu.menu = menu
```

**FICHERO_COMMAND_TOOLBAR_DEMO.py** demonstrates:
```python
FicheroCommand(
    id="demo.view",
    label="View",
    icon="src/fichero/resources/icons/toolbar/square.grid.2x2@10x.png",
    item_type="menu",
    menu_items=["Thumbnails", "List", "Columns", "Gallery"],
    visibility_priority=700,
    show_in_toolbar=True
)
```

**FicheroCommand Support**:
- 🔄 **PARTIALLY SUPPORTED**: `item_type="menu"` exists (not in `__init__`)
- 🔄 **PARTIALLY SUPPORTED**: `menu_items` parameter exists (not in `__init__`)
- ❌ **NOT SUPPORTED**: `showsIndicator` property (show/hide dropdown arrow)
- ❌ **NOT SUPPORTED**: Menu item configuration beyond labels
- ❌ **NOT SUPPORTED**: Menu item actions/handlers
- ❌ **NOT SUPPORTED**: Menu item icons
- ❌ **NOT SUPPORTED**: Submenu support

**Gap**: `item_type` and `menu_items` used in demo but not in `FicheroCommand.__init__()` signature.

---

### 1.4 Group Items (NSToolbarItemGroup)

**ULTIMATE_TOOLBAR_DEMO.py** demonstrates:
```python
# Create subitems
inbox_subitem = NSToolbarItem.alloc().initWithItemIdentifier("inbox.subitem")
inbox_subitem.setImage(inbox_icon)
inbox_subitem.setLabel("Inbox")
inbox_subitem.setToolTip("View inbox")

# Create group
inbox_group = NSToolbarItemGroup.alloc().initWithItemIdentifier("inbox.group")
inbox_group.setSubitems([inbox_subitem, archive_subitem, trash_subitem])
inbox_group.setLabel("Mail")
inbox_group.setPaletteLabel("Mail Actions")
inbox_group.setToolTip("Mail management")
inbox_group.visibilityPriority = 900

# Set badge (macOS 14+)
badge = NSItemBadge.alloc().initWithCount_(5)
inbox_group.badge = badge
```

**FICHERO_COMMAND_TOOLBAR_DEMO.py** demonstrates:
```python
FicheroCommand(
    id="demo.actions.group",
    label="Actions",
    item_type="group",
    visibility_priority=850,
    subitems=[
        {"id": "duplicate", "label": "Duplicate", "icon": "src/fichero/resources/icons/toolbar/duplicate.png"},
        {"id": "rename", "label": "Rename", "icon": "src/fichero/resources/icons/toolbar/rename.png"},
        {"id": "trash", "label": "Trash", "icon": "src/fichero/resources/icons/toolbar/trash.png"},
    ],
    show_in_toolbar=True
)
```

**FicheroCommand Support**:
- 🔄 **PARTIALLY SUPPORTED**: `item_type="group"` exists (not in `__init__`)
- 🔄 **PARTIALLY SUPPORTED**: `subitems` parameter exists (not in `__init__`)
- ❌ **NOT SUPPORTED**: Subitem configuration (tooltips, actions, etc.)
- ❌ **NOT SUPPORTED**: Badge support (macOS 14+)
- ❌ **NOT SUPPORTED**: Group-level tooltip

**Gap**: `item_type` and `subitems` used in demo but not in `FicheroCommand.__init__()` signature.

---

### 1.5 Tracking Separator Items (NSTrackingSeparatorToolbarItem)

**ULTIMATE_TOOLBAR_DEMO.py** demonstrates:
```python
separator = NSTrackingSeparatorToolbarItem.alloc().initWithItemIdentifier_("separator.tracking")
separator.splitView = native_split  # Link to NSSplitView
separator.dividerIndex = 0  # Track first divider
```

**FICHERO_COMMAND_TOOLBAR_DEMO.py** demonstrates:
```python
FicheroCommand(
    id="separator.tracking",
    label="",
    item_type="separator",
    ...
)
```

**FicheroCommand Support**:
- 🔄 **PARTIALLY SUPPORTED**: `item_type="separator"` exists (not in `__init__`)
- ❌ **NOT SUPPORTED**: splitView binding
- ❌ **NOT SUPPORTED**: dividerIndex configuration

**Gap**: `item_type` used in demo but not in `FicheroCommand.__init__()` signature.

---

### 1.6 Space Items (Flexible/Fixed)

**ULTIMATE_TOOLBAR_DEMO.py** demonstrates:
```python
# In toolbarDefaultItemIdentifiers_:
default_ids = [
    "search.bar",
    "NSToolbarFlexibleSpaceItem",  # Flexible space
    "inbox.group",
    ...
]

# In toolbarAllowedItemIdentifiers_:
allowed_ids = list(self.toolbar_items.keys()) + [
    "NSToolbarSpaceItem",           # Fixed space
    "NSToolbarFlexibleSpaceItem",   # Flexible space
]
```

**FICHERO_COMMAND_TOOLBAR_DEMO.py** demonstrates:
- Same pattern - flexible/fixed spaces added to default/allowed item lists

**FicheroCommand Support**:
- ❌ **NOT SUPPORTED**: No concept of flexible/fixed space items
- ❌ **NOT SUPPORTED**: No way to specify space items in toolbar layout

**Gap**: Space items are system-provided, not command-based. Need layout system.

---

## 2. Item Properties

### 2.1 Labels

**Properties Demonstrated**:
- `setLabel()` - Label shown in toolbar
- `setPaletteLabel()` - Label shown in customization palette (can be different)
- Multi-line toolbar text (e.g., "Rotate\nLeft")

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `label` parameter
- ✅ **SUPPORTED**: `toolbar_text` parameter (for different toolbar display)
- ❌ **NOT SUPPORTED**: Separate paletteLabel
- ✅ **SUPPORTED**: Multi-line text via `toolbar_text` with `\n`

---

### 2.2 Icons

**Icon Types Demonstrated**:
1. **SF Symbols** (system icons):
   ```python
   NSImage.imageWithSystemSymbolName_accessibilityDescription_("house.fill", "Home")
   ```

2. **PNG Files** (custom icons):
   ```python
   NSImage.alloc().initWithContentsOfFile(at("/path/to/icon.png"))
   image.setSize(NSSize(32, 32))  # Resize to toolbar size
   ```

3. **Mixed usage** in same toolbar

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `icon` parameter (file path or SF Symbol name)
- ✅ **SUPPORTED**: `toolbar_icon` parameter specifically for SF Symbols (macOS NSToolbar)
- ❌ **NOT SUPPORTED**: Icon size configuration
- ❌ **NOT SUPPORTED**: Multiple icon types (light/dark mode variants)

---

### 2.3 Enabled/Disabled State

**Demonstrated**:
```python
# Dynamic state management
for item_id, item in self.toolbar_items.items():
    if hasattr(item, 'setEnabled_'):
        item.setEnabled_(self.items_enabled)
```

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `enabled` property
- ✅ **SUPPORTED**: `enable()` and `disable()` methods
- ✅ **SUPPORTED**: Syncs with toga.Command if registered

---

### 2.4 Visibility Priority

**Demonstrated**:
```python
search_item.visibilityPriority = 1000  # High priority - stays visible
settings_item.visibilityPriority = 100  # Low priority - overflows first
```

**How it works**: When window is narrow, items with lower priority move to overflow menu first.

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `visibility_priority` parameter (default 500)
- ✅ **DOCUMENTED**: Range 0-1000, higher stays visible when window narrow

---

### 2.5 Bordered vs Borderless

**Demonstrated**:
```python
starred_item.bordered = True  # Show border/hover effect
view_menu.isBordered = False  # No border
```

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `toolbar_bordered` parameter (default True)

---

### 2.6 Navigational Style

**Demonstrated**:
```python
home_item.navigational = True  # Navigation item styling (macOS 11+)
```

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `navigational` parameter (default False)
- ✅ **DOCUMENTED**: macOS 11+ feature

---

### 2.7 Prominent Style with Tint Colors

**Demonstrated**:
```python
# Style: 0=plain, 1=prominent
starred_item.style = 1
# Custom tint color
orange_color = NSColor.orangeColor()
starred_item.backgroundTintColor = orange_color
```

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `toolbar_style` parameter ("plain" or "prominent", default "plain")
- ✅ **SUPPORTED**: `toolbar_tint_color` parameter (hex string, e.g., "#FF6B35")

---

### 2.8 Badge Counts (macOS 14+)

**Demonstrated**:
```python
NSItemBadge = ObjCClass("NSItemBadge")
badge = NSItemBadge.alloc().initWithCount_(5)
inbox_group.badge = badge
```

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `toolbar_badge_count` parameter (integer)
- ✅ **DOCUMENTED**: Requires macOS 14+

---

## 3. Layout & Organization

### 3.1 Item Positioning

**Demonstrated**:
```python
# Layout control via toolbarDefaultItemIdentifiers_:
default_ids = [
    "search.bar",                    # Left side
    "NSToolbarFlexibleSpaceItem",    # Push to right
    "inbox.group",
    "separator.tracking",
    "home.button",
    "starred.button",
    "NSToolbarFlexibleSpaceItem",    # Push to far right
    "view.dropdown",
    "settings.button",
]
```

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `toolbar_position` parameter ('left', 'center', 'right')
- ❌ **NOT SUPPORTED**: Explicit layout ordering system
- ❌ **NOT SUPPORTED**: Flexible/fixed space items
- ❌ **NOT SUPPORTED**: Default vs allowed item lists

**Gap**: No system for defining toolbar layout/ordering.

---

### 3.2 Flexible Space Usage

**Demonstrated**: `"NSToolbarFlexibleSpaceItem"` in default items list

**FicheroCommand Support**:
- ❌ **NOT SUPPORTED**: No concept of flexible space

---

### 3.3 Fixed Space Usage

**Demonstrated**: `"NSToolbarSpaceItem"` in allowed items list

**FicheroCommand Support**:
- ❌ **NOT SUPPORTED**: No concept of fixed space

---

### 3.4 Item Groups

See section 1.4 above.

---

### 3.5 Separators

See section 1.5 above.

---

## 4. Advanced Features

### 4.1 Customization (Drag to Reorder)

**Demonstrated**:
```python
toolbar.setAllowsUserCustomization(True)  # Enable right-click → "Customize Toolbar..."
toolbar.setAutosavesConfiguration(True)   # Save layout between launches
```

**FicheroCommand Support**:
- ❌ **NOT SUPPORTED**: No toolbar-level configuration
- ❌ **NOT SUPPORTED**: No customization enable/disable
- ❌ **NOT SUPPORTED**: No autosave configuration

**Gap**: FicheroCommand is item-level, not toolbar-level. Need ToolbarManager.

---

### 4.2 Autosave Configuration

**Demonstrated**:
```python
toolbar.setAutosavesConfiguration(True)  # Save layout using toolbar identifier
toolbar = NSToolbar.alloc().initWithIdentifier("fichero.ultimate.toolbar")
```

**FicheroCommand Support**:
- ❌ **NOT SUPPORTED**: No toolbar identifier concept
- ❌ **NOT SUPPORTED**: No autosave configuration

**Gap**: Need ToolbarManager to handle toolbar-level config.

---

### 4.3 Default vs Allowed Items

**Demonstrated**:
```python
@objc_method
def toolbarDefaultItemIdentifiers_(self, toolbar):
    """Items shown by default"""
    return at(["search.bar", "NSToolbarFlexibleSpaceItem", "inbox.group", ...])

@objc_method
def toolbarAllowedItemIdentifiers_(self, toolbar):
    """All items available for customization"""
    return at(list(self.toolbar_items.keys()) + ["NSToolbarSpaceItem", ...])
```

**FicheroCommand Support**:
- ❌ **NOT SUPPORTED**: No concept of default vs allowed items
- ❌ **NOT SUPPORTED**: No distinction between "shown by default" and "available to add"

**Gap**: Need layout system to define default/allowed item lists.

---

### 4.4 Selectable Items

**Demonstrated**:
```python
@objc_method
def toolbarSelectableItemIdentifiers_(self, toolbar):
    """Items that can be selected (like tabs)"""
    return at([])  # None in this demo
```

**FicheroCommand Support**:
- ❌ **NOT SUPPORTED**: No concept of selectable items
- ❌ **NOT SUPPORTED**: No selected state tracking

**Gap**: Need to add selectable item support.

---

### 4.5 Validation

**Demonstrated**:
```python
# Dynamic state management via toggle button
def onToggleStates_(self, sender):
    self.items_enabled = not self.items_enabled
    for item_id, item in self.toolbar_items.items():
        if hasattr(item, 'setEnabled_'):
            item.setEnabled_(self.items_enabled)
```

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `enable()` and `disable()` methods
- ❌ **NOT SUPPORTED**: Automatic validation based on app state
- ❌ **NOT SUPPORTED**: Validation callback system

**Gap**: No validation callback mechanism.

---

## 5. Titlebar Accessory Buttons

**FICHERO_COMMAND_TOOLBAR_DEMO.py** demonstrates:
```python
# Sidebar toggle button BEFORE window title
FicheroCommand(
    id="toggleSidebar",
    label="",
    icon="sidebar.left",
    action=lambda w: self.toggle_sidebar(),
    item_type="button",
    show_in_toolbar=True  # Special handling - added as titlebar accessory
)

# Implementation:
button = NSButton.buttonWithImage_target_action_(sidebar_icon, delegate, SEL("handleSidebarToggle:"))
vc = NSTitlebarAccessoryViewController.alloc().init()
vc.view = button
vc.layoutAttribute = 5  # NSLayoutAttributeLeading (left side)
native_window.addTitlebarAccessoryViewController(vc)
```

**FicheroCommand Support**:
- ✅ **SUPPORTED**: `show_in_titlebar` parameter (default False)
- ✅ **SUPPORTED**: `titlebar_position` parameter ("leading" or "trailing", default "leading")
- ✅ **SUPPORTED**: `titlebar_has_menu` parameter (default False)
- ✅ **SUPPORTED**: `titlebar_menu_items` parameter (list of menu item dicts)

**Note**: Titlebar accessories are NOT part of NSToolbar - they're separate `NSTitlebarAccessoryViewController` objects.

---

## 6. Overflow Menu

**Demonstrated**: When window is narrow, items with lower `visibilityPriority` automatically move to overflow menu (≡ button on right side of toolbar).

**FicheroCommand Support**:
- ✅ **SUPPORTED**: Via `visibility_priority` parameter
- ✅ **AUTOMATIC**: macOS handles overflow menu automatically

---

## 7. Display Mode

**Demonstrated**:
```python
toolbar.setDisplayMode(0)  # 0=Icon+Label, 1=Icon only, 2=Label only
```

**FicheroCommand Support**:
- ❌ **NOT SUPPORTED**: No toolbar-level display mode configuration

**Gap**: Need ToolbarManager to handle toolbar-level config.

---

## 8. Centered Item

**FICHERO_COMMAND_TOOLBAR_DEMO.py** demonstrates:
```python
toolbar.centeredItemIdentifier = at("demo.search")
# Creates layout: [toggleSidebar] [Title] [search centered] [other items...]
```

**FicheroCommand Support**:
- ❌ **NOT SUPPORTED**: No concept of centered item

**Gap**: Need ToolbarManager to handle centered item configuration.

---

## Summary of FicheroCommand Gaps

### Critical Gaps (High Priority)

1. **Missing `__init__` Parameters**:
   - ❌ `item_type` - Used in demos but not in constructor signature
   - ❌ `menu_items` - Used in demos but not in constructor signature
   - ❌ `subitems` - Used in demos but not in constructor signature
   - ❌ `tooltip` - Not supported at all

2. **Toolbar-Level Configuration** (need ToolbarManager class):
   - ❌ Customization enable/disable
   - ❌ Autosave configuration
   - ❌ Display mode (icon+label, icon only, label only)
   - ❌ Toolbar identifier
   - ❌ Centered item identifier

3. **Layout System**:
   - ❌ Default item list ordering
   - ❌ Allowed item list (customization palette)
   - ❌ Flexible space items
   - ❌ Fixed space items
   - ❌ Section/divider support

4. **Search Item Properties**:
   - ❌ Placeholder text
   - ❌ Search action handler

5. **Menu Item Properties**:
   - ❌ showsIndicator (dropdown arrow)
   - ❌ Menu item actions/handlers
   - ❌ Menu item icons
   - ❌ Submenu support

6. **Group Item Properties**:
   - ❌ Subitem tooltips
   - ❌ Subitem actions
   - ❌ Group-level tooltip

7. **Tracking Separator Properties**:
   - ❌ splitView binding
   - ❌ dividerIndex configuration

8. **Selectable Items**:
   - ❌ Selectable state (like tabs)
   - ❌ Selected state tracking

9. **Validation System**:
   - ❌ Automatic validation callbacks
   - ❌ App state-based enable/disable

### Medium Priority Gaps

1. **Icon Configuration**:
   - ❌ Icon size control
   - ❌ Light/dark mode variants

2. **Label Configuration**:
   - ❌ Separate paletteLabel

### Features Already Supported ✅

1. **Basic Properties**:
   - ✅ Labels (`label`, `toolbar_text`)
   - ✅ Icons (`icon`, `toolbar_icon`)
   - ✅ Actions (`action`)
   - ✅ Enable/disable (`enabled`, `enable()`, `disable()`)
   - ✅ Visibility priority (`visibility_priority`)
   - ✅ Bordered property (`toolbar_bordered`)

2. **macOS-Specific Styling**:
   - ✅ Navigational style (`navigational`)
   - ✅ Prominent style (`toolbar_style`)
   - ✅ Tint colors (`toolbar_tint_color`)
   - ✅ Badge counts (`toolbar_badge_count`)

3. **Titlebar Accessories**:
   - ✅ Show in titlebar (`show_in_titlebar`)
   - ✅ Titlebar position (`titlebar_position`)
   - ✅ Titlebar menu (`titlebar_has_menu`, `titlebar_menu_items`)

4. **Platform Adaptation**:
   - ✅ Mobile/desktop flags (`mobile_only`, `desktop_only`)
   - ✅ Multiple toolbar placement (`show_in_top_toolbar`, `show_in_bottom_toolbar`)
   - ✅ Toolbar position (`toolbar_position`)
   - ✅ Context support (`context`)

---

## Recommendations

### Immediate Actions

1. **Fix `FicheroCommand.__init__()` signature**:
   - Add `item_type` parameter (default "button")
   - Add `menu_items` parameter (default None)
   - Add `subitems` parameter (default None)
   - Add `tooltip` parameter (default None)
   - Add `palette_label` parameter (default None)
   - Add `search_placeholder` parameter (default None)

2. **Create `ToolbarManager` class** to handle:
   - Toolbar-level configuration (customization, autosave, display mode)
   - Default/allowed item lists and ordering
   - Flexible/fixed space item insertion
   - Centered item configuration
   - Toolbar identifier management

3. **Create `ToolbarLayout` class** to define:
   - Default item ordering
   - Allowed items for customization
   - Space item placement
   - Section/divider placement

### Future Enhancements

1. **Enhanced Menu Support**:
   - Menu item configuration objects
   - Menu item icons
   - Submenu support
   - Menu item actions/handlers

2. **Enhanced Group Support**:
   - Subitem configuration objects
   - Subitem tooltips and actions
   - Group-level tooltips

3. **Validation System**:
   - Validation callback registration
   - Automatic state-based enable/disable

4. **Selectable Items**:
   - Selectable state flag
   - Selection change callbacks
   - Tab-like behavior support

---

## File Reference

**Analyzed Files**:
- `/Users/dtubb/code/fichero_main/fichero/ULTIMATE_TOOLBAR_DEMO.py`
- `/Users/dtubb/code/fichero_main/fichero/FICHERO_COMMAND_TOOLBAR_DEMO.py`
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/commands/command.py`

**Feature Count**:
- Total NSToolbar features demonstrated: 45+
- FicheroCommand features supported: 20
- FicheroCommand features partially supported: 5
- FicheroCommand features not supported: 20+

---

*End of Report*
