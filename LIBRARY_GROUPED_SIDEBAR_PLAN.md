# Library-Grouped Sidebar Refactor Plan

## Goal
Restructure sidebar from section-based grouping (Library, Searches, Chat, Workflows) to library-based grouping where each library contains all its items (folders, searches, chats, workflows).

## Current Structure (Section-Based)
```
Libraries
  > Library 1
  > Library 2

Searches
  > Library 1
  > Library 2

Chat
  > Library 1
  > Library 2

Workflows
  > Library 1
  > Library 2
```

## Target Structure (Library-Based)
```
▼ Library 1
    📁 Research Project
    📁 Meeting Notes
    🔍 Recent PDFs
    💬 Research Chat
    ⚙️ Extract Keywords

▼ Library 2
    📁 Personal
    🔍 Photos Search
    💬 Photo Analysis

▼ Global
    🔍 All Documents
    💬 General Chat
    ⚙️ Batch Convert
```

## Key Concepts

### 1. Global Library
- Special library stored at `~/Library/Application Support/Fichero/global.duckdb`
- Always open, always at the bottom of the sidebar
- Default location for new searches/chats/workflows
- Can search across ALL libraries
- User can drag items between Global and specific libraries

### 2. Library-Grouped Items
- Each library is a collapsible group
- Within each library: folders, searches, chats, workflows are siblings (no sections)
- Items can be in any order, including nested folders
- Visual hierarchy maintained through indentation

### 3. No "Active Library" Concept
- Selected item's libraryId determines which library owns it
- ContentView displays the selected item's content using that item's libraryId
- Creation defaults to Global (no concept of "current" library)

### 4. Drag & Drop Between Libraries
- User can move searches/chats/workflows between libraries and Global
- Folders belong to their library (can't be moved between libraries)

## Implementation Phases

### Phase 1: Backend - Global Library Support
- [ ] Create global library path in StorageSettings
- [ ] Update LibraryManager to always load Global library
- [ ] Global library has fixed UUID (e.g., "00000000-0000-0000-0000-000000000001")
- [ ] Global library displayName = "Global"
- [ ] Global library always appears last in sidebar

### Phase 2: Models - Library-Grouped Structure
- [ ] Remove SidebarSection enum (no more sections!)
- [ ] Update SidebarItem to support mixed item types in same hierarchy
- [ ] Add itemCategory enum: folder, search, chat, workflow
- [ ] Update SidebarItemBuilder.buildLibraryGroup() to return all items for a library

### Phase 3: SidebarView - Restructure UI
- [ ] Remove section-based rendering (libraryExpanded, searchesExpanded, etc.)
- [ ] Render list of libraries (including Global at bottom)
- [ ] Each library expands to show all its items (mixed types)
- [ ] Update selection handler: extract libraryId from item, no "switching"
- [ ] Update creation methods: default to Global library

### Phase 4: ContentView - Remove Active Library
- [ ] Remove windowState.libraryId concept
- [ ] Extract library from selected item instead
- [ ] Pass selected item's library to browser/inspector

### Phase 5: SidebarState - Update Persistence
- [ ] Remove section expansion state (libraryExpanded, searchesExpanded, etc.)
- [ ] Keep only expandedItems (per-item expansion)
- [ ] Track which libraries are expanded (libraryId -> Bool)

### Phase 6: Drag & Drop - Inter-Library Movement
- [ ] Update DragDropService to support moving items between libraries
- [ ] Allow searches/chats/workflows to be moved
- [ ] Prevent folders from being moved between libraries

## File Changes

### Backend Files

#### src/fichero/storage.py
Add global library path:
```python
@computed_field
@property
def global_library_path(self) -> Path:
    """Path to global library database."""
    return self.base_path / "global.duckdb"
```

### Frontend Files

#### Fichero/Fichero/Models/LibraryManager.swift
- Add GLOBAL_LIBRARY_ID constant
- loadGlobalLibrary() called on init
- Global library always in openLibraries

#### Fichero/Fichero/Models/SidebarItem.swift
- Remove section: SidebarSection field
- Add category: ItemCategory enum (folder, search, chat, workflow)
- Update all initializers

#### Fichero/Fichero/Models/SidebarItemBuilder.swift
- Remove section parameter from all methods
- buildLibraryGroup(library) returns mixed list of all item types
- Sort/order items within library

#### Fichero/Fichero/Models/SidebarState.swift
- Remove libraryExpanded, searchesExpanded, chatExpanded, workflowsExpanded
- Add libraryExpansionStates: [UUID: Bool]
- Simplify persistence

#### Fichero/Fichero/Views/Sidebar/SidebarView.swift
- Remove section-based rendering
- Render List of libraries
- Each library expands to show buildLibraryGroup(library)
- Update selection handler (no library switching)
- Update creation methods to use Global library

#### Fichero/Fichero/Views/ContentView.swift
- Remove windowState.libraryId
- Extract library from selectedItem.libraryId
- Pass to browser/inspector

#### Fichero/Fichero/Models/WindowState.swift
- Remove libraryId property

## Migration Strategy

### Data Migration
- No data migration needed!
- Existing libraries keep their searches/chats/workflows
- Global library created on first launch (empty)
- User manually moves items to Global if desired

### Gradual Rollout
1. Backend changes (Global library support)
2. Model changes (remove sections, add categories)
3. UI changes (library-grouped rendering)
4. Drag & drop (optional, can come later)

## Edge Cases

### No Libraries Open
- Global library is always open
- Show only Global in sidebar

### One Regular Library + Global
- Show both libraries
- Works as expected

### Many Libraries
- Scrollable list
- Each library collapsible
- Global always at bottom

### Empty Global Library
- Still shown in sidebar
- Shows "No items" state
- User can create new items

## Benefits

### User Experience
- ✅ Clear relationship: Library 1's search belongs to Library 1
- ✅ Global library for cross-library work
- ✅ Less visual clutter (no repeated library headers per section)
- ✅ Drag & drop between libraries (natural UX)

### Code Quality
- ✅ Simpler model (no section-based complexity)
- ✅ No "active library" state to manage
- ✅ Fewer moving parts
- ✅ More intuitive hierarchy

## Testing Checklist

### Phase 1-3 (Core Refactor)
- [ ] Global library created on first launch
- [ ] Global library always appears in sidebar
- [ ] Libraries show all items (folders, searches, chats, workflows mixed)
- [ ] Selection works across all item types
- [ ] Expansion state persists

### Phase 4-5 (Polish)
- [ ] Create new search -> goes to Global
- [ ] Create new chat -> goes to Global
- [ ] Create new workflow -> goes to Global
- [ ] Create new folder -> goes to Global
- [ ] Selecting item shows correct content

### Phase 6 (Drag & Drop)
- [ ] Drag search from Library 1 to Global
- [ ] Drag chat from Global to Library 2
- [ ] Cannot drag folder between libraries

## Current Status

⏳ **Planning Phase** - Ready to implement

## Next Steps

1. Implement Phase 1: Backend Global Library Support
2. Implement Phase 2: Model Changes (remove sections)
3. Implement Phase 3: SidebarView Refactor
4. Implement Phase 4: ContentView Simplification
5. Implement Phase 5: State Persistence Updates
6. Test thoroughly
7. Phase 6 (Drag & Drop) can be deferred to later
