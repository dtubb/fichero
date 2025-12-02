# NSTreeController Refactoring Plan

## Current State Analysis

### The Problem

Our current implementation attempts to use NSTreeController for drag-drop but crashes because:

1. **KVO Incompatibility**: NSTreeController's mutation methods (`moveNodes:toIndexPath:`, `insertObject:atArrangedObjectIndexPath:`, `removeObjectAtArrangedObjectIndexPath:`) rely on Objective-C's auto-synthesized KVO-compliant properties.

2. **Rubicon-ObjC Limitation**: Python/Rubicon-ObjC cannot replicate Objective-C's automatic KVO that comes from `@property` declarations. Our manual `willChangeValueForKey_`/`didChangeValueForKey_` calls don't integrate properly with NSTreeController's internal expectations.

3. **Segfault on Mutation**: When NSTreeController tries to modify our SidebarNode's children array, the KVO mechanism fails, causing a segfault.

### Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Python Data Model                        │
│   List[Dict] - _data with nested _children                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     SidebarNode                             │
│   ObjC class with children array (KVO-problematic)          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   NSTreeController                          │
│   Bound to SidebarNode tree (mutations crash)               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    NSOutlineView                            │
│   DataSource methods + NSTreeController content             │
└─────────────────────────────────────────────────────────────┘
```

## Apple's Objective-C Pattern (Reference)

From `/Users/dtubb/code/docs/SourceViewUsingNSOutlineViewwithNSTreeController-master`:

### Model Class (BaseNode)
```objc
@interface BaseNode : NSObject <NSCoding, NSCopying>
@property (strong) NSString *nodeTitle;
@property (strong) NSMutableArray *children;  // Auto-synthesized KVO
@property (assign) BOOL isLeaf;
@end
```

### Drag-Drop Flow
```objc
// In writeItems - store dragged nodes
self.dragNodesArray = items;

// In acceptDrop - internal moves
[self.treeController moveNodes:self.dragNodesArray toIndexPath:indexPath];
```

### Why It Works in Objective-C
- `@property (strong)` auto-synthesizes `setChildren:` with KVO notifications
- NSTreeController observes children changes automatically
- `moveNodes:toIndexPath:` internally calls setters which trigger KVO

## Solution: Nuclear Refresh Pattern

Since we can't use NSTreeController's mutation methods, we use "Nuclear Refresh":

```
┌─────────────────────────────────────────────────────────────┐
│                    Python Data Model                        │
│   List[Dict] - _data with nested _children (SOURCE OF TRUTH)│
└──────────────────────────┬──────────────────────────────────┘
                           │
                   Drag-Drop:
                   1. Modify _data directly
                   2. Rebuild SidebarNode tree
                   3. setContent() on TreeController
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     SidebarNode                             │
│   ObjC class - REBUILT on each modification                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   NSTreeController                          │
│   setContent() replaces entire tree (no mutations)          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    NSOutlineView                            │
│   reloadData() syncs display                                │
└─────────────────────────────────────────────────────────────┘
```

## Refactoring Tasks

### Phase 1: Simplify SidebarNode (Priority: High)

**Goal**: SidebarNode becomes a simple data container, not KVO-managed.

1. **Remove KVO complexity from SidebarNode**
   - Remove `willChangeValueForKey_`/`didChangeValueForKey_` calls
   - Remove indexed accessors (`insertObject_inChildrenAtIndex_`, etc.)
   - Keep simple property accessors

2. **SidebarNode Structure**
   ```python
   class SidebarNode(NSObject):
       # Simple properties only
       @objc_method
       def identifier(self): return storage['identifier']

       @objc_method
       def nodeTitle(self): return storage['nodeTitle']

       @objc_method
       def children(self): return storage['children']

       @objc_method
       def isLeaf(self): return len(storage['children']) == 0
   ```

### Phase 2: Clean Up TreeController (Priority: High)

**Goal**: TreeController only does `setContent()`, no mutations.

1. **Remove mutation methods**
   - Remove `move()` method
   - Remove `insert_object_at_index_path()`
   - Remove `remove_object_at_index_path()`

2. **Keep only**
   - `set_content(root_nodes)` - Sets entire tree
   - `find_tree_node_by_id()` - For lookups
   - `create_index_path()` - For path building

### Phase 3: Centralize Data Model Operations (Priority: High)

**Goal**: All model mutations happen in renderer.py on Python data.

1. **Move/Reorder operations**
   ```python
   def move_item(self, source_id, target_parent_id, target_index):
       # 1. Find and remove from _data
       item, old_parent, old_index = self._find_and_remove_item(source_id)

       # 2. Insert at new location in _data
       target_children = self._get_children_for_parent(target_parent_id)
       target_children.insert(target_index, item)

       # 3. Nuclear refresh
       self._rebuild_and_refresh_tree()
   ```

2. **Add/Delete operations**
   ```python
   def add_item(self, item_data, parent_id, index):
       # 1. Add to _data
       # 2. Nuclear refresh

   def delete_item(self, item_id):
       # 1. Remove from _data
       # 2. Nuclear refresh
   ```

### Phase 4: Clean Up objc_classes.py (Priority: Medium)

**Goal**: Remove dead code paths.

1. **Drag-Drop Handler**
   - Remove fallback manual DataSource update code
   - Always use `move_via_tree_controller()` (which now does nuclear refresh)
   - Remove duplicate node tracking

2. **Remove unused methods**
   - Audit all ObjC callback methods
   - Remove any methods that reference removed tree controller functionality

### Phase 5: Testing & Validation (Priority: High)

1. **Unit Tests**
   - Test `_find_and_remove_item()` with various tree structures
   - Test `_find_item_by_id()` with nested hierarchies
   - Test `_rebuild_and_refresh_tree()` produces correct SidebarNode tree

2. **Integration Tests**
   - Test drag within same parent
   - Test drag to different parent
   - Test drag to root level
   - Test drag into expanded/collapsed containers

## Files to Modify

| File | Changes |
|------|---------|
| `sidebar_node.py` | Remove KVO complexity, simplify to data container |
| `tree_controller.py` | Remove mutation methods, keep only setContent |
| `renderer.py` | Centralize model operations, nuclear refresh |
| `objc_classes.py` | Clean up drag-drop handler, remove fallbacks |
| Unit tests | Update for new architecture |

## Trade-offs

### Advantages of Nuclear Refresh
- **Reliable**: No KVO issues, no segfaults
- **Simple**: Clear data flow, easy to debug
- **Maintainable**: Python data model is source of truth

### Disadvantages
- **No animation**: Item visually jumps to new position (no smooth move)
- **Performance**: Rebuilds entire tree on each modification
- **Selection loss**: Need to manually restore selection after refresh

### Mitigations
- For selection: Save selection before refresh, restore after
- For performance: Only rebuild if tree is large (>100 items)
- For animation: Accept this limitation as the cost of Python/ObjC bridge

## Implementation Order

1. Test current nuclear refresh implementation
2. If stable, proceed with Phase 1-2 cleanup
3. Run tests after each phase
4. Complete Phase 3-4 cleanup
5. Final testing and validation

## Success Criteria

- [ ] Drag-drop works without crashes
- [ ] Items move to correct positions
- [ ] No duplication of items
- [ ] Tree state persists correctly
- [ ] Selection can be restored after moves
- [ ] All unit tests pass
