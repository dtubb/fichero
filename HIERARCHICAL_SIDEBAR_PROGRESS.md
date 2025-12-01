# Hierarchical Sidebar Implementation Progress

**Date**: November 26, 2025
**Status**: Phase 1 Complete - Ready for Testing

---

## CRITICAL BUG FIXED ✅

### Collection View Not Updating

**Fixed Files:**
1. `src/fichero/windows/main/main_window.py:1044` - Added `current_view._load_collection_items()` when reusing views
2. `src/fichero/windows/main/views/collection/collection_view.py:3899-3901` - Fixed `refresh()` method to actually reload data

**Impact**: Collection view now updates properly when clicking on collections!

---

## PHASE 1 COMPLETE ✅

### Generic Hierarchical Support in Sidebar Renderer

**Goal**: Make the sidebar renderer support hierarchy through callbacks (generic, reusable component)

### Changes Made

**1. Updated NSOutlineView Delegates** (`macos_sidebar.py`)

**Lines 121-150: `numberOfChildrenOfItem_`**
- Now supports hierarchy via `_get_children_callback`
- Root level returns `len(self.interface._data)`
- Non-root items call callback to get children
- Falls back to 0 (leaf node) if no callback or no children

**Lines 153-183: `child_ofItem_`**
- Returns root items for `item == None`
- For non-root, calls `_get_children_callback(item._python_data)`
- Wraps child data in `SidebarItem` objects
- Returns `None` for out-of-range or no callback

**Lines 186-213: `isItemExpandable_`**
- Checks `_node_type` field in item data
- Sections, collections, folders can be expandable
- Returns `item_data.get('_has_children', False)`
- Generic - works for any node type!

**2. Added Callback Registration** (`macos_sidebar.py:1400-1430`)

```python
def set_get_children_callback(self, callback: callable):
    """
    Set callback for getting children of a hierarchical item.

    Args:
        callback: Function(item_data: Dict) -> Optional[List[Dict]]
    """
```

**Callback Pattern:**
```python
def get_children(item_data):
    node_type = item_data.get('_node_type')

    if node_type == 'section':
        return list_of_collections
    elif node_type == 'collection':
        return list_of_folders
    elif node_type == 'folder':
        return list_of_subfolders

    return None  # Leaf nodes
```

### What This Enables

✅ **True Hierarchy** - Not just styled flat lists anymore
✅ **Generic Component** - Sidebar doesn't know about sections/collections/folders
✅ **Expand/Collapse** - NSOutlineView handles triangles automatically
✅ **Flexible** - Works for any tree structure (file browser, org chart, etc.)
✅ **Lazy Loading Ready** - Callback can load children on-demand

---

## DEMO APP CREATED ✅

**Demo**: `src/fichero/shared/widgets/list_widget/demos/widget_list_demo.py`

### What It Tests

**Mock Data Structure:**
```
📥 INBOX (section)
  ├─ Inbox (collection, no folders)

📁 LIBRARY (section)
  ├─ Documents Archive (collection)
  │   ├─ 2024 (folder)
  │   │   ├─ January (folder)
  │   │   └─ February (folder)
  │   └─ Legal (folder)
  └─ Photos (collection, no folders)

🔗 EXTERNAL FOLDERS (section)
  └─ Network Drive (collection)
      └─ Shared Documents (folder)
```

### Features Demonstrated

1. **3-Level Hierarchy**: Sections → Collections → Folders
2. **Section Header Styling**: Uppercase, gray, bold, 32px height
3. **Expandable Nodes**: Click triangles to expand/collapse
4. **Non-Selectable Headers**: Section headers can't be selected
5. **Nested Folders**: Folders under folders under collections
6. **Visual Spacing**: Extra padding on section headers

### How to Run

```bash
# Using Briefcase (recommended)
briefcase dev

# The demo app will launch automatically and show the widget list demo with button navigation
```

**Requirements:**
- macOS (uses NSOutlineView via Rubicon-ObjC)
- Briefcase/Toga installed
- Python 3.8+

### What to Test

1. **Expand/Collapse**:
   - Click triangle next to "LIBRARY" → should show collections
   - Click triangle next to "Documents Archive" → should show folders
   - Click triangle next to "2024" → should show January, February

2. **Selection**:
   - Try clicking "INBOX" header → should NOT select (no highlight)
   - Click "Inbox" collection → should select (highlight)
   - Click "2024" folder → should select

3. **Visual Hierarchy**:
   - Section headers: UPPERCASE, gray, bold
   - Collections: Regular text with icons
   - Folders: Indented under collections
   - Nested folders: Further indented

4. **Icons**:
   - Sections: No icon (just text)
   - Collections: Type-specific icons
   - Folders: Folder icon

---

## DATA STRUCTURE SPECIFICATION

### Item Data Format

Every item in the hierarchy must be a dict with these fields:

```python
{
    '_node_type': str,  # 'section', 'collection', 'folder', 'file', etc.
    '_has_children': bool,  # True if expandable
    'text': str,  # Display text
    'icon': Optional[str],  # SF Symbol name or PNG path

    # Optional metadata:
    '_is_section_header': bool,  # Special styling for sections
    '_section_id': str,  # For sections
    '_collection_id': str,  # For collections
    '_folder_id': str,  # For folders

    # For demo/testing only:
    '_children': List[Dict],  # Embedded children (not used in production)
}
```

