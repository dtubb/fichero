# Sidebar Implementation Plan - Following Apple's Pattern

## Problem Summary

The current sidebar implementation has rubicon-objc issues:
- `KeyError` when accessing ObjC instance cache
- `AttributeError: 'objc_id' object has no attribute '_as_parameter_'`
- These occur during KVO callbacks when accessing tree controller

## Apple's Pattern (from NavigatingHierarchicalDataUsingOutlineAndSplitViews)

### 1. Node Class
```swift
class Node: NSObject {
    var title: String = ""
    @objc dynamic var children = [Node]()  // KVO-compliant array
    @objc dynamic var isLeaf: Bool { ... }  // Computed property
}
```

### 2. KVO Setup
```swift
treeControllerObserver = treeController.observe(\.selectedObjects, options: [.new]) { (treeController, change) in
    // ONLY post a notification - do NOT access selection here
    NotificationCenter.default.post(
        name: Notification.Name("selectionChanged"),
        object: treeController)
}
```

### 3. Selection Handling (in separate handler)
```swift
@objc func handleSelectionChange(_ notification: Notification) {
    guard let treeController = notification.object as? NSTreeController else { return }
    // NOW safe to access selectedNodes
    let vcForDetail = outlineVC.viewControllerForSelection(treeController.selectedNodes)
    // ... update detail view
}
```

### 4. Helper to Extract Node
```swift
class func node(from item: Any) -> Node? {
    if let treeNode = item as? NSTreeNode,
       let node = treeNode.representedObject as? Node {
        return node
    }
    return nil
}
```

## Implementation Plan for Python/Rubicon

### Phase 1: Simplify KVO Observer

The KVO observer should ONLY set a flag or schedule a callback. No ObjC access.

```python
@objc_method
def observeValueForKeyPath_ofObject_change_context_(self, keyPath, obj, change, ctx):
    sidebar = self._sidebar
    if sidebar:
        # Schedule on next event loop - NO ObjC access here
        asyncio.get_event_loop().call_soon(sidebar._handle_selection_changed)
```

### Phase 2: Handle Selection in Deferred Callback

```python
def _handle_selection_changed(self):
    if self._handling_selection:
        return
    self._handling_selection = True
    try:
        # Now safe to access tree controller
        index_path = self._tree_controller.selectionIndexPath
        if index_path:
            doc_id = self._path_to_docid.get(self._index_path_to_tuple(index_path))
            if doc_id and self.on_select:
                self.on_select(doc_id)
    finally:
        self._handling_selection = False
```

### Phase 3: Build Path Cache During Reload

When building the tree, create a Python dict mapping index path tuples to document IDs.
This avoids having to traverse the ObjC tree during selection.

```python
def reload(self):
    self._roots = build_sidebar_tree()
    self._path_to_docid = {}  # {(0,): "doc:123", (0,0): "doc:456", ...}
    self._build_path_cache(self._roots, ())
```

### Phase 4: Simplify Delegate Methods

All delegate methods should:
1. Check `if not item: return default`
2. Wrap `item.representedObject` in try/except for KeyError
3. Return safe defaults on error

```python
@objc_method
def outlineView_shouldSelectItem_(self, outline_view, item) -> bool:
    if not item:
        return True
    try:
        node = item.representedObject
        if node and getattr(node, "_is_header", False):
            return False
        return True
    except (KeyError, AttributeError):
        return True  # Safe default
```

## Key Principles

1. **Never access ObjC objects in KVO callback** - just schedule work
2. **Use Python-side caching** - path→docid mapping built during reload
3. **Graceful error handling** - catch KeyError/AttributeError, return safe defaults
4. **Keep strong references** - prevent GC of nodes while tree controller has pointers

## Files to Modify

- `sidebar_native.py` - Implement the above pattern
- `browser.py` - Simple `reloadData()`, no deferrals needed once sidebar is fixed
