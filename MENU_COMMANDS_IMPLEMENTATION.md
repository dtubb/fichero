# Menu Commands Implementation Plan

**Goal**: Add proper macOS menu bar commands, toolbar buttons, and context menus for creating searches, chats, workflows, and folders.

---

## Current State

### ✅ What Exists
- **@FocusedValue system** - Connects menu commands to focused views
- **SidebarActions** - Has `createFolder`, `importFiles`, `renameItem`, `deleteItem`
- **Menu Commands in FicheroApp.swift**:
  - File > New Library (⌘N)
  - File > New Folder (⌘⇧N)
  - File > Import Files or Folders... (⌘I)
  - Edit > Rename (Return)
  - Edit > Delete (⌘⌫)

### ❌ What's Missing
- Menu commands for New Search, New Chat, New Workflow
- Context-aware toolbar buttons
- Right-click context menus for sections

---

## Implementation Plan

### Step 1: Extend SidebarActions

**File**: `Fichero/Views/Menu/FocusedCommandButtons.swift`

**Add new actions**:
```swift
struct SidebarActions {
    let createFolder: () -> Void
    let importFiles: () -> Void
    let renameItem: () -> Void
    let deleteItem: () -> Void

    // NEW ACTIONS
    let createSearch: (() -> Void)?      // Optional - only available in Searches section
    let createChat: (() -> Void)?        // Optional - only available in Chat section
    let createWorkflow: (() -> Void)?    // Optional - only available in Workflows section
}
```

### Step 2: Create Focused Buttons

**File**: `Fichero/Views/Menu/FocusedCommandButtons.swift`

**Add at end of file**:
```swift
/// Button that creates a new search
struct FocusedNewSearchButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Search") {
            sidebarActions?.createSearch?()
        }
        .keyboardShortcut("n", modifiers: [.command, .option])
        .disabled(sidebarActions?.createSearch == nil)
    }
}

/// Button that creates a new chat
struct FocusedNewChatButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Chat") {
            sidebarActions?.createChat?()
        }
        .keyboardShortcut("n", modifiers: [.command, .control])
        .disabled(sidebarActions?.createChat == nil)
    }
}

/// Button that creates a new workflow
struct FocusedNewWorkflowButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Workflow") {
            sidebarActions?.createWorkflow?()
        }
        .keyboardShortcut("n", modifiers: [.command, .control, .shift])
        .disabled(sidebarActions?.createWorkflow == nil)
    }
}
```

### Step 3: Add Menu Commands

**File**: `Fichero/FicheroApp.swift`

**Modify the CommandGroup**:
```swift
// File menu
CommandGroup(replacing: .newItem) {
    Button("New Library") {
        handleNewLibrary()
    }
    .keyboardShortcut("n", modifiers: [.command])

    FocusedNewWindowButton()

    Divider()

    // NEW: Context-aware "New" commands
    FocusedNewSearchButton()       // ⌘⌥N - New Search
    FocusedNewChatButton()          // ⌘⌃N - New Chat
    FocusedNewWorkflowButton()      // ⌘⌃⇧N - New Workflow

    Divider()

    FocusedOpenLibraryButton()

    Divider()

    FocusedSaveLibraryButton()

    Divider()

    FocusedNewFolderButton()        // ⌘⇧N - New Folder

    FocusedImportFilesButton()       // ⌘I - Import
}
```

### Step 4: Implement Actions in SidebarView

**File**: `Fichero/Views/Sidebar/SidebarView.swift`

**Update the focusedValue**:
```swift
// Around line 100, update the existing .focusedValue
.focusedValue(\.sidebarActions, SidebarActions(
    createFolder: handleCreateNewFolder,
    importFiles: importFiles,
    renameItem: renameState.startRenaming,
    deleteItem: deleteState.requestDeletion,
    // NEW: Context-aware actions
    createSearch: viewMode.sidebarSection == .searches ? createNewSearch : nil,
    createChat: viewMode.sidebarSection == .chat ? createNewChat : nil,
    createWorkflow: viewMode.sidebarSection == .workflows ? createNewWorkflow : nil
))
```

