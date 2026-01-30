# Creating Items and Folders - User Guide

**Date**: January 1, 2026
**Status**: Current implementation + Needed enhancements

---

## What's Already Implemented ✅

### Creating New Items

The sidebar already has "+" buttons for creating new items:

#### 1. **New Search** (⌘N when in Searches section)
- **Location**: Bottom of Searches section
- **Button**: "New Search..." with plus icon
- **What it does**: Switches to search view with empty search (viewMode = .search(nil))
- **How it saves**: Currently just switches view - **needs backend integration**

#### 2. **New Chat** (⌘N when in Chat section)
- **Location**: Bottom of Chat section
- **Button**: "New Chat..." with plus icon (also accepts document drops)
- **What it does**: Switches to chat view with new conversation (viewMode = .chat(nil))
- **How it saves**: Currently just switches view - **needs backend integration**

#### 3. **New Workflow** (⌘N when in Workflows section)
- **Location**: Bottom of Workflows section
- **Button**: "New Workflow..." with plus icon
- **What it does**: Switches to workflow editor with empty workflow (viewMode = .workflow(nil))
- **How it saves**: Currently just switches view - **needs backend integration**

### Creating Folders (Documents Only)

#### **New Folder** (⌘⇧N)
- **Location**: Toolbar button in sidebar
- **Icon**: folder.badge.plus
- **What it does**: Creates a new folder in the Library section
- **Implementation**: `handleCreateNewFolder()` in SidebarView.swift:408
- **Saves to**: DocumentStore backend
- **Limitation**: **Only works for Documents**, not for Searches/Chats/Workflows

---

## What's Missing ❌

### 1. Backend Integration for Creating Items

Currently, the "New Search/Chat/Workflow" buttons just switch views but don't actually create and save the items. They need to:

**For New Search**:
```swift
private func createNewSearch() {
    Task {
        do {
            // Create a new saved search in backend
            let newSearch = try await savedSearchService.saveSearch(
                query: "Untitled Search",
                isSmartSearch: true
            )

            // Convert to local model and refresh
            await savedSearchService.loadSavedSearches()

            // Switch to search view
            viewMode = .search(SavedSearch(
                id: newSearch.id,
                name: newSearch.query,
                query: newSearch.query,
                filters: SearchFilters(),
                isSmartSearch: newSearch.isSmartSearch,
                folderPath: newSearch.folderPath,
                sortOrder: newSearch.sortOrderInt
            ))
        } catch {
            logger.error("Failed to create new search: \(error)")
        }
    }
}
```

**For New Chat**:
```swift
private func createNewChat() {
    // The chat view will create the conversation when first message is sent
    // Current implementation is fine - no changes needed
    viewMode = .chat(nil)
}
```

**For New Workflow**:
```swift
private func createNewWorkflow() {
    Task {
        do {
            // Create a new workflow in backend
            let newWorkflow = try await workflowStore.workflowService.createWorkflow(
                WorkflowDefinition(
                    name: "Untitled Workflow",
                    description: "",
                    nodes: [],
                    edges: []
                )
            )

            // Refresh workflows
            await workflowStore.loadWorkflows()

            // Switch to workflow editor
            // ... (need to convert response to WorkflowSidebarItem)
        } catch {
            logger.error("Failed to create new workflow: \(error)")
        }
    }
}
```

### 2. Folder Creation for Searches/Chats/Workflows

Currently there's NO UI to create folders for these sections. Need to add:

#### Option A: Context Menu on Section Header

Add a context menu to each section header (Searches, Chat, Workflows):

```swift
.contextMenu {
    Button(action: { createFolder(in: .searches) }) {
        Label("New Folder", systemImage: "folder.badge.plus")
    }
}
```

#### Option B: Toolbar Button (Per Section)

Make the toolbar "New Folder" button context-aware:

```swift
func handleCreateNewFolder() {
    // Detect which section is active
    switch viewMode.sidebarSection {
    case .library:
        // Current implementation (create document folder)
        createDocumentFolder()

    case .searches:
        // NEW: Create search folder
        createSearchFolder()

    case .chat:
        // NEW: Create chat folder
        createChatFolder()

    case .workflows:
        // NEW: Create workflow folder
        createWorkflowFolder()
    }
}
```

#### Option C: Context Menu on Items

Add "New Folder Here" to item context menus:

```swift
.contextMenu {
    // ... existing menu items ...

    Divider()

    Button(action: { createFolderAt(item.folderPath) }) {
        Label("New Subfolder", systemImage: "folder.badge.plus")
    }
}
```

---

## Recommended Implementation Plan

### Phase 1: Fix "New Item" Buttons (High Priority)

