# TODO-062: Refactor to ID-Based Selection (Proper SwiftUI Pattern)

## What to Do

Refactor sidebar selection from struct-based to ID-based to follow Apple's recommended SwiftUI pattern. This will eliminate the complex selection restoration logic and make the code simpler and more robust.

## Why This Matters

Current approach uses `.tag(item)` which tags with struct instances. When the tree rebuilds after CRUD operations, new struct instances are created and selection is lost, requiring complex manual restoration.

**Proper approach:** Use `.tag(item.id)` and store `selectedItemId: String?` instead of `selectedItem: SidebarItem?`. SwiftUI handles selection automatically across rebuilds.

## Steps

### Phase 1: Update ContentView Selection State

- [ ] Step 1: Change `@State var selectedSidebarItem: SidebarItem?` to `@State var selectedSidebarItemId: String?`
- [ ] Step 2: Add computed property `var selectedSidebarItem: SidebarItem?` that derives item from ID
- [ ] Step 3: Update all references to `selectedSidebarItem` binding to use `selectedSidebarItemId`

### Phase 2: Update SidebarView Signature

- [ ] Step 4: Change parameter from `@Binding var selectedItem: SidebarItem?` to `@Binding var selectedItemId: String?`
- [ ] Step 5: Add computed property `var selectedItem: SidebarItem?` that derives from ID
- [ ] Step 6: Update all `.tag(item)` calls to `.tag(item.id)` (library, searches, chat, workflows)
- [ ] Step 7: Update nested children `.tag(child)` to `.tag(child.id)`

### Phase 3: Clean Up Selection Restoration

- [ ] Step 8: Remove `@State private var pendingSelectionId: String?`
- [ ] Step 9: Remove `restoreSelectionAfterRename()` function
- [ ] Step 10: Remove `restorePendingSelection()` function
- [ ] Step 11: Remove `findItemById()` function (keep for computed property if needed)
- [ ] Step 12: Remove `.onChange(of: libraryItems)` for selection restoration
- [ ] Step 13: Remove `onRenameComplete` callback from all SidebarItemRow calls
- [ ] Step 14: Remove `onRenameComplete` parameter from SidebarItemRow struct
- [ ] Step 15: Remove callback invocation from `performRename()`

### Phase 4: Update SidebarItemRow

- [ ] Step 16: Remove `@Binding var selectedItem: SidebarItem?` parameter
- [ ] Step 17: Remove `var onRenameComplete: ((String) -> Void)?` parameter
- [ ] Step 18: Update all call sites to remove these parameters

### Phase 5: Fix ContentView Usage

- [ ] Step 19: Update `handleSelection()` to work with ID
- [ ] Step 20: Fix any other ContentView code that uses selectedSidebarItem

### Phase 6: Test

- [ ] Step 21: Build and verify no compilation errors
- [ ] Step 22: Test rename → selection should persist automatically
- [ ] Step 23: Test delete → selection behavior correct
- [ ] Step 24: Test create folder → selection behavior correct
- [ ] Step 25: Test navigation → selecting items works correctly

## Files to Modify

- `Fichero/Fichero/Views/ContentView.swift`
- `Fichero/Fichero/Views/Sidebar/SidebarView.swift`

## Success Criteria

✅ Selection uses `String?` ID binding
✅ All `.tag()` calls use `item.id` not `item`
✅ No manual selection restoration code
✅ No `pendingSelectionId` state
✅ No `onRenameComplete` callbacks
✅ Selection persists automatically after rename/delete
✅ No flash when renaming
✅ Code is simpler and more maintainable
✅ Build succeeds with no errors

## Expected Outcome

**Before:** 50+ lines of complex selection restoration logic
**After:** SwiftUI handles it automatically, ~10 lines for computed property

## References

- Apple Documentation: [List init(_:selection:rowContent:)](https://developer.apple.com/documentation/swiftui/list/init(_:selection:rowcontent:)-1q8lq)
- Research: `ai/tasks/TODO-062/research.md`
- Apple Forums: [SwiftUI List selection](https://developer.apple.com/forums/thread/122140)
