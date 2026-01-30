# Sidebar Consistency & Unification Plan

## Current State (2026-01-29)

### Problem Summary
The sidebar modes have inconsistent implementations, making the UX confusing and code hard to maintain.

### Current Sidebar Modes (7 total)

1. **Library** (Navigate) - Most complete implementation
   - Has folders, subfolders
   - CRUD: add, delete, rename, duplicate
   - Drag & drop within/between libraries
   - Uses `SidebarItemRow` with `SidebarItem` model
   - File: `LibrarySidebarContent.swift` (3.3KB)

2. **Search** - Shows search results
   - No folders
   - File: `SearchSidebarContent.swift` (3.2KB)

3. **Chat** - AI conversation interface
   - File: `ChatSidebarContent.swift` (9.2KB)

4. **Workflows** - Partially implemented
   - Clicking causes layout jump (bug)
   - No folders
   - Limited CRUD
   - Different code path from Library
   - File: `WorkflowsSidebarContent.swift` (10.6KB)

5. **Automation** (Schedules & Triggers) - Split design
   - Schedules and Triggers shown separately in disclosure groups
   - Has + buttons in disclosure headers
   - No folders
   - Can't actually create new (clicking + doesn't work)
   - File: `AutomationSidebarContent.swift` (9.2KB)

6. **Activity** - Shows running tasks/executions
   - Real-time status updates
   - Read-only (monitoring view)
   - File: `ActivitySidebarContent.swift` (17.2KB) - largest!

7. **Batches** - Minimal implementation
   - No + button or bottom toolbar
   - No folders
   - Shows running/completed batches only
   - Read-only feel
   - File: `BatchesSidebarContent.swift` (4.5KB)

**Also related:**
- `ActivityRun.swift` (1.8KB)
- `ActivityRunRow.swift` (2KB)

### Specific Issues Identified
- [ ] Workflows: clicking causes left-jump layout bug
- [ ] Batches: no bottom toolbar, no add button
- [ ] Automation: can't add triggers or schedules (+ button broken?)
- [ ] Comparisons: not accessible from sidebar
- [ ] No folder support for workflows, batches, automation
- [ ] Schedules/Triggers artificially separated (user wants unified)
- [ ] Inconsistent code paths - each mode is implemented differently

### Functionality Audit (Code Review - 2026-01-29)

**Legend:** ✅ Works | ❌ Not implemented | ⚠️ Partial | N/A Not applicable

| Mode | Add | Delete | Rename | Duplicate | Folders | Drag/Drop | Row Component |
|------|-----|--------|--------|-----------|---------|-----------|---------------|
| Library | ✅ | ✅ | ✅ inline | ❌ | ✅ | ✅ | `SidebarItemRow` |
| Search | ✅ | ✅ | ✅ inline | ❌ | ❌ | ⚠️ | `SidebarItemRow` |
| Chat | ✅ chats, ✅ comparisons | ✅ chats, ❌ comparisons | ✅ chats, ❌ comparisons | ❌ | ❌ | ⚠️ chats only | `SidebarItemRow` + `ComparisonSidebarRow` |
| Workflows | ✅ | ✅ | ✅ inline (workflows), ⚠️ alert (chains) | ❌ | ❌ | ⚠️ workflows only | `SidebarItemRow` + `ChainSidebarRow` |
| Automation | ✅ opens editor | ✅ | ❌ | ❌ | ❌ | ❌ | `ScheduleRow` + `TriggerRow` |
| Activity | N/A | N/A | N/A | N/A | N/A | N/A | Custom (read-only) |
| Batches | ❌ (created by workflows) | ✅ | ❌ | N/A | ❌ | ❌ | `BatchRow` |

### Implementation Pattern Analysis

**Group A: SidebarItemRow-based** (Library, Search, Chat, Workflows)
- Uses unified `SidebarItemRow` component
- Has `RenameStateManager` for inline rename
- Has `DeleteStateManager` for delete confirmation
- Data comes from `cachedLibraryHeaders` (built from Combine publishers)
- Context menus via `SidebarItemContextMenu`

**Group B: Custom Row-based** (Automation, Batches)
- Uses specialized row components (`ScheduleRow`, `TriggerRow`, `BatchRow`)
- Actions via `onAction` callback pattern
- Data loaded via async `load*Data()` in SidebarView
- No inline rename (would need redesign)
- No drag/drop support

**Group C: Read-Only** (Activity)
- Custom nested DisclosureGroup structure
- Real-time data from `WorkflowExecutionObserver`
- Historical data from parent
- No CRUD needed

### Key Findings

1. **Add buttons work** - Automation "+" buttons correctly set `viewMode = .schedule(nil)` / `.trigger(nil)` which opens editor
2. **Rename inconsistency** - Group A uses inline TextField, chains use alert dialog, Group B has no rename
3. **Folder support missing** - Only Library mode has working folder hierarchy
4. **Drag/Drop partial** - Works in Library, items are draggable elsewhere but no drop targets
5. **Comparisons isolated** - Shown in Chat sidebar with custom row, no delete endpoint exists

### User Requirements

#### Unified CRUD for All Item Types
- Add (new item, new folder)
- Delete
- Rename (inline)
- Duplicate
- Move (drag & drop)

#### Folder Support
- Folders and subfolders for:
  - Workflows
  - Actions
  - Chains
  - Comparisons
  - Schedules
  - Triggers
  - Searches (saved)
- NOT for:
  - Activity (running tasks)
  - Batches (running/completed jobs)

#### Library-Based Organization
- All items belong to a library
- Multiple libraries supported
- Drag & drop between libraries
- Each library section shows its items

