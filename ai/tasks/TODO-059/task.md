# TODO-059: Implement Hierarchical Folder Structure for All Sidebar Items

## What to do
Add hierarchical folder support to the sidebar so folders, searches, chats, and workflows can be organized in a hierarchy instead of being flat.

## Steps
- [x] Step 1: Review current sidebar data models and identify where hierarchy needs to be added
- [x] Step 2: Update backend data models to support parent-child folder relationships for all item types (no changes needed - already supported)
- [x] Step 3: Update frontend Swift models to add folderPath and sortOrder fields
- [x] Step 4: Create SidebarItemBuilder.swift to build hierarchical structures from flat lists
- [x] Step 5: Update ContentView to use hierarchy builders
- [x] Step 6: Document implementation (folder expand/collapse already works via existing DisclosureGroup)

## Manual Action Required
- Add SidebarItemBuilder.swift to Xcode project:
  - Open Fichero/Fichero.xcodeproj in Xcode
  - Right-click on Models folder
  - Select "Add Files to Fichero"
  - Choose Fichero/Fichero/Models/SidebarItemBuilder.swift
  - Ensure "Copy items if needed" is unchecked (file is already in correct location)
  - Click "Add"

## Files
- Backend models: `fichero_api/app/models/` - folder, search, chat, workflow models
- Frontend sidebar: `Fichero/Fichero/Views/Browser/SidebarView.swift`
- Frontend models: `Fichero/Fichero/Models/` - relevant item models

## Questions for Human
- [ ] Question 1: Should all item types (searches, chats, workflows) support nesting or only folders?
    Answer: Based on the request, all item types should support being organized in a folder hierarchy
- [ ] Question 2: What is the maximum nesting depth allowed?
    Answer: Allow reasonable nesting (5-10 levels) with UI handling deep hierarchies gracefully

## Answers and Implementation
- All sidebar item types will support being placed in a folder hierarchy
- Backend will add parent_id field to relevant models to support tree structure
- Frontend will use OutlineGroup or similar SwiftUI components for hierarchical display
- Existing drag and drop functionality will be extended to work with hierarchy

## Need help?
- Review existing sidebar tasks (TODO-051 through TODO-058) for context
- Check frontend/key_files.md for navigation