**Update the create functions** (already exists, just need to make them save):
```swift
/// Creates a new search and saves it to backend
private func createNewSearch() {
    Task {
        do {
            let search = try await savedSearchService.saveSearch(
                query: "Untitled Search",
                isSmartSearch: true
            )

            // Reload searches to show new item
            await savedSearchService.loadSavedSearches()

            // Switch to the new search
            viewMode = .search(SavedSearch(
                id: search.id,
                name: search.query,
                query: search.query,
                filters: SearchFilters(),
                isSmartSearch: search.isSmartSearch,
                folderPath: search.folderPath,
                sortOrder: search.sortOrderInt
            ))

            logger.info("Created new search: \(search.id)")
        } catch {
            logger.error("Failed to create search: \(error)")
        }
    }
}

/// Creates a new chat conversation
private func createNewChat() {
    // Chat is created when first message is sent
    // Just switch to empty chat view
    viewMode = .chat(nil)
}

/// Creates a new workflow and saves it to backend
private func createNewWorkflow() {
    Task {
        do {
            let workflow = try await workflowStore.workflowService.createWorkflow(
                WorkflowDefinition(
                    name: "Untitled Workflow",
                    description: "",
                    provider: "",
                    model: "",
                    nodes: [],
                    edges: []
                )
            )

            // Reload workflows
            await workflowStore.loadWorkflows()

            logger.info("Created new workflow: \(workflow.id)")

            // Switch to workflow editor (need to find the workflow in store)
            // For now, just reload - the workflow will appear in sidebar
        } catch {
            logger.error("Failed to create workflow: \(error)")
        }
    }
}
```

### Step 5: Add Context Menus

**File**: `Fichero/Views/Sidebar/SidebarView.swift`

**Add context menus to section headers**:
```swift
// In searchSectionView (around line 222)
} header: {
    SidebarSectionHeader(title: "Searches", icon: "magnifyingglass")
        .background(isSearchHeaderDropTargeted ? Color.accentColor.opacity(0.2) : Color.clear)
        .cornerRadius(4)
        .contextMenu {                    // NEW
            Button(action: createNewSearch) {
                Label("New Search", systemImage: "plus")
            }
            Button(action: { createFolderInSection(.searches) }) {
                Label("New Folder", systemImage: "folder.badge.plus")
            }
        }
        .dropDestination(for: String.self) { itemIDs, _ in
            handleSearchHeaderDrop(itemIDs: itemIDs)
        } isTargeted: { isTargeted in
            isSearchHeaderDropTargeted = isTargeted
        }
}

// Repeat for chatSectionView and workflowsSectionView
```

**Add folder creation helper**:
```swift
private func createFolderInSection(_ section: SidebarSection) {
    // Show dialog for folder name
    let alert = NSAlert()
    alert.messageText = "New Folder"
    alert.informativeText = "Enter folder name for \(section.rawValue):"
    alert.alertStyle = .informational
    alert.addButton(withTitle: "Create")
    alert.addButton(withTitle: "Cancel")

    let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 200, height: 24))
    input.placeholderString = "Folder Name"
    alert.accessoryView = input

    if alert.runModal() == .alertFirstButtonReturn {
        let folderName = input.stringValue.trimmingCharacters(in: .whitespaces)
        guard !folderName.isEmpty else { return }

        Task {
            do {
                let folderPath = "/\(folderName)"

                switch section {
                case .searches:
                    // Create a placeholder search in this folder
                    _ = try await savedSearchService.saveSearch(
                        query: ".folder-\(folderName)",
                        isSmartSearch: false,
                        folderPath: folderPath
                    )
                    await savedSearchService.loadSavedSearches()

                case .chat:
                    // Can't create empty folders yet - need backend support
                    logger.warning("Chat folder creation not yet implemented")

                case .workflows:
                    // Create a placeholder workflow in this folder
                    _ = try await workflowStore.workflowService.createWorkflow(
                        WorkflowDefinition(
                            name: ".folder-\(folderName)",
                            description: "Folder placeholder",
                            provider: "",
                            model: "",
                            nodes: [],
                            edges: []
                        )
                    )
                    await workflowStore.loadWorkflows()

                case .library:
                    // Use existing document folder creation
                    handleCreateNewFolder()
                }

                logger.info("Created folder in \(section.rawValue): \(folderPath)")
            } catch {
                logger.error("Failed to create folder: \(error)")
            }
        }
    }
}
```

### Step 6: Update Toolbar

**File**: `Fichero/Views/Sidebar/SidebarViewExtensions.swift`

