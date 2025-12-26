# TODO-059: Implement Hierarchical Folder Structure for All Sidebar Items

## What to do
Add hierarchical folder support to the sidebar so folders, searches, chats, and workflows can be organized in a hierarchy instead of being flat.

## Steps
- [ ] Step 1: Review current sidebar data models and identify where hierarchy needs to be added
- [ ] Step 2: Update backend data models to support parent-child folder relationships for all item types
- [ ] Step 3: Update frontend sidebar view to display hierarchical folder structure with proper indentation
- [ ] Step 4: Implement folder expand/collapse functionality for hierarchical display
- [ ] Step 5: Update drag and drop to support moving items into hierarchical folders
- [ ] Step 6: Test hierarchical structure with all item types (folders, searches, chats, workflows)

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
