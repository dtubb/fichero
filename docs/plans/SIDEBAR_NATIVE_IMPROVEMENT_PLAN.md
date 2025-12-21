# Sidebar Native Improvement Plan

## Current Issues

1. **Crashes on click/expand/collapse** - KVO observer issues, improper init patterns
2. **No icons showing** - SF Symbol loading not working
3. **No badges** - Missing badge count display
4. **Full tree reload** - Reloads entire tree instead of updating nodes
5. **Missing contextual menu** - No right-click menu
6. **Missing + buttons on sections** - Can't add items to sections
7. **Missing sections** - Only LIBRARY, need SEARCHES, WORKFLOWS, TOOLS, PROVIDERS

## Learning Sources

### Apple Demo (NavigatingHierarchicalDataUsingOutlineAndSplitViews)
- **Node.swift**: `@objc dynamic var children` for KVO
- **OutlineViewController+Delegate.swift**: Cell view creation with `makeView(withIdentifier:owner:)`
- **OutlineViewController+ContextalMenu.swift**: Context menu via CustomMenuDelegate protocol
- **Different views per type**: IconViewController (folder), FileViewController (file), ImageViewController (image)
- **Incremental updates**: `treeController.insert(node, atArrangedObjectIndexPath:)` instead of reload

### Old sidebar.py (747 lines)
- **SourceListItem dataclass**: Clean Python data model with `text`, `icon`, `badge`, `children`
- **menuForEvent_**: Context menu generation
- **on_action callback**: Menu action handling
- **do_rename_**: Inline rename support
- **DEFAULT_CONTEXT_MENU**: Predefined menu items

## Implementation Plan

### Phase 1: Fix Critical Crashes
1. **Fix SidebarNode init** - Ensure proper ObjC init pattern with return type
2. **Fix KVO observer** - Use try/except in observer callback, check for nil
3. **Fix selection callback** - Guard against missing document_id
4. **Remove full reload** - Use incremental tree controller updates

### Phase 2: Fix Icons
1. **Use NSImage.imageWithSystemSymbolName_** correctly
2. **Add fallback icons** - Use generic folder/document icons if SF Symbol fails
3. **Cache icons** - Avoid repeated icon creation

### Phase 3: Add Contextual Menu
1. **Create _OutlineContextMenuDelegate** - Handle menuForEvent_
2. **Define menu items** - Rename, Delete, Add Folder, Add Document, Reveal in Finder
3. **Wire to on_action callback** - Use same pattern as browser.py
4. **Inline rename** - Make text field editable on rename action

### Phase 4: Add + Buttons on Sections
1. **Custom header cell view** - NSTableCellView with button
2. **Wire button to add action** - Insert new node at end of section
3. **Auto-edit new item name** - Focus text field after insert

### Phase 5: Add Missing Sections
```python
def build_sidebar_tree() -> list[SidebarNode]:
    roots = []

    # LIBRARY - collections from DB
    library = create_section("LIBRARY", icon="books.vertical.fill")
    for doc in db.query(Document, doc_type=DocType.collection):
        library.addChild_(create_node_from_document(doc))
    roots.append(library)

    # SEARCHES - saved searches (placeholder for now)
    searches = create_section("SEARCHES", icon="magnifyingglass")
    # TODO: Load from saved searches storage
    roots.append(searches)

    # WORKFLOWS - from plans directory
    workflows = create_section("WORKFLOWS", icon="arrow.triangle.branch")
    for plan in load_workflow_plans():
        workflows.addChild_(create_node(plan.name, icon="doc.text", id=plan.id))
    roots.append(workflows)

    # TOOLS - processing tools
    tools = create_section("TOOLS", icon="wrench.and.screwdriver.fill")
    for tool in get_registered_tools():
        tools.addChild_(create_node(tool.name, icon=tool.icon, id=tool.id))
    roots.append(tools)

    # PROVIDERS - AI providers with models
    providers = create_section("PROVIDERS", icon="cpu.fill")
    for provider in get_ai_providers():
        provider_node = create_node(provider.name, icon="server.rack", id=provider.id, is_leaf=False)
        for model in provider.models:
            provider_node.addChild_(create_node(model.name, icon="brain", id=model.id))
        providers.addChild_(provider_node)
    roots.append(providers)

    return roots
```

### Phase 6: Different Browser Views per Selection
Based on Apple demo pattern:
- **Collection selected** -> Show IconViewController (grid of documents)
- **Document selected** -> Show FileViewController (single file preview)
- **Folder selected** -> Show IconViewController (folder contents)
- **Multiple selection** -> Show MultipleSelectionViewController

## Key Code Patterns to Apply

### 1. Proper ObjC init (from Apple demo)
```python
@objc_method
def init(self) -> objc_id:
    self = ObjCInstance(send_super(__class__, self, 'init', restype=objc_id, argtypes=[]))
    if self:
        self._children = NSMutableArray.alloc().init()
    return self
```

### 2. Incremental updates (not full reload)
```python
def add_item(self, parent_id: str, node: SidebarNode):
    """Add item without reloading entire tree."""
    parent_path = self._find_index_path(parent_id)
    if parent_path:
        parent_node = self._node_at_path(parent_path)
        insert_path = parent_path.indexPathByAddingIndex_(parent_node.children.count)
        self._tree_controller.insertObject_atArrangedObjectIndexPath_(node, insert_path)
```

### 3. Context menu via delegate
```python
@objc_method
def menuForEvent_(self, event):
    point = self.convertPoint_fromView_(event.locationInWindow, None)
    row = self.rowAtPoint_(point)
    if row < 0:
        return None

    # Select clicked row if not already selected
    if not self.isRowSelected_(row):
        self.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(row), False)

    menu = NSMenu.alloc().initWithTitle_("")
    # Build menu items based on selected node type
    return menu
```

### 4. Header cell with + button
```python
def create_header_cell(self, title: str, section_id: str) -> NSTableCellView:
    cell = NSTableCellView.alloc().initWithFrame_(((0, 0), (200, HEADER_HEIGHT)))

    # Title label
    label = NSTextField.alloc().initWithFrame_(((4, 6), (150, 16)))
    label.stringValue = title
    label.font = NSFont.systemFontOfSize_weight_(11, 0.6)
    cell.addSubview_(label)

    # + button
    button = NSButton.alloc().initWithFrame_(((180, 4), (16, 16)))
    button.bezelStyle = 0  # Inline
    button.image = NSImage.imageWithSystemSymbolName_accessibilityDescription_("plus", None)
    button.target = self._delegate
    button.action = SEL("addToSection:")
    button.tag = section_id  # Store section ID in tag
    cell.addSubview_(button)

    return cell
```

## Files to Modify

1. **sidebar_native.py** - Main sidebar implementation
2. **window.py** - Update to handle new sidebar events
3. **Create sidebar_sections.py** - Section configuration and loading

## Testing Checklist

- [ ] Click on sidebar item - no crash
- [ ] Expand/collapse section - no crash
- [ ] Icons display correctly
- [ ] Right-click shows context menu
- [ ] Rename works inline
- [ ] + button adds new item
- [ ] All 5 sections load
- [ ] Selection updates browser
- [ ] Drag-drop files works
- [ ] Drag-drop reorder works (if implemented)

## Priority Order

1. **P0**: Fix crashes (Phase 1) - Must work without crashing
2. **P1**: Fix icons (Phase 2) - Visual feedback needed
3. **P2**: Add context menu (Phase 3) - Core functionality
4. **P3**: Add sections (Phase 5) - Feature completeness
5. **P4**: Add + buttons (Phase 4) - Polish
6. **P5**: Different views (Phase 6) - Nice to have
