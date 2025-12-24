# Widget List Demos

This directory contains demo applications for testing all **Widget List** renderers independently, without hooking up to the backend library system.

## Purpose

Test UI functionality of widget list renderers BEFORE integrating with the library backend:

1. **Sidebar Renderer** (NSOutlineView) - Hierarchical, macOS-native
2. **Table Renderer** (NSTableView) - Flat list with columns
3. **Detailed List Renderer** - List with icons and descriptions
4. **Tree Renderer** - Generic tree view

## Main Demo App

### `widget_list_demo.py`

**Comprehensive demo testing all renderers with separate windows**

Features:
- Opens 4 windows automatically, one for each renderer type
- Window 1: Sidebar Renderer (NSOutlineView) - Working hierarchical demo
- Window 2: Table Renderer - Placeholder (not yet implemented)
- Window 3: Detailed List Renderer - Placeholder (not yet implemented)
- Window 4: Tree Renderer - Placeholder (not yet implemented)
- Mock hierarchical data for sidebar (sections → collections → folders)
- Mock flat data for table/list views
- Info panels explaining what each renderer tests
- Independent of library backend

**Install dependencies first:**
```bash
# Install toga and required packages
pip install toga toga-cocoa rubicon-objc pyobjc-framework-Cocoa pyobjc-core
```

**Run:**
```bash
# From project root (simple Python command)
PYTHONPATH=src python3 src/fichero/shared/widgets/list_widget/demos/widget_list_demo.py
```

When launched, 6 windows will open automatically:
1. **Sidebar Renderer (NSOutlineView)** - Fully functional hierarchical demo
2. **Table Renderer (NSTableView)** - Placeholder window (coming soon)
3. **Detailed List Renderer** - Placeholder window (coming soon)
4. **Tree Renderer** - Placeholder window (coming soon)


## What Each Renderer Tests

### 1. Sidebar Renderer (NSOutlineView)

**Status**: ✅ Implemented and working

**Tests:**
- 3-level hierarchy (sections → collections → folders)
- Section headers (uppercase, gray, bold, 32px height)
- Expand/collapse triangles
- Non-selectable section headers
- Selectable collections and folders
- Visual spacing between sections
- Nested folders (folder → folder → folder)
- SF Symbol icons
- Callback pattern for getting children

**Data Format:**
```python
{
    '_node_type': str,           # 'section', 'collection', 'folder', 'file'
    '_has_children': bool,        # True if expandable
    'text': str,                  # Display text
    'icon': Optional[str],        # SF Symbol name
    '_is_section_header': bool,   # Special styling for sections
    '_children': List[Dict],      # For demo only (use callback in production)
}
```

**Callback Pattern:**
```python
def get_children(item_data):
    return item_data.get('_children')  # Or query backend

sidebar.set_get_children_callback(get_children)
```

### 2. Table Renderer (NSTableView)

**Status**: ⏳ Not yet implemented

**Will test:**
- Flat list with multiple columns
- Sortable columns
- Row selection
- Custom cell rendering
- Drag-and-drop support

### 3. Detailed List Renderer

**Status**: ⏳ Not yet implemented

**Will test:**
- List items with icons
- Multi-line descriptions
- Metadata display
- Custom styling per item

### 4. Tree Renderer

**Status**: ⏳ Not yet implemented

**Will test:**
- Generic tree view (not macOS-specific)
- Cross-platform hierarchy support
- Custom node rendering

## Component Architecture

### Location
`src/fichero/shared/widgets/list_widget/`

### Structure
```
list_widget/
├── renderers/
│   ├── macos_sidebar.py      # NSOutlineView renderer (hierarchical)
│   ├── macos_table.py         # NSTableView renderer (flat)
│   ├── detailed_list.py       # Detailed list renderer
│   └── tree.py                # Generic tree renderer
├── demos/
│   ├── widget_list_demo.py    # Main demo (all renderers)
│   ├── hierarchical_demo.py   # Legacy sidebar-only demo
│   └── README.md              # This file
└── list_widget.py             # Base widget interface
```

### Design Principles

**Generic Components:**
- Renderers don't know about sections, collections, folders
- Work with any data structure through callbacks
- Reusable across different domains

**Separation of Concerns:**
- **Renderer Layer**: UI rendering, native widgets, callbacks
- **Data Model Layer**: Sections, collections, folders, tree building
- **Backend Layer**: Database queries, file system, library manager