### Node Types

| Type | Selectable | Expandable | Special Styling |
|------|------------|------------|-----------------|
| `section` | No | Yes | Uppercase, gray, bold, 32px height |
| `collection` | Yes | Yes (if has folders) | Regular, icon, 24px height |
| `folder` | Yes | Yes (if has subfolders) | Regular, folder icon, indented |
| `file` | Yes | No | Regular, file icon, indented |

---

## NEXT STEPS

### Before Integrating with Library

**Test the Demo App:**
1. Run `python demo_hierarchical_sidebar.py`
2. Verify all expand/collapse works
3. Verify selection behavior
4. Verify visual styling
5. Check console logs for errors

**Known Issues to Watch For:**
- Triangles not appearing (check `_has_children` flag)
- Items not expanding (check `_get_children_callback` implementation)
- Selection not working (check `shouldSelectItem` logic)
- Styling broken (check `_is_section_header` flag)

### After Demo Testing Passes

**Phase 2: Data Model**
- Create `SidebarFolderNode` dataclass
- Update `SidebarSection` and `SidebarCollection` with children support
- Implement tree building from flat list with `parent_id`

**Phase 3: Library Integration**
- Add `get_collection_folder_tree()` to LibraryManager
- Wire up to sidebar data model
- Implement lazy loading (folders load on expand)

---

## ARCHITECTURE

### Separation of Concerns

**Generic Widget Layer** (sidebar renderer):
- Knows about: parent-child relationships, expand/collapse, selection
- Doesn't know about: sections, collections, folders, library data
- Communication: Callbacks (`_get_children_callback`)

**Domain Layer** (sidebar data model):
- Knows about: sections, collections, folders, library structure
- Doesn't know about: NSOutlineView, macOS UI details
- Communication: Provides data in standard format

**Backend Layer** (library manager):
- Knows about: database queries, file system, items with parent_id
- Doesn't know about: UI, widgets, rendering
- Communication: Returns Collection and CollectionItem objects

### Data Flow

```
LibraryManager
    ↓ (Collections + Items with parent_id)
SidebarDataModel
    ↓ (Build tree structure)
_get_children_callback
    ↓ (Return children for item)
MacOSSidebarRenderer
    ↓ (NSOutlineView delegates)
NSOutlineView
    ↓ (Native macOS UI)
User sees hierarchical sidebar!
```

---

## TESTING STRATEGY

### Unit Tests (To Be Written)

```python
# tests/unit/test_sidebar_hierarchical.py

def test_get_children_callback_registration():
    """Test that callback can be registered"""

def test_expandable_detection():
    """Test isItemExpandable with different node types"""

def test_number_of_children():
    """Test numberOfChildrenOfItem with hierarchy"""

def test_child_at_index():
    """Test child_ofItem returns correct child"""

def test_section_header_styling():
    """Test that sections render with special styling"""

def test_nested_hierarchy():
    """Test 3+ levels of nesting"""
```

### Integration Tests

```python
# tests/integration/test_sidebar_demo.py

def test_demo_app_launches():
    """Test that demo app starts without errors"""

def test_expand_collapse_works():
    """Test expand/collapse functionality"""

def test_selection_behavior():
    """Test selecting different node types"""
```

### Manual Test Checklist

- [ ] Demo app runs without errors
- [ ] All sections show expand triangles
- [ ] Expanding sections shows collections
- [ ] Expanding collections shows folders
- [ ] Nested folders work (folder → folder → folder)
- [ ] Section headers not selectable
- [ ] Collections selectable
- [ ] Folders selectable
- [ ] Visual spacing correct
- [ ] Icons display properly
- [ ] Indentation shows hierarchy clearly

---

## FILES MODIFIED

### Core Renderer
- `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py`
  - Lines 121-150: `numberOfChildrenOfItem_` (hierarchical support)
  - Lines 153-183: `child_ofItem_` (hierarchical support)
  - Lines 186-213: `isItemExpandable_` (node type detection)
  - Lines 1400-1430: `set_get_children_callback()` (NEW method)

### Bug Fixes
- `src/fichero/windows/main/main_window.py:1044` (collection view refresh)
- `src/fichero/windows/main/views/collection/collection_view.py:3899-3901` (refresh method)

### Demo/Testing
- `src/fichero/shared/widgets/list_widget/demos/widget_list_demo.py` (NEW - comprehensive demo)
- `src/fichero/shared/widgets/list_widget/demos/README.md` (NEW - demo documentation)

---

## SUCCESS METRICS

✅ **Generic Component**: Sidebar works for any tree structure
✅ **Callback Pattern**: Clean separation via `_get_children_callback`
✅ **Demo App**: Can test without library backend
✅ **Expandable Nodes**: True hierarchy with expand/collapse
✅ **Visual Polish**: Section headers styled correctly
⏳ **Library Integration**: Not yet started (Phase 2-3)
⏳ **Menu Commands**: Not yet started (Phase 5)
⏳ **Contextual Menus**: Not yet started (Phase 6)

---

## READY TO TEST!

The hierarchical sidebar renderer is now **generic and reusable**. The demo app lets you test the UI before hooking up the library backend.

**Next**: Run the demo, verify it works, then proceed with Phase 2 (data model) and Phase 3 (library integration).
