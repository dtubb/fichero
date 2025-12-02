# NSTreeController Migration Plan

## Overview

This document outlines the migration from our current `NSOutlineViewDataSource` approach to Apple's recommended `NSTreeController` pattern. This is necessary to fix the drag-drop animation crash where returning `True` from `acceptDrop` crashes.

## The Problem

Currently, we use `NSOutlineViewDataSource` protocol directly:
- We maintain Python dict-based data (`self._data`)
- We wrap dicts in `SidebarItem` NSObject wrappers
- We manually manage `_item_cache`, `_child_cache`, `_wrapped_items`
- When we return `True` from `acceptDrop`, NSOutlineView crashes because its internal item tracking doesn't match our manual data source updates

## Apple's Solution: NSTreeController

Apple's sample code (`NavigatingHierarchicalDataUsingOutlineAndSplitViews`) uses:
1. **NSTreeController** bound to a `contents` array
2. **KVO-compliant Node class** with `@objc dynamic var children = [Node]()`
3. **One-line move**: `treeController.move(itemsToMove, to: indexPath)`

The key insight: NSTreeController manages both the data model AND the NSOutlineView's internal state atomically. When you call `treeController.move()`, it:
1. Updates the model
2. Updates NSOutlineView's internal tracking
3. Animates the change
4. Returns

This is why Apple's code works and ours crashes.

## Migration Strategy

### Phase 1: Create KVO-Compliant Node Class (Python)

```python
# sidebar_node.py - KVO-compliant Python class for NSTreeController

from rubicon.objc import ObjCClass, objc_method, objc_property, NSObject

class SidebarNode(NSObject):
    """
    KVO-compliant node class for NSTreeController binding.

    This mirrors Apple's Node.swift but in Python:
    - @objc dynamic properties for KVO observation
    - children array that NSTreeController can observe
    - isLeaf computed property for tree structure
    """

    # KVO-compliant properties
    title = objc_property(str)
    identifier = objc_property(str)
    icon_name = objc_property(str)
    node_type = objc_property(str)  # 'section', 'collection', 'folder', 'item'
    badge_text = objc_property(str)
    can_accept_drops = objc_property(bool)

    # The key property: children array with KVO
    # NSTreeController observes this to build its tree
    children = objc_property(list)

    # Store original data for callbacks
    _original_data = objc_property(object)

    @objc_method
    def init(self):
        self = super().init()
        if self:
            self.children = []
            self.node_type = 'item'
            self.can_accept_drops = False
        return self

    @objc_property
    def isLeaf(self) -> bool:
        """NSTreeController uses this to determine if node can have children."""
        return self.node_type not in ('section', 'folder', 'collection')

    @objc_property
    def isDirectory(self) -> bool:
        """Convenience property for container check."""
        return self.node_type in ('section', 'folder', 'collection')
```

### Phase 2: Set Up NSTreeController

```python
# In renderer.py

def create_widget(self):
    # ...existing scroll view and outline view setup...

    # Create NSTreeController
    NSTreeController = ObjCClass("NSTreeController")
    self._tree_controller = NSTreeController.alloc().init()

    # Configure tree controller
    self._tree_controller.childrenKeyPath = "children"
    self._tree_controller.leafKeyPath = "isLeaf"
    self._tree_controller.countKeyPath = "children.@count"

    # Set content mode - we'll use setContent: directly
    self._tree_controller.objectClass = SidebarNode

    # The contents array - this is what we populate
    self._contents = []  # Will hold [SidebarNode] objects

    # Bind outline view to tree controller
    # In Swift: outlineView.bind(.content, to: treeController, withKeyPath: "arrangedObjects")
    self._toga_sidebar.bind_toObject_withKeyPath_options_(
        "content",
        self._tree_controller,
        "arrangedObjects",
        None
    )
```

### Phase 3: Convert Data to SidebarNode Tree

```python
def _convert_data_to_nodes(self, data_list: list) -> list:
    """Convert Python dict tree to SidebarNode tree for NSTreeController."""
    nodes = []
    for item_data in data_list:
        node = SidebarNode.alloc().init()

        # Copy properties
        node.title = item_data.get('text', '')
        node.identifier = get_item_id(item_data) or str(uuid.uuid4())
        node.icon_name = item_data.get('icon', '')
        node.badge_text = str(item_data.get('badge_text', ''))
        node.can_accept_drops = item_data.get('_can_accept_drops', False)
        node._original_data = item_data

        # Determine node type
        if item_data.get('_is_section_header'):
            node.node_type = 'section'
        elif item_data.get('_can_accept_drops'):
            node.node_type = 'folder'
        else:
            node.node_type = 'collection'

        # Recursively convert children
        children = item_data.get('_children', [])
        if children:
            node.children = self._convert_data_to_nodes(children)

        nodes.append(node)

    return nodes

def attach_source(self, source):
    """Attach data to sidebar via NSTreeController."""
    if isinstance(source, list):
        self._data = source
    else:
        self._data = list(source)

    # Convert to SidebarNode tree
    self._contents = self._convert_data_to_nodes(self._data)

    # Set tree controller content
    self._tree_controller.setContent_(self._contents)
```

### Phase 4: Implement Drag-Drop with treeController.move()