**Make toolbar context-aware**:
```swift
func sidebarToolbar(
    createFolder: @escaping () -> Void,
    importFiles: @escaping () -> Void,
    createSearch: @escaping () -> Void,     // NEW
    createChat: @escaping () -> Void,       // NEW
    createWorkflow: @escaping () -> Void    // NEW
) -> some View {
    self.toolbar {
        ToolbarItemGroup(placement: .automatic) {
            // Context-aware "New" button
            Menu {
                Button(action: createFolder) {
                    Label("New Folder", systemImage: "folder.badge.plus")
                }

                Divider()

                Button(action: createSearch) {
                    Label("New Search", systemImage: "magnifyingglass")
                }

                Button(action: createChat) {
                    Label("New Chat", systemImage: "bubble.left.and.bubble.right")
                }

                Button(action: createWorkflow) {
                    Label("New Workflow", systemImage: "arrow.triangle.branch")
                }
            } label: {
                Label("New", systemImage: "plus")
            }
            .help("New Item (⌘N)")

            Button(action: importFiles) {
                Image(systemName: "square.and.arrow.down")
            }
            .help("Import Files or Folders (⌘I)")
        }
    }
}
```

**Update call site in SidebarView**:
```swift
.sidebarToolbar(
    createFolder: handleCreateNewFolder,
    importFiles: importFiles,
    createSearch: createNewSearch,      // NEW
    createChat: createNewChat,          // NEW
    createWorkflow: createNewWorkflow   // NEW
)
```

---

## Keyboard Shortcuts Summary

| Command | Shortcut | Context |
|---------|----------|---------|
| New Library | ⌘N | Global |
| New Search | ⌘⌥N | When Searches section active |
| New Chat | ⌘⌃N | When Chat section active |
| New Workflow | ⌘⌃⇧N | When Workflows section active |
| New Folder | ⌘⇧N | Context-aware per section |
| Import | ⌘I | Global |
| Rename | Return | When item selected |
| Delete | ⌘⌫ | When item selected |

---

## Implementation Checklist

### Phase 1: Menu Commands (High Priority) ✅ COMPLETE
- [x] Update `SidebarActions` struct with optional create actions
- [x] Create `FocusedNewSearchButton`, `FocusedNewChatButton`, `FocusedNewWorkflowButton`
- [x] Add buttons to File menu in `FicheroApp.swift`
- [x] Update `SidebarView` focusedValue to provide context-aware actions
- [x] Fix `createNewSearch()` to save to backend
- [x] Fix `createNewWorkflow()` to save to backend

**Status**: Phase 1 complete! See `MENU_COMMANDS_PHASE1_COMPLETE.md` for details.

### Phase 2: Context Menus (Medium Priority) ✅ COMPLETE
- [x] Add context menu to Searches section header
- [x] Add context menu to Chat section header
- [x] Add context menu to Workflows section header
- [x] Implement `createFolderInSection()` helper function (placeholder)

**Status**: Phase 2 complete!

### Phase 3: Bottom Toolbar (Low Priority) ✅ COMPLETE
- [x] Create compact bottom toolbar (28px, macOS-style)
- [x] Add "+" dropdown menu with all create options
- [x] Add import button
- [x] Use material background for native look
- [x] Replace top toolbar with bottom toolbar

**Status**: Phase 3 complete! See `MENU_TOOLBAR_COMPLETE.md` for full details.

---

## Testing

After implementation, verify:
1. ✅ File > New Search creates and saves a search
2. ✅ File > New Chat switches to chat view
3. ✅ File > New Workflow creates and saves a workflow
4. ✅ Keyboard shortcuts work (⌘⌥N, ⌘⌃N, ⌘⌃⇧N)
5. ✅ Right-click on section headers shows context menu
6. ✅ Context menu "New Folder" creates folder
7. ✅ Toolbar "+" menu shows all options
8. ✅ Commands disabled when section not active

---

## Next Steps After Implementation

1. **Add folder management to context menus**:
   - Rename folder (updates all items in folder)
   - Delete folder (moves items to parent or deletes)
   - Move folder (drag & drop)

2. **Add smart folder creation**:
   - Detect when user types "/" in name
   - Auto-create parent folders
   - Show folder path preview

3. **Add folder icons and badges**:
   - Different icons for folder vs item
   - Item count badges on folders
   - Smart folder indicators