**Files to modify**:
- `SidebarView.swift` - Update `createNewSearch()` and `createNewWorkflow()`

**Changes**:
1. Make "New Search" actually create and save a search to backend
2. Make "New Workflow" actually create and save a workflow to backend
3. Keep "New Chat" as-is (chat created on first message)

### Phase 2: Add Folder Creation UI (Medium Priority)

**Option**: Use Section Header Context Menus (cleanest UX)

**Files to modify**:
- `SidebarView.swift` - Add context menus to section headers

**Implementation**:
```swift
// In searchSectionView
.contextMenu {
    Button(action: { createSearchFolder() }) {
        Label("New Folder", systemImage: "folder.badge.plus")
    }
}
```

**Create Helper Functions**:
```swift
private func createSearchFolder() {
    Task {
        // Prompt user for folder name
        let folderName = await promptForFolderName()
        guard !folderName.isEmpty else { return }

        // Determine parent path based on selection
        let parentPath = currentSearchFolderPath() ?? "/"
        let newPath = parentPath == "/" ? "/\(folderName)" : "\(parentPath)/\(folderName)"

        // Create folder in backend (implicit via creating item)
        // OR use folder management API:
        // try await api.post("/folders/search/folders?folder_path=\(newPath)")

        // For now, just create a placeholder search in that folder
        try await savedSearchService.saveSearch(
            query: folderName,
            isSmartSearch: false,
            folderPath: newPath
        )

        await savedSearchService.loadSavedSearches()
    }
}
```

### Phase 3: Folder Management (Low Priority)

Add context menu items for folders:
- **Rename Folder** - Changes folder_path for all items in that folder
- **Delete Folder** - Uses `/api/folders/{type}/folders` DELETE endpoint
- **Move Folder** - Drag & drop between folders

---

## Quick Start: Minimal Changes Needed

To get basic functionality working, you need **2 small changes**:

### 1. Fix "New Search" Button

**File**: `Fichero/Views/Sidebar/SidebarView.swift:345`

**Change**:
```swift
private func createNewSearch() {
    Task {
        do {
            let search = try await savedSearchService.saveSearch(
                query: "Untitled Search"
            )
            await savedSearchService.loadSavedSearches()
            logger.info("Created new search: \(search.id)")
        } catch {
            logger.error("Failed to create search: \(error)")
        }
    }
}
```

### 2. Fix "New Workflow" Button

**File**: `Fichero/Views/Sidebar/SidebarView.swift:355`

**Change**:
```swift
private func createNewWorkflow() {
    Task {
        do {
            let workflow = try await workflowStore.workflowService.createWorkflow(
                WorkflowDefinition(
                    name: "Untitled Workflow",
                    description: "",
                    nodes: [],
                    edges: []
                )
            )
            await workflowStore.loadWorkflows()
            logger.info("Created new workflow: \(workflow.id)")
        } catch {
            logger.error("Failed to create workflow: \(error)")
        }
    }
}
```

### 3. Add Folder Creation (Optional but Recommended)

For now, users can create folders by:
1. Creating a search/chat/workflow
2. Renaming it to include a folder path like "Archive/2024/Query"
3. The system will parse the path and create the folder structure

**Better approach**: Add a simple dialog:

```swift
private func createSearchFolder() {
    // Show dialog for folder name
    let alert = NSAlert()
    alert.messageText = "New Folder"
    alert.informativeText = "Enter folder name:"
    alert.alertStyle = .informational
    alert.addButton(withTitle: "Create")
    alert.addButton(withTitle: "Cancel")

    let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 200, height: 24))
    input.placeholderString = "Folder Name"
    alert.accessoryView = input

    if alert.runModal() == .alertFirstButtonReturn {
        let folderName = input.stringValue
        Task {
            // Create a dummy search in this folder to establish it
            try await savedSearchService.saveSearch(
                query: ".folder",  // Hidden search
                folderPath: "/\(folderName)"
            )
            await savedSearchService.loadSavedSearches()
        }
    }
}
```

---

## Summary

### Current State
✅ Buttons exist for creating searches, chats, workflows
✅ Toolbar button exists for creating document folders
✅ Backend API supports all operations
❌ New item buttons don't save to backend
❌ No folder creation UI for searches/chats/workflows

### Minimum Viable Solution
1. Make "New Search" and "New Workflow" buttons actually create items (2 function changes)
2. Document that users can create folders by including "/" in item names
3. Add proper folder UI in next iteration

### Full Solution
1. Fix new item buttons to save to backend
2. Add section header context menus for folder creation
3. Add folder management (rename, delete, move)
4. Add folder dialog with path preview
