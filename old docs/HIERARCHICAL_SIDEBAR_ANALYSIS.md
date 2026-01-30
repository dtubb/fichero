# Hierarchical Sidebar Analysis

**Date**: December 31, 2025
**Task**: Enable hierarchical organization for Searches, Chats, and Workflows in Sidebar
**Status**: Backend 60% Complete, Frontend 0% Complete

---

## Executive Summary

The backend **already supports** hierarchical organization for Searches, Chats, and Workflows through `folder_path` and `sort_order` fields in the data models. However:

1. **Conversations are not persisted** (in-memory only)
2. **Workflow CRUD endpoints are missing** (only execution endpoint exists)
3. **Folder management endpoints are missing** (create/rename/move/delete folders)
4. **Frontend sidebar doesn't use hierarchical structure** yet

---

## Current Backend State

### ✅ Data Models (Complete)

All three entity types have hierarchical support built-in:

**`Workflow` (models.py:413-414)**:
```python
folder_path: str = "/"  # Unix-style path: "/archive/letters"
sort_order: int = 0     # User-defined order within folder
```

**`SavedSearch` (models.py:739-740)**:
```python
folder_path: str = "/"  # Unix-style path for organization
sort_order: int = 0     # User-defined order within folder
```

**`Conversation` (models.py:767-768)**:
```python
folder_path: str = "/"  # Unix-style path for organization
sort_order: int = 0     # User-defined order within folder
```

### ✅ Database Migrations (Complete)

**Workflows Table** (db.py:1016-1022):
- Migration adds `folder_path` and `sort_order` columns
- Runs automatically on database init
- Existing workflows default to `folder_path="/"`, `sort_order=0`

**SavedSearches Table** (db.py:1083-1095):
- Migration adds `folder_path` and `sort_order` columns
- Runs automatically on database init

### ⚠️ API Endpoints (Partial)

#### **SavedSearch** (BEST - 80% Complete)

**Existing endpoints** (`api/routes/search.py`):
- ✅ `POST /api/search/saved` - Save new search
- ✅ `GET /api/search/saved` - List all saved searches
- ✅ `DELETE /api/search/saved/{id}` - Delete search
- ✅ `POST /api/search/saved/{id}/duplicate` - Duplicate search
- ✅ `POST /api/search/saved/reorder` - Reorder searches within folder
  - Accepts `folder_path` parameter (line 282)
  - Updates `sort_order` for each search (lines 291-292)

**Missing**:
- ❌ `PUT /api/search/saved/{id}` - Update search (change name, folder, filters)
- ❌ Folder management endpoints (create/rename/move/delete)

#### **Conversation** (NEEDS WORK - 30% Complete)

**Current implementation** (`api/routes/chat.py`):
- ⚠️ **In-memory storage only** (line 107: `_conversations: dict[str, dict] = {}`)
- ✅ `POST /api/chat` - Send message (creates/updates conversation)
- ✅ `GET /api/chat/conversations` - List conversations (accepts `folder_path` filter, line 309)
- ✅ `GET /api/chat/conversations/{id}` - Get conversation history
- ✅ `DELETE /api/chat/conversations/{id}` - Delete conversation
- ✅ `POST /api/chat/conversations/{id}/duplicate` - Duplicate conversation
- ✅ `POST /api/chat/conversations/reorder` - Reorder (accepts `folder_path`, line 389)

**Critical Issues**:
1. ❌ **Conversations NOT persisted to database** - lost on server restart
2. ❌ `folder_path` and `sort_order` hardcoded to `"/"` and `0` (lines 323-324)
3. ❌ No update endpoint to move conversations between folders

**Required**:
- Persist conversations to database using `Conversation` model
- Add `PUT /api/chat/conversations/{id}` - Update conversation (title, folder_path)
- Folder management endpoints

#### **Workflow** (MISSING - 10% Complete)

