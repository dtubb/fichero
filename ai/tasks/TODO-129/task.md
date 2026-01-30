# TODO-129: Add Folder Support to Workflows Sidebar

## What to do
Enable folder organization in the Workflows sidebar (similar to Library sidebar), allowing users to organize workflows and chains into folders for better management.

## Steps
- [ ] Step 1: Verify backend WorkflowDefinition already has `folderPath` field
- [ ] Step 2: Update `SidebarItemBuilder` to build folder hierarchy for workflows (similar to documents)
- [ ] Step 3: Update `WorkflowsSidebarContent` to display hierarchical folder structure
- [ ] Step 4: Add folder creation support in workflows sidebar
- [ ] Step 5: Update workflow creation to allow parent folder selection
- [ ] Step 6: Enable drag-and-drop to move workflows between folders
- [ ] Step 7: Test folder operations (create, rename, delete, move items)

## Files
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/workflows/types.py` (verify WorkflowDefinition.folderPath)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Models/SidebarItemBuilder.swift` (add buildWorkflowsGroup)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Views/Sidebar/Modes/WorkflowsSidebarContent.swift` (display hierarchy)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Services/WorkflowStore.swift` (folder operations)

## Questions for Human
- [ ] Question 1: Should chains also support folders, or just workflows?
    Answer: Both workflows and chains should support folders - they're similar organizational units
- [ ] Question 2: Should folders be shared across libraries or per-library?
    Answer: Per-library - workflows belong to specific libraries
- [ ] Question 3: Should there be a default "Uncategorized" folder or use root level?
    Answer: Use root level (folderPath: "/") - simpler, matches document model

## Implementation Notes

### Backend Support (Already Exists)
```python
# src/fichero/workflows/types.py
@dataclass
class WorkflowDefinition:
    id: str
    name: str
    description: str
    provider: str
    model: str
    nodes: List[NodeDef]
    edges: List[EdgeDef]
    folderPath: str = "/"      # Already exists!
    sortOrder: int = 0
```

Backend already supports `folderPath` - just need to use it in frontend.

### Frontend Changes Needed

#### 1. SidebarItemBuilder Enhancement
Add `buildWorkflowsGroup()` function similar to `buildLibraryGroup()`:

```swift
static func buildWorkflowsGroup(workflows: [WorkflowSidebarItem], chains: [WorkflowChain]) -> [SidebarItem] {
    var items: [SidebarItem] = []

    // Build folder hierarchy for workflows
    let workflowTree = buildFolderHierarchy(
        items: workflows,
        getPath: { $0.folderPath },
        createItem: { SidebarItem.fromWorkflow($0) }
    )
    items.append(contentsOf: workflowTree)

    // Build folder hierarchy for chains (if they support folderPath)
    let chainTree = buildFolderHierarchy(
        items: chains,
        getPath: { $0.folderPath ?? "/" },
        createItem: { SidebarItem.fromChain($0) }
    )
    items.append(contentsOf: chainTree)

    return items
}
```

#### 2. WorkflowsSidebarContent Update
Replace flat list with hierarchical display:

```swift
// Current (flat):
ForEach(workflowItems) { item in
    SidebarItemRow(...)
}

// Target (hierarchical):
ForEach(cachedWorkflowItems) { item in  // Now includes folders
    SidebarItemRow(...)
}
```

#### 3. Folder Creation
Add folder creation to workflows context:

```swift
func createWorkflowFolder(_ name: String) async {
    // Use WorkflowStore to create folder metadata
    // Or reuse document collection folders (simpler)
}
```

### Chain Support
Check if `WorkflowChain` model has `folderPath`:
- If yes: Use it for hierarchy
- If no: Add it to backend model first

## Visual Comparison

**Before:**
```
Global
  Workflows (5)
    Workflow A
    Workflow B
    Workflow C
  Chains (2)
    Chain X
    Chain Y
```

**After:**
```
Global
  Workflows
    📁 Import Workflows
      Workflow A
      Workflow B
    📁 Reports
      Workflow C
    Workflow D (root level)
  Chains
    📁 Processing
      Chain X
    Chain Y (root level)
```

## Need help?
- Verify chain model has folderPath field
- Confirm folder creation should use DocumentStore collections or separate workflow folders
- Test drag-and-drop between folders