```python
# In objc_classes.py acceptDrop:

def outlineView_acceptDrop_item_childIndex_(self, outline_view, drag_info, item, index):
    """Accept drop using NSTreeController.move() - Apple's atomic approach."""

    # ... validation code stays the same ...

    if is_local_reorder:
        # Get dragged items as NSTreeNode objects
        items_to_move = []

        pasteboard = drag_info.draggingPasteboard
        source_id = str(pasteboard.stringForType_("com.fichero.collection.id"))

        # Find the NSTreeNode for the dragged item
        # NSTreeController's arrangedObjects has a descendant(at:) method
        source_tree_node = self._find_tree_node_by_id(source_id)
        if source_tree_node:
            items_to_move.append(source_tree_node)

        # Calculate destination IndexPath
        if item is not None:
            # Dropping into a container
            parent_index_path = item.indexPath
            dest_index_path = parent_index_path.appendingIndex_(index)
        else:
            # Dropping at root level
            dest_index_path = NSIndexPath.indexPathWithIndex_(index)

        # THE MAGIC LINE - one atomic operation!
        self.interface._tree_controller.move(items_to_move, to: dest_index_path)

        # Fire callback to sync database
        if self.interface._on_reorder_callback:
            self.interface._on_reorder_callback(source_id, index)

        return True  # Now we can return True without crashing!
```

### Phase 5: Update Cell Rendering

NSTreeController uses `NSTreeNode` as proxy objects. Update `outlineView_viewForTableColumn_item_` to handle this:

```python
@objc_method
def outlineView_viewForTableColumn_item_(self, outline_view, table_column, item):
    """Render cell - item is now an NSTreeNode from NSTreeController."""

    # Get the actual SidebarNode from the tree node
    if item is None:
        return None

    # item is NSTreeNode, representedObject is our SidebarNode
    node = item.representedObject

    text = node.title
    icon_name = node.icon_name
    is_section_header = node.node_type == 'section'
    badge_text = node.badge_text

    # ... rest of cell rendering stays similar ...
```

## Data Preservation Strategy

**Critical**: User's existing data must be preserved during migration.

1. **Data Format**: The underlying Python dict format (`_data`) stays the same
2. **Conversion Layer**: `_convert_data_to_nodes()` creates SidebarNode tree on-the-fly
3. **Sync Back**: After moves, sync SidebarNode tree back to `_data`:

```python
def _sync_nodes_to_data(self):
    """After NSTreeController operations, sync back to Python dicts."""
    def _sync_node(node):
        original = node._original_data
        if original:
            # Update children order in original data
            original['_children'] = [
                child._original_data
                for child in node.children
                if child._original_data
            ]
        return original

    for node in self._contents:
        _sync_node(node)
```

4. **Callbacks**: `_on_reorder_callback` still fires to update database

## Implementation Phases

### Phase 1: Foundation (Est. 2-3 hours)
- [ ] Create `sidebar_node.py` with KVO-compliant SidebarNode class
- [ ] Test KVO observation in isolation
- [ ] Verify Rubicon-ObjC supports `@objc dynamic` equivalent

### Phase 2: NSTreeController Setup (Est. 2-3 hours)
- [ ] Add NSTreeController to renderer.py
- [ ] Set up Cocoa Bindings between outline view and tree controller
- [ ] Implement `_convert_data_to_nodes()`
- [ ] Test basic rendering (without drag-drop)

### Phase 3: Drag-Drop Migration (Est. 3-4 hours)
- [ ] Update `acceptDrop` to use `treeController.move()`
- [ ] Implement `_find_tree_node_by_id()` helper
- [ ] Implement `_sync_nodes_to_data()` for database sync
- [ ] Test drag-drop with proper animation

### Phase 4: Cleanup & Testing (Est. 2-3 hours)
- [ ] Remove old manual caching code (`_item_cache`, `_child_cache`, `_wrapped_items`)
- [ ] Update all delegate methods for NSTreeNode items
- [ ] Comprehensive testing with real library data
- [ ] Performance testing with large collections

## Risks & Mitigations

### Risk 1: Rubicon-ObjC KVO Support
**Risk**: Python KVO through Rubicon-ObjC may not work correctly.
**Mitigation**: Test early with simple KVO observation. Fallback: use `willChangeValueForKey:`/`didChangeValueForKey:` manually.

### Risk 2: Cocoa Bindings Complexity
**Risk**: Setting up bindings from Python is complex.
**Mitigation**: Can use tree controller without bindings - just call `setContent:` and update manually.

### Risk 3: Data Sync Issues
**Risk**: SidebarNode tree gets out of sync with Python dicts.
**Mitigation**: Single source of truth stays as `_data`. Nodes are created fresh on `attach_source()`.

### Risk 4: Existing Integration Points
**Risk**: library_view.py and other code depends on current API.
**Mitigation**: Keep external API unchanged (`attach_source()`, callbacks, etc.)

## Files to Modify

1. **NEW**: `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar/sidebar_node.py`
2. **MODIFY**: `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar/renderer.py`
3. **MODIFY**: `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar/objc_classes.py`
4. **OPTIONAL**: `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar/tree_operations.py` (may simplify)

## Success Criteria

1. Drag-drop works with smooth animation (no bounce-back)
2. Returning `True` from `acceptDrop` doesn't crash
3. All existing data is preserved
4. Database sync via `_on_reorder_callback` still works
5. External API (`attach_source()`, callbacks) unchanged

## References

- Apple Sample: `/Users/dtubb/code/docs/NavigatingHierarchicalDataUsingOutlineAndSplitViews/`
- Key file: `OutlineViewController+DragDrop.swift` line 333: `self.treeController.move(itemsToMove, to: indexPath)`
- Node class: `Node.swift` - `@objc dynamic var children = [Node]()`
