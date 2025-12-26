# Context for TODO-059: Implement Hierarchical Folder Structure for All Sidebar Items

## Background
Currently the sidebar displays all items (folders, searches, chats, workflows) in a flat list without hierarchy. Users want to organize items in nested folders for better organization.

## What you need to know
- The sidebar is implemented in SwiftUI at `Fichero/Fichero/Views/Browser/SidebarView.swift`
- Backend models are in `fichero_api/app/models/` with folder, search, chat, and workflow models
- SwiftUI provides OutlineGroup for hierarchical tree displays with expand/collapse
- The sidebar already has drag and drop functionality that will need to be extended
- Related tasks TODO-051 through TODO-058 cover other sidebar improvements
- Frontend uses MVVM pattern with @Observable state management

## Do not Ask if unclear
- Make implementation decisions based on SwiftUI best practices and existing sidebar patterns