**Current implementation** (`api/routes/workflows.py`):
- ✅ `POST /api/workflows/run` - Execute workflow (doesn't save definition)
- ✅ `GET /api/workflows/tools` - List available tools
- ❌ **NO CRUD endpoints** - Cannot list, save, update, or delete workflows
- ❌ No folder management endpoints

**Required**:
- `POST /api/workflows` - Create workflow
- `GET /api/workflows` - List all workflows (filter by folder_path)
- `GET /api/workflows/{id}` - Get workflow definition
- `PUT /api/workflows/{id}` - Update workflow (name, definition, folder_path)
- `DELETE /api/workflows/{id}` - Delete workflow
- `POST /api/workflows/{id}/duplicate` - Duplicate workflow
- `POST /api/workflows/reorder` - Reorder workflows within folder
- Folder management endpoints

---

## Missing: Folder Management Endpoints

**None of the routes have folder operations**. Need to add to all three:

### Required Endpoints (for each entity type)

**1. List Folders**:
```
GET /api/{entity}/folders?parent_path=/
Returns: List of unique folder paths under parent
```

**2. Create Folder**:
```
POST /api/{entity}/folders
Body: { "folder_path": "/archive/letters" }
Returns: { "folder_path": "/archive/letters", "item_count": 0 }
```

**3. Rename Folder**:
```
PUT /api/{entity}/folders
Body: { "old_path": "/archive", "new_path": "/Archive 2024" }
Returns: { "moved_count": 5 }
```

**4. Move Items**:
```
PUT /api/{entity}/move
Body: { "item_ids": ["id1", "id2"], "folder_path": "/new/location" }
Returns: { "moved_count": 2 }
```

**5. Delete Folder**:
```
DELETE /api/{entity}/folders?folder_path=/archive&delete_contents=false
Returns: { "deleted_count": 0, "moved_to_root": 5 }
```

---

## Frontend State

### Current Sidebar Implementation

**Files**:
- `Fichero/Fichero/Views/Sidebar/SidebarView.swift` (691 lines)
- `Fichero/Fichero/Views/Sidebar/SidebarItemRow.swift` (482 lines)
- `Fichero/Fichero/Models/SidebarItem.swift`
- `Fichero/Fichero/Models/SidebarState.swift`

**Current Behavior**:
- ✅ **Navigate mode** - Hierarchical documents with folders (uses `Document.parent_id`)
- ❌ **Search mode** - Flat list of saved searches (ignores `folder_path`)
- ❌ **Chat mode** - Flat list of conversations (ignores `folder_path`)
- ❌ **Workflows mode** - Flat list of workflows (ignores `folder_path`)

### SidebarItem Model

**Current structure** (needs extension):
```swift
struct SidebarItem: Identifiable {
    let id: String
    let name: String
    let icon: String
    let type: SidebarItemType  // .document, .search, .chat, .workflow
    var children: [SidebarItem]?  // Only used for documents

    // Missing:
    // - folder_path: String
    // - sort_order: Int
    // - isFolder: Bool
}
```

---

## Implementation Plan

### Phase 1: Backend - Persist Conversations (P0)

**File**: `src/fichero/api/routes/chat.py`

**Changes**:
1. Remove in-memory `_conversations` dict (line 107)
2. Update all endpoints to use database:
   ```python
   from fichero.models import Conversation

   # Create
   conv = Conversation(
       title=request.message[:50],
       messages=[{"role": "user", "content": request.message}],
       folder_path="/",
       sort_order=0
   )
   db.save(conv)

   # List
   convs = db.query(Conversation, folder_path=folder_path)

   # Update
   conv = db.get(Conversation, conv_id)
   conv.messages.append({"role": "user", "content": request.message})
   conv.updated_at = datetime.now()
   db.save(conv)
   ```

**Estimate**: 1-2 hours

---

### Phase 2: Backend - Workflow CRUD Endpoints (P0)

**File**: `src/fichero/api/routes/workflows.py`

**Add endpoints**:
```python
from fichero.models import Workflow

@router.post("")
async def create_workflow(request: WorkflowCreate, db: Database = Depends(get_library_database)):
    workflow = Workflow(
        name=request.name,
        description=request.description,
        format=request.format,
        nodes=request.nodes,
        edges=request.edges,
        folder_path=request.folder_path or "/",
        sort_order=request.sort_order or 0
    )
    db.save(workflow)
    return workflow

@router.get("")
async def list_workflows(folder_path: str = "/", db: Database = Depends(get_library_database)):
    return db.query(Workflow, folder_path=folder_path)

@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str, db: Database = Depends(get_library_database)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow

@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, request: WorkflowUpdate, db: Database = Depends(get_library_database)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Update fields
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(workflow, field, value)

    workflow.updated_at = datetime.now()
    db.save(workflow)
    return workflow

@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, db: Database = Depends(get_library_database)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete(workflow)
    return {"status": "deleted"}

@router.post("/{workflow_id}/duplicate")
async def duplicate_workflow(workflow_id: str, db: Database = Depends(get_library_database)):
    original = db.get(Workflow, workflow_id)
    if not original:
        raise HTTPException(status_code=404, detail="Workflow not found")

    new_workflow = Workflow(
        name=f"{original.name} (Copy)",
        description=original.description,
        format=original.format,
        steps=original.steps[:],
        nodes=original.nodes[:],
        edges=original.edges[:],
        folder_path=original.folder_path,
        sort_order=original.sort_order
    )
    db.save(new_workflow)
    return new_workflow

@router.post("/reorder")
async def reorder_workflows(workflow_ids: list[str], folder_path: str = "/", db: Database = Depends(get_library_database)):
    for i, workflow_id in enumerate(workflow_ids):
        workflow = db.get(Workflow, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        workflow.sort_order = i
        db.save(workflow)
    return {"status": "reordered", "count": len(workflow_ids)}
```

**Estimate**: 2-3 hours

---

### Phase 3: Backend - Update Endpoints (P1)

**Files**:
- `src/fichero/api/routes/search.py`
- `src/fichero/api/routes/chat.py`

**Add missing update endpoints**:

**SavedSearch**:
```python
@router.put("/saved/{search_id}")
async def update_saved_search(
    search_id: str,
    request: SavedSearchUpdate,
    db: Database = Depends(get_library_database)
):
    saved = db.get(SavedSearch, search_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Saved search not found")

    # Update fields
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(saved, field, value)

    saved.updated_at = datetime.now()
    db.save(saved)
    return saved
```

**Conversation**:
```python
@router.put("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    db: Database = Depends(get_library_database)
):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Update fields (title, folder_path)
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(conv, field, value)

    conv.updated_at = datetime.now()
    db.save(conv)
    return conv
```

**Estimate**: 1 hour

---

### Phase 4: Backend - Folder Management (P1)

**Create new file**: `src/fichero/api/routes/folders.py`

**Generic folder operations** (works for all entity types):

```python
from enum import Enum
from fichero.models import Workflow, SavedSearch, Conversation

class EntityType(str, Enum):
    workflow = "workflow"
    search = "search"
    conversation = "conversation"

def _get_model_for_entity(entity_type: EntityType):
    mapping = {
        EntityType.workflow: Workflow,
        EntityType.search: SavedSearch,
        EntityType.conversation: Conversation
    }
    return mapping[entity_type]

@router.get("/{entity_type}/folders")
async def list_folders(
    entity_type: EntityType,
    parent_path: str = "/",
    db: Database = Depends(get_library_database)
):
    """List unique folder paths under parent."""
    model = _get_model_for_entity(entity_type)
    all_items = db.all(model)

    # Extract unique folders under parent
    folders = set()
    for item in all_items:
        path = item.folder_path
        if path.startswith(parent_path) and path != parent_path:
            # Get immediate child folder
            relative = path[len(parent_path):].lstrip('/')
            if '/' in relative:
                child_folder = parent_path.rstrip('/') + '/' + relative.split('/')[0]
            else:
                child_folder = path
            folders.add(child_folder)

    # Count items in each folder
    result = []
    for folder in sorted(folders):
        count = len([i for i in all_items if i.folder_path == folder])
        result.append({"path": folder, "item_count": count})

    return result

@router.post("/{entity_type}/folders")
async def create_folder(
    entity_type: EntityType,
    folder_path: str,
    db: Database = Depends(get_library_database)
):
    """Create a folder (just validates path format)."""
    if not folder_path.startswith('/'):
        raise HTTPException(status_code=400, detail="folder_path must start with '/'")

    # Count existing items in folder
    model = _get_model_for_entity(entity_type)
    items = db.query(model, folder_path=folder_path)

    return {"folder_path": folder_path, "item_count": len(items)}

@router.put("/{entity_type}/folders")
async def rename_folder(
    entity_type: EntityType,
    old_path: str,
    new_path: str,
    db: Database = Depends(get_library_database)
):
    """Rename a folder and all items within it."""
    model = _get_model_for_entity(entity_type)
    all_items = db.all(model)

    # Find all items in old path or its subfolders
    moved_count = 0
    for item in all_items:
        if item.folder_path == old_path or item.folder_path.startswith(old_path + '/'):
            # Update path
            item.folder_path = new_path + item.folder_path[len(old_path):]
            item.updated_at = datetime.now()
            db.save(item)
            moved_count += 1

    return {"moved_count": moved_count}

@router.put("/{entity_type}/move")
async def move_items(
    entity_type: EntityType,
    item_ids: list[str],
    folder_path: str,
    db: Database = Depends(get_library_database)
):
    """Move items to a different folder."""
    model = _get_model_for_entity(entity_type)

    moved_count = 0
    for item_id in item_ids:
        item = db.get(model, item_id)
        if item:
            item.folder_path = folder_path
            item.updated_at = datetime.now()
            db.save(item)
            moved_count += 1

    return {"moved_count": moved_count}

@router.delete("/{entity_type}/folders")
async def delete_folder(
    entity_type: EntityType,
    folder_path: str,
    delete_contents: bool = False,
    db: Database = Depends(get_library_database)
):
    """Delete a folder (optionally with contents)."""
    model = _get_model_for_entity(entity_type)
    items = db.query(model, folder_path=folder_path)

    if delete_contents:
        # Delete all items in folder
        for item in items:
            db.delete(item)
        return {"deleted_count": len(items), "moved_to_root": 0}
    else:
        # Move items to parent folder
        parent_path = '/'.join(folder_path.rstrip('/').split('/')[:-1]) or '/'
        for item in items:
            item.folder_path = parent_path
            db.save(item)
        return {"deleted_count": 0, "moved_to_root": len(items)}
```

**Register in main.py**:
```python
from fichero.api.routes import folders
app.include_router(folders.router, prefix="/api", tags=["folders"])
```

**Estimate**: 3-4 hours

---

### Phase 5: Frontend - Extend SidebarItem Model (P0)

**File**: `Fichero/Fichero/Models/SidebarItem.swift`

**Add hierarchical properties**:
```swift
struct SidebarItem: Identifiable, Hashable {
    let id: String
    let name: String
    let icon: String
    let type: SidebarItemType

    // Hierarchical support
    let folderPath: String  // Unix-style path: "/archive/letters"
    let sortOrder: Int      // User-defined order within folder
    let isFolder: Bool      // True for folder items, false for leaf items

    // Children (for hierarchical display)
    var children: [SidebarItem]?

    // Metadata (type-specific)
    var metadata: [String: Any]?  // e.g., search filters, workflow config
}

enum SidebarItemType: String, Codable {
    case document
    case folder
    case savedSearch
    case conversation
    case workflow
}
```

**Estimate**: 30 minutes

---

### Phase 6: Frontend - Update API Models (P0)

**Files**:
- `Fichero/Fichero/Models/Document.swift` (already has hierarchy)
- Create `Fichero/Fichero/Models/SavedSearch.swift`
- Create `Fichero/Fichero/Models/Conversation.swift`
- Update `Fichero/Fichero/Models/Workflow.swift`

**Example SavedSearch**:
```swift
struct SavedSearch: Identifiable, Codable {
    let id: String
    let query: String
    let isSmartSearch: Bool
    let filters: [String: Any]?
    let searchType: String
    let sortBy: String
    let sortOrder: String

    // Hierarchical
    let folderPath: String
    let sortOrder: Int

    let createdAt: Date
    let updatedAt: Date
}
```

**Estimate**: 1 hour

---

### Phase 7: Frontend - Update Services (P0)

**Files**:
- Create `Fichero/Fichero/Services/SavedSearchService.swift`
- Create `Fichero/Fichero/Services/ConversationService.swift`
- Update `Fichero/Fichero/Services/WorkflowService.swift`

**Example SavedSearchService**:
```swift
@MainActor
class SavedSearchService: ObservableObject {
    private let apiClient: APIClient

    // CRUD
    func list(folderPath: String = "/") async throws -> [SavedSearch]
    func get(id: String) async throws -> SavedSearch
    func create(_ search: SavedSearch) async throws -> SavedSearch
    func update(_ search: SavedSearch) async throws -> SavedSearch
    func delete(id: String) async throws
    func duplicate(id: String) async throws -> SavedSearch

    // Hierarchy
    func move(ids: [String], to folderPath: String) async throws
    func reorder(ids: [String], in folderPath: String) async throws

    // Folders
    func listFolders(parent: String = "/") async throws -> [Folder]
    func createFolder(path: String) async throws -> Folder
    func renameFolder(from: String, to: String) async throws
    func deleteFolder(path: String, deleteContents: Bool) async throws
}
```

**Estimate**: 3 hours

---

### Phase 8: Frontend - Build Hierarchy from Flat List (P1)

**Create new file**: `Fichero/Fichero/Utilities/HierarchyBuilder.swift`

**Purpose**: Convert flat list with `folder_path` into nested tree

```swift
struct HierarchyBuilder {
    /// Build hierarchical tree from flat list of items with folder_path
    static func buildTree<T: HierarchicalItem>(from items: [T]) -> [SidebarItem] {
        // 1. Group items by folder_path
        let grouped = Dictionary(grouping: items) { $0.folderPath }

        // 2. Extract unique folder paths
        var allPaths = Set<String>()
        for item in items {
            let components = item.folderPath.split(separator: "/")
            var path = ""
            for component in components {
                path += "/\(component)"
                allPaths.insert(path)
            }
        }

        // 3. Build folder items
        var folderItems: [String: SidebarItem] = [:]
        for path in allPaths {
            let name = path.split(separator: "/").last.map(String.init) ?? "Root"
            folderItems[path] = SidebarItem(
                id: UUID().uuidString,
                name: name,
                icon: "folder",
                type: .folder,
                folderPath: path,
                sortOrder: 0,
                isFolder: true,
                children: []
            )
        }

        // 4. Build leaf items from actual data
        var leafItems: [String: [SidebarItem]] = [:]
        for item in items {
            let sidebarItem = item.toSidebarItem()
            leafItems[item.folderPath, default: []].append(sidebarItem)
        }

        // 5. Assemble tree (recursive)
        return assembleNode(path: "/", folderItems: folderItems, leafItems: leafItems)
    }

    private static func assembleNode(
        path: String,
        folderItems: [String: SidebarItem],
        leafItems: [String: [SidebarItem]]
    ) -> [SidebarItem] {
        var children: [SidebarItem] = []

        // Add child folders
        for (folderPath, folder) in folderItems {
            if isImmediateChild(child: folderPath, parent: path) {
                var updatedFolder = folder
                updatedFolder.children = assembleNode(
                    path: folderPath,
                    folderItems: folderItems,
                    leafItems: leafItems
                )
                children.append(updatedFolder)
            }
        }

        // Add leaf items in this folder
        if let leaves = leafItems[path] {
            children.append(contentsOf: leaves.sorted { $0.sortOrder < $1.sortOrder })
        }

        return children.sorted { item1, item2 in
            // Folders first, then by name
            if item1.isFolder && !item2.isFolder { return true }
            if !item1.isFolder && item2.isFolder { return false }
            return item1.name < item2.name
        }
    }

    private static func isImmediateChild(child: String, parent: String) -> Bool {
        guard child.hasPrefix(parent), child != parent else { return false }
        let relative = child.dropFirst(parent.count).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return !relative.contains("/")
    }
}

protocol HierarchicalItem {
    var folderPath: String { get }
    var sortOrder: Int { get }
    func toSidebarItem() -> SidebarItem
}
```

**Estimate**: 2 hours

---

### Phase 9: Frontend - Update SidebarView (P1)

**File**: `Fichero/Fichero/Views/Sidebar/SidebarView.swift`

**Changes**:
1. Load hierarchical items for each mode
2. Build tree using `HierarchyBuilder`
3. Support folder expand/collapse state
4. Support drag-and-drop to move items between folders

**Example**:
```swift
struct SidebarView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var searchService = SavedSearchService()
    @StateObject private var conversationService = ConversationService()
    @StateObject private var workflowService = WorkflowService()

    @State private var searches: [SavedSearch] = []
    @State private var conversations: [Conversation] = []
    @State private var workflows: [Workflow] = []

    @State private var expandedFolders: Set<String> = ["/"]

    var body: some View {
        List {
            switch appState.sidebarMode {
            case .navigate:
                // Existing document hierarchy (already works)
                DocumentHierarchyView()

            case .search:
                // Build hierarchical tree from searches
                ForEach(hierarchicalSearches) { item in
                    SidebarItemRow(
                        item: item,
                        isExpanded: expandedFolders.contains(item.folderPath)
                    )
                    .onTapGesture {
                        if item.isFolder {
                            toggleFolder(item.folderPath)
                        } else {
                            selectSearch(item.id)
                        }
                    }
                }

            case .chat:
                // Build hierarchical tree from conversations
                ForEach(hierarchicalConversations) { item in
                    SidebarItemRow(item: item, isExpanded: expandedFolders.contains(item.folderPath))
                }

            case .workflows:
                // Build hierarchical tree from workflows
                ForEach(hierarchicalWorkflows) { item in
                    SidebarItemRow(item: item, isExpanded: expandedFolders.contains(item.folderPath))
                }
            }
        }
        .task {
            await loadItems()
        }
    }

    private var hierarchicalSearches: [SidebarItem] {
        HierarchyBuilder.buildTree(from: searches)
    }

    private var hierarchicalConversations: [SidebarItem] {
        HierarchyBuilder.buildTree(from: conversations)
    }

    private var hierarchicalWorkflows: [SidebarItem] {
        HierarchyBuilder.buildTree(from: workflows)
    }

    private func loadItems() async {
        do {
            searches = try await searchService.list()
            conversations = try await conversationService.list()
            workflows = try await workflowService.list()
        } catch {
            logger.error("Failed to load sidebar items: \(error)")
        }
    }
}
```

**Estimate**: 4-5 hours

---

## Total Estimates

**Backend**:
- Phase 1 (Persist Conversations): 1-2 hours
- Phase 2 (Workflow CRUD): 2-3 hours
- Phase 3 (Update Endpoints): 1 hour
- Phase 4 (Folder Management): 3-4 hours
**Total Backend**: 7-10 hours

**Frontend**:
- Phase 5 (SidebarItem Model): 30 minutes
- Phase 6 (API Models): 1 hour
- Phase 7 (Services): 3 hours
- Phase 8 (HierarchyBuilder): 2 hours
- Phase 9 (SidebarView): 4-5 hours
**Total Frontend**: 11-12 hours

**Grand Total**: 18-22 hours (2-3 days of focused work)

---

## Testing Plan

### Backend Tests

**Test each entity type**:
1. Create items in different folders
2. List items (filter by folder_path)
3. Move items between folders
4. Rename folders
5. Delete folders (with/without contents)
6. Reorder items within folder

### Frontend Tests

**Test sidebar modes**:
1. Navigate mode - existing document hierarchy works
2. Search mode - hierarchical saved searches
3. Chat mode - hierarchical conversations
4. Workflows mode - hierarchical workflows

**Test operations**:
1. Create folder (context menu)
2. Rename folder (inline edit)
3. Move items via drag-and-drop
4. Delete folder (with confirmation)
5. Expand/collapse folders (state persists)

---

## Future Enhancements

### 1. Smart Folders (P2)

**Like macOS Finder smart folders**:
- SavedSearch automatically updates based on criteria
- Conversations auto-organized by date/topic
- Workflows tagged by category (vision, transform, etc.)

### 2. Folder Templates (P3)

**Pre-defined folder structures**:
- "Research Project" template (Literature, Notes, Analysis)
- "Archive Collection" template (Correspondence, Reports, Media)

### 3. Folder Color/Icons (P3)

**Visual differentiation**:
- Custom colors for folders
- Custom SF Symbol icons
- Emoji support

---

## Risks and Mitigations

### Risk 1: Breaking Existing Functionality

**Mitigation**:
- All new fields have defaults (`folder_path="/"`, `sort_order=0`)
- Database migrations are non-destructive
- Existing items automatically appear in root folder

### Risk 2: Performance with Large Trees

**Mitigation**:
- Lazy loading (only load visible folders)
- Cache expanded state
- Debounce drag-and-drop operations

### Risk 3: User Confusion

**Mitigation**:
- Clear UI for "New Folder" vs "New Item"
- Confirmation dialogs for destructive operations
- Breadcrumb navigation in content area

---

## Conclusion

**The backend is 60% complete** - data models and migrations are ready, but:
1. Conversations need persistence
2. Workflow CRUD endpoints needed
3. Folder management endpoints needed

**The frontend is 0% complete** - sidebar shows flat lists only.

**Recommended approach**:
1. Start with backend (Phases 1-4) to get a complete API
2. Then tackle frontend (Phases 5-9) to visualize the hierarchy
3. Test thoroughly with all three entity types

This is a **2-3 day effort** for a complete implementation.
