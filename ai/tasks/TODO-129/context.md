# Context: Workflow Folder Support

## Problem
Currently, workflows and chains are displayed in flat lists in the Workflows sidebar, making organization difficult as the number of workflows grows. Users cannot:
- Group related workflows into folders
- Create folder hierarchies
- Move workflows between folders

## User Request
> "I'd like to be able to put workflows in folders."

## Current Architecture

### Backend Support
The backend already has folder support:
- `WorkflowDefinition` has `folderPath: str = "/"` field
- Workflows can be stored with folder paths like "/Import Workflows/PDF"
- Backend just needs to be told which folder to use when creating/updating

### Frontend Gap
The frontend displays workflows in a flat list:
```swift
// WorkflowsSidebarContent.swift
let workflowItems = workflows.map { workflow in
    SidebarItem.fromWorkflow(workflow, libraryId: library.id)
}

ForEach(workflowItems) { item in
    SidebarItemRow(...)
}
```

No hierarchy building - just direct mapping.

### How Library Sidebar Does It
The Library sidebar builds folder hierarchies:

```swift
// SidebarItemBuilder.swift - buildLibraryGroup()
static func buildLibraryGroup(library: LibraryManager.LibraryReference) -> [SidebarItem] {
    let documents = library.documentStore.rootDocuments
    let collections = library.documentStore.collections

    // Build folder nodes from collections
    var folderItems: [SidebarItem] = collections.map { collection in
        SidebarItem.folder(
            name: collection.name,
            path: collection.path,
            children: [] // Filled recursively
        )
    }

    // Build document items
    let docItems = documents.map { SidebarItem.fromDocument($0) }

    // Combine and organize hierarchically
    return buildHierarchy(folders: folderItems, items: docItems)
}
```

## Solution Architecture

### Reuse Hierarchy Building
Use the same pattern as Library sidebar:
1. Parse `folderPath` from workflows
2. Build folder structure
3. Place workflows under their folders

### Folder Storage Options

#### Option A: Reuse DocumentStore Collections
Pros:
- Already exists
- Proven folder creation/management
- Shared folders between docs and workflows

Cons:
- Conceptual mixing (documents vs workflows)
- Potential naming conflicts

#### Option B: Separate Workflow Folders
Pros:
- Clean separation
- Workflow-specific metadata possible

Cons:
- Need backend support
- More complex implementation

**Recommendation**: Start with Option A (reuse collections) for speed, migrate to Option B if needed.

### Code Structure

```swift
// SidebarItemBuilder.swift
static func buildWorkflowsGroup(
    workflows: [WorkflowSidebarItem],
    chains: [WorkflowChain],
    collections: [Collection]
) -> [SidebarItem] {
    // Build folder hierarchy from collections
    // Place workflows/chains under matching folderPath
    // Return combined tree
}
```

### Folder Operations

**Create Folder:**
```swift
func createWorkflowFolder(name: String, parentPath: String) async {
    let collection = try await documentStore.createCollection(
        name: name,
        parentPath: parentPath
    )
    // Refresh sidebar
}
```

**Move Workflow to Folder:**
```swift
func moveWorkflow(id: String, toFolder: String) async {
    let workflow = try await workflowStore.getWorkflow(id)
    workflow.folderPath = toFolder
    try await workflowStore.updateWorkflow(workflow)
    // Refresh sidebar
}
```

## Related Patterns

### How Other Apps Do It
- **Xcode**: Project navigator shows groups (folders)
- **Finder**: Hierarchical folder view
- **Notes.app**: Folders for organizing notes
- **Hazel**: Rules organized in folders

All use expandable/collapsible disclosure groups with indent.

## Benefits
1. **Scalability**: Handle dozens of workflows without clutter
2. **Organization**: Group by purpose (Import, Export, Reports, etc.)
3. **Consistency**: Matches Library sidebar UX
4. **Discoverability**: Folders provide categorization

## Edge Cases
- What if workflow has `folderPath: "/Import/PDF"` but folder doesn't exist?
  - Auto-create missing folders OR show at root with warning
- What if user deletes folder with workflows?
  - Move workflows to root OR delete with folder (with confirmation)
- How to handle chain folders if chains don't have folderPath?
  - Add folderPath to chain model OR keep chains flat

## Testing Considerations
- Create folders in workflows sidebar
- Move workflows between folders via drag-and-drop
- Rename folders (workflows should update folderPath)
- Delete folders (confirm handling of contained workflows)
- Multi-library support (folders per library)
