# Xcode Project Reorganization Steps

**Purpose:** Reorganize files into proper folders (to be done manually in Xcode GUI)

## Files to Move

### From Models/ to Services/
1. `DocumentStore.swift` → `Services/DocumentStore.swift`
2. `WorkflowStore.swift` → `Services/WorkflowStore.swift`

### From Models/ to Utilities/ (create new group)
1. `SidebarItemBuilder.swift` → `Utilities/SidebarItemBuilder.swift`
2. `WorkflowExporter.swift` → `Utilities/WorkflowExporter.swift`

### Keep in Models/ (these are actual data models)
- `Document.swift` ✅
- `Provider.swift` ✅
- `Workflow.swift` ✅
- `WorkflowTypes.swift` ✅
- `SidebarItem.swift` ✅
- `SidebarState.swift` ✅
- `DragDropModel.swift` ✅
- `ErrorModel.swift` ✅

## Steps in Xcode

1. Open `Fichero.xcodeproj` in Xcode
2. In Project Navigator, create new groups:
   - Right-click on `Fichero` folder → New Group → name it `Utilities`
3. Drag and drop files:
   - `DocumentStore.swift` from Models → Services
   - `WorkflowStore.swift` from Models → Services
   - `SidebarItemBuilder.swift` from Models → Utilities
   - `WorkflowExporter.swift` from Models → Utilities
4. Build (⌘B) to verify everything compiles
5. Commit changes

## Why This Needs Xcode GUI

The `.xcodeproj` file is a complex property list that tracks:
- File UUIDs
- Build phases
- Group hierarchies
- File references

Editing it programmatically risks corruption. Xcode's GUI safely updates all references.

## After Reorganization

Once complete, the folder structure will match:

```
Models/           # Pure data models
Services/         # ObservableObject services
Utilities/        # Pure functions, builders
App/              # App-level state
Views/            # SwiftUI views
```
