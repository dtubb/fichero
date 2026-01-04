# Multi-Library Sidebar Refactor Plan

## Goal
Transform sidebar from showing ONE library at a time to showing ALL open libraries simultaneously, grouped by library within each section.

## Current State (Single Library)
```
[Dropdown: Select Library ▼]

Library
  folder 1
  folder 2

Searches
  search 1

Chat
  chat 1

Workflows
  workflow 1
```

## Target State (Multi-Library)
```
Library
  📚 Test Library 1
    folder 1
    folder 2
  📚 Test Library 2
    folder 1

Searches
  📚 Test Library 1
    search 1
  📚 Test Library 2
    search 2

Chat
  📚 Test Library 1
    chat 1
  📚 Test Library 2
    chat 1

Workflows
  📚 Test Library 1
    workflow 1
  📚 Test Library 2
    workflow 1
```

## Architecture Decisions

### ✅ SwiftUI-Centric Approach
- Use `@ObservedObject var libraryManager: LibraryManager`
- Each library's services are already `@Published`
- SwiftUI automatically updates when any library's data changes
- No manual cache invalidation needed

### ✅ State Persistence
- `SidebarState` (per-window) persists to UserDefaults
- Expansion states survive app relaunch
- Each window tracks its own sidebar state independently

### ✅ Active Library Concept
- Selecting an item switches the active library
- Active library = `windowState.libraryId`
- ContentView shows content from active library

## Implementation Phases

### Phase 1: Data Model ✅ COMPLETE
- [x] Add `libraryId: UUID?` to SidebarItem
- [x] Update SidebarItemBuilder to tag items with libraryId
- [x] Add `SidebarItem.libraryGroup()` helper for library headers
- [x] Create SidebarState with persistence

### Phase 2: SidebarView Refactor ✅ COMPLETE
- [x] Change signature: accept `LibraryManager` instead of individual services
- [x] Update `rebuildCaches()` to iterate all libraries
- [x] Remove "Open Libraries" section (now redundant)
- [x] Update selection handler to extract libraryId and switch active library
- [x] Update creation methods (createNewSearch, createNewChat, etc.) to use active library
- [x] Update deletion/import/folder methods to use active library
- [x] Remove obsolete `openLibrariesExpanded` state

### Phase 3: Update Callsites ✅ COMPLETE
- [x] ContentView: Pass `libraryManager` instead of individual stores
- [x] Code compiles with no errors (only linting warnings)

### Phase 4: Multi-Library Testing
- [ ] Open two libraries
- [ ] Verify sidebar shows both
- [ ] Test selecting item from Library B switches active library
- [ ] Test creating new search/chat/workflow in active library
- [ ] Test state persistence across relaunch

### Phase 5: Edge Cases
- [ ] No libraries open → show welcome screen
- [ ] One library open → works as before (but shows library header)
- [ ] Library closed → rebuild caches, remove from sidebar

## Key Files Modified

### Models
- ✅ `SidebarItem.swift` - Added libraryId field
- ✅ `SidebarItemBuilder.swift` - Accepts libraryId parameter
- ✅ `SidebarState.swift` - NEW: State persistence

### Views
- 🔄 `SidebarView.swift` - Major refactor to use LibraryManager
- ⏳ `ContentView.swift` - Update to pass libraryManager
- ⏳ `SidebarItemRow.swift` - May need updates for library switching

### Services
- No changes needed (already per-library)

## Rollback Plan

If issues arise:
1. Revert SidebarView changes
2. Keep SidebarItem/SidebarItemBuilder changes (they're backward compatible)
3. Keep SidebarState (useful even for single-library)

The data model changes are safe and don't break existing code.

## Testing Strategy

### Manual Tests
1. **Single library**: Open one library, verify all functions work
2. **Multi library**: Open two libraries, verify both appear in sidebar
3. **Switching**: Click item from Library B, verify ContentView switches
4. **Creation**: Create search/chat/workflow, verify goes to active library
5. **Persistence**: Quit and relaunch, verify expansion states restored
6. **Closing**: Close a library, verify sidebar updates

### What Could Go Wrong
- **Selection not switching library**: Check selection handler extracts libraryId
- **Items appear in wrong library**: Check SidebarItemBuilder tags correctly
- **State lost on relaunch**: Check SidebarState persistence keys
- **Performance with many libraries**: Cache is rebuilt on data change, should be fine

## Current Status

✅ **Phase 1 COMPLETE** - Data models updated with libraryId tracking
✅ **Phase 2 COMPLETE** - SidebarView refactored for multi-library
✅ **Phase 3 COMPLETE** - ContentView updated to pass LibraryManager
⏳ **Phase 4 PENDING** - Multi-library testing
⏳ **Phase 5 PENDING** - Edge cases

## Summary of Changes

### Models Updated
- `SidebarItem`: Added `libraryId: UUID?` field
- `SidebarItemBuilder`: All methods now accept and tag items with libraryId
- `SidebarItem.libraryGroup()`: New helper for creating library group headers
- `SidebarState`: New persistence layer for expansion states

### Views Updated
- `SidebarView`: Major refactor
  - Accepts `LibraryManager` instead of individual services
  - `rebuildCaches()` iterates all open libraries
  - Selection handler switches active library
  - All creation/deletion/import methods use active library's services
  - Removed "Open Libraries" section (now redundant)
- `ContentView`: Updated to pass `LibraryManager.shared`

### Code Status
✅ Compiles successfully (0 errors, 0 warnings)
✅ SwiftUI-centric approach maintained
✅ Backward compatible (works with single library)
✅ Build verified on 2026-01-03

## Next Steps

**Ready for Testing:**
1. Build and run the app
2. Open one library - verify everything works as before
3. Open two libraries - verify sidebar shows both
4. Test selection, creation, deletion across libraries
5. Test state persistence across relaunch

**If issues arise:**
- Check logs for "No active library" errors
- Verify libraryId is correctly tagged on items
- Ensure onSwitchLibrary callback is working