**Data Flow:**
```
Backend (Library Manager)
    ↓ (Collections + Items with parent_id)
Data Model (Sidebar Data Model)
    ↓ (Build tree structure)
Callback (get_children)
    ↓ (Return children for item)
Renderer (MacOSSidebarRenderer)
    ↓ (NSOutlineView delegates)
NSOutlineView
    ↓ (Native macOS UI)
User sees hierarchical sidebar!
```

## Mock Data

### Hierarchical Data (Sidebar)

```python
[
    {
        '_node_type': 'section',
        '_is_section_header': True,
        '_has_children': True,
        'text': 'Inbox',
        'icon': 'archivebox',
        '_children': [
            {
                '_node_type': 'collection',
                '_has_children': False,
                'text': 'Inbox',
                'icon': 'tray',
                '_children': []
            }
        ]
    },
    {
        '_node_type': 'section',
        '_is_section_header': True,
        '_has_children': True,
        'text': 'Library',
        'icon': 'folder',
        '_children': [
            {
                '_node_type': 'collection',
                '_has_children': True,
                'text': 'Documents Archive',
                'icon': 'doc.text',
                '_children': [
                    {
                        '_node_type': 'folder',
                        '_has_children': True,
                        'text': '2024',
                        'icon': 'folder',
                        '_children': [...]
                    }
                ]
            }
        ]
    }
]
```

### Flat Data (Table/List)

```python
[
    {'id': 1, 'name': 'Item 1', 'type': 'document', 'size': '2.5 MB'},
    {'id': 2, 'name': 'Item 2', 'type': 'image', 'size': '1.2 MB'},
    {'id': 3, 'name': 'Item 3', 'type': 'document', 'size': '500 KB'},
]
```

## Testing Checklist

When testing a renderer, verify:

- [ ] Demo launches without errors
- [ ] UI renders correctly
- [ ] Selection works as expected
- [ ] Icons display properly
- [ ] No console errors
- [ ] Performance is acceptable
- [ ] All features documented in info panel work

### Sidebar Renderer Specific:
- [ ] Expand/collapse triangles appear and work
- [ ] Section headers display correctly (uppercase, gray, bold)
- [ ] Section headers are non-selectable
- [ ] Collections/folders are selectable
- [ ] Visual spacing between sections
- [ ] Indentation shows hierarchy clearly
- [ ] Nested folders work (3+ levels)

## Requirements

- **macOS**: Some renderers use native macOS widgets (NSOutlineView, NSTableView)
- **Toga/Briefcase**: BeeWare framework
- **Rubicon-ObjC**: Python-Objective-C bridge
- **Python 3.8+**

## Troubleshooting

### "Rubicon not available"
- Only works on macOS (NSOutlineView is macOS-only)
- Install: `pip install rubicon-objc`

### "No module named 'toga'"
- Run with Briefcase: `briefcase dev`
- Or install Toga: `pip install toga`

### Triangles not showing (Sidebar)
- Check `_has_children` flag is `True`
- Verify callback returns non-empty list

### Items not expanding (Sidebar)
- Register callback: `sidebar.set_get_children_callback(fn)`
- Verify callback returns `List[Dict]`, not `None`

## Adding New Renderers

When implementing a new renderer:

1. Create renderer file: `src/fichero/shared/widgets/list_widget/renderers/new_renderer.py`
2. Add demo section in `widget_list_demo.py`
3. Create mock data in `_create_xxx_mock_data()`
4. Add button and show method (`show_xxx_demo()`)
5. Update this README with:
   - What the renderer tests
   - Data format required
   - Usage patterns
   - Testing checklist

## Related Documentation

- `HIERARCHICAL_SIDEBAR_PROGRESS.md` - Phase 1 implementation progress
- `SECTION_HEADERS_IMPLEMENTATION.md` - Section header styling details
- `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py` - Sidebar renderer source

## Implementation Status

- ✅ **Sidebar Renderer**: Hierarchical support complete
- ✅ **Demo App**: Comprehensive testing app
- ⏳ **Table Renderer**: Pending
- ⏳ **Detailed List**: Pending
- ⏳ **Tree Renderer**: Pending

## Next Steps

1. Test hierarchical sidebar demo thoroughly
2. Implement Table Renderer
3. Implement Detailed List Renderer
4. Implement Tree Renderer
5. Wire up to library backend (Phase 2-3)
6. Add menu commands (Phase 5)
7. Add contextual menus (Phase 6)