#### Consistent UI
- Same row styling across all modes
- Same context menu options
- Same toolbar/bottom bar
- Same selection behavior

## Architecture Proposal

### Shared Components
1. **UnifiedSidebarItem** - Generic item model that works for all types
   - `id: String`
   - `name: String`
   - `itemType: SidebarItemType` (workflow, schedule, trigger, comparison, search, folder, etc.)
   - `parentId: String?` (for folders)
   - `libraryId: UUID`
   - `icon: String`
   - `metadata: [String: Any]` (type-specific data)

2. **UnifiedSidebarRow** - Single row component for all item types
   - Reuse existing `SidebarItemRow` patterns
   - Support inline rename
   - Support drag & drop
   - Support context menu

3. **UnifiedSidebarContent** - Single content view for item-based modes
   - Takes item type filter
   - Shows library sections
   - Handles CRUD operations

### Backend Requirements
- Folders table/model for organizing items
- Move endpoint for changing parent/library
- Consistent response format across item types

## Files Reference

### Sidebar Content Views (by lines of code)

| File | Lines | Pattern | Notes |
|------|-------|---------|-------|
| `ActivitySidebarContent.swift` | 468 | Custom | Largest, real-time + historical |
| `WorkflowsSidebarContent.swift` | 303 | SidebarItemRow + Custom | Chains have own row |
| `ChatSidebarContent.swift` | 274 | SidebarItemRow + Custom | Comparisons have own row |
| `AutomationSidebarContent.swift` | 244 | Custom | Uses DisclosureGroups |
| `ScheduleRow.swift` | 137 | Row component | Used by Automation |
| `TriggerRow.swift` | 135 | Row component | Used by Automation |
| `BatchRow.swift` | 122 | Row component | Used by Batches |
| `BatchesSidebarContent.swift` | 120 | Custom | Minimal implementation |
| `LibrarySidebarContent.swift` | 102 | SidebarItemRow | Clean reference impl |
| `SearchSidebarContent.swift` | 100 | SidebarItemRow | Nearly identical to Library |

### Shared Infrastructure

| File | Lines | Purpose |
|------|-------|---------|
| `SidebarView.swift` | 856 | Main coordinator, data loading, creation methods |
| `SidebarItemRow.swift` | 532 | Unified row with drag/drop, inline rename |
| `SidebarItem.swift` | ~300 | Data model with `itemType` enum |
| `SidebarStateManagers.swift` | 47 | RenameStateManager, DeleteStateManager |
| `SidebarItemContextMenu.swift` | ~100 | Context menu builder |

### Backend API Endpoints (to verify)

| Operation | Schedules | Triggers | Batches | Comparisons |
|-----------|-----------|----------|---------|-------------|
| List | ✅ GET /api/automation/schedules | ✅ GET /api/automation/triggers | ✅ GET /api/batch | ✅ GET /api/model-comparison/history |
| Create | ✅ POST /api/automation/schedules | ✅ POST /api/automation/triggers | ❌ (via workflow) | ✅ POST /api/model-comparison/compare |
| Update | ✅ PUT /api/automation/schedules/{id} | ✅ PUT /api/automation/triggers/{id} | ❌ | ❌ |
| Delete | ✅ DELETE /api/automation/schedules/{id} | ✅ DELETE /api/automation/triggers/{id} | ✅ DELETE /api/batch/{id} | ❌ Missing |
| Rename | ⚠️ Via Update | ⚠️ Via Update | ❌ | ❌ |

## Next Steps

1. **Audit** - Read all sidebar content views to understand current implementation
2. **Design** - Create unified data model and component structure
3. **Backend** - Add missing endpoints (folders, CRUD operations)
4. **Refactor** - Implement shared components
5. **Test** - Verify all CRUD operations work consistently

## Priority Order with Specific Tasks

### P0: Fix Actually Broken Functionality
Nothing is completely broken - the + buttons DO work (they open editors).

However, these are confusing/incomplete:
- [ ] **Automation rename** - No way to rename schedules/triggers
- [ ] **Comparison delete** - Backend endpoint missing (`DELETE /api/model-comparison/{id}`)
- [ ] **Batches sidebar** - No bottom toolbar (inconsistent with other modes)

### P1: Unify Code Paths (Reduce 3 Patterns → 1)

**Option A: Extend SidebarItemRow for all types**
- Add `ScheduleInfo`, `TriggerInfo`, `BatchInfo` to `SidebarItem.itemType`
- Modify `SidebarItemRow` to render appropriate content per type
- Modify rename/delete handlers to call appropriate service
- PRO: Maximum code reuse, consistent behavior
- CON: SidebarItemRow grows complex

**Option B: Create SidebarItemRow variants**
- Keep `SidebarItemRow` for documents/folders
- Create `AutomationItemRow` based on SidebarItemRow patterns
- Create `BatchItemRow` based on SidebarItemRow patterns
- PRO: Cleaner separation
- CON: More duplication

**Recommendation: Option A** - The existing pattern already handles multiple types (document, search, conversation, workflow, chain). Adding schedule/trigger/batch follows the same approach.

### P2: Add Folder Support

**Frontend changes needed:**
1. Add `folderPath` editing to schedule/trigger/batch/comparison models
2. Show folder hierarchy in sidebar (extend existing pattern)
3. Enable drag/drop for these types

**Backend changes needed:**
1. Add `folder_path` column to schedules/triggers tables (if missing)
2. Add `PATCH` endpoint to update folder_path
3. Return `folder_path` in list responses

### P3: Polish

- [ ] Consistent row heights across all modes
- [ ] Consistent icon colors
- [ ] Consistent context menu items
- [ ] Keyboard shortcuts work in all modes (delete, rename)
