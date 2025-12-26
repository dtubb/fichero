# Notes for TODO-059: Implement Hierarchical Folder Structure

## Analysis Summary

### Backend Models (src/fichero/models.py)
- **Document**: Already has `parent_id` field (line 112) - supports full hierarchy
- **Workflow**: Has `folder_path` field (line 404) - uses Unix-style paths like "/archive/letters"
- **SavedSearch**: Has `folder_path` field (line 730) - uses Unix-style paths
- **Conversation**: Has `folder_path` field (line 758) - uses Unix-style paths

### Frontend Models
- **Document** (Swift): Already has `parentId` field (line 73 in Document.swift) - matches backend
- **SidebarItem**: Already has `children` field (line 31 in SidebarItem.swift) - ready for hierarchy
- **SavedSearch**: NO parent_id or folderPath field currently
- **Conversation**: NO parent_id or folderPath field currently
- **WorkflowSidebarItem**: NO parent_id or folderPath field currently

### Frontend UI (SidebarView.swift)
- Already uses `DisclosureGroup` for hierarchical display (line 261)
- Already has expand/collapse functionality with `expandedItems` Set (line 23)
- Already has drag-and-drop to folders with `dropDestination` (line 284)
- Currently only Library section items use hierarchy - other sections are flat lists

## Implementation Strategy

### Phase 1: Update Backend Models (if needed)
The backend models already support hierarchy through `folder_path`. No changes needed for backend.

### Phase 2: Update Frontend Swift Models
Need to add `folderPath` or `parentId` to:
1. SavedSearch struct
2. Conversation struct
3. WorkflowSidebarItem struct

### Phase 3: Update Frontend Sidebar View
1. Modify data loading to build hierarchical structure for all sections
2. Each section should group items by folder_path and build tree
3. Extend drag-and-drop to work with all sections, not just Library

### Phase 4: Update API Communication
1. Ensure frontend sends/receives folder_path when creating/updating items
2. Update services to handle hierarchical queries

## Decision: Use folder_path approach
Since backend already uses `folder_path` for Workflow, SavedSearch, and Conversation, we'll use the same approach for consistency rather than parent_id.

## Implementation Progress

### Completed:
1. Updated SavedSearch, Conversation, and WorkflowSidebarItem Swift models to include folderPath and sortOrder
2. Created SidebarItemBuilder.swift with hierarchy building logic
3. Updated ContentView to use SidebarItemBuilder for all sidebar sections

### Next Steps:
1. Add SidebarItemBuilder.swift to Xcode project (needs manual Xcode or pbxproj edit)
2. Build and test
3. The sidebar already has DisclosureGroup support for hierarchical display - should work automatically
4. Drag-and-drop already supports folders for Library - extend to other sections if needed

### Files Modified:
- Fichero/Fichero/Models/SidebarItem.swift
- Fichero/Fichero/Views/ContentView.swift

### Files Created:
- Fichero/Fichero/Models/SidebarItemBuilder.swift (needs to be added to Xcode project)
