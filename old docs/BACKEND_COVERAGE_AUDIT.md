# Backend API Coverage Audit

**Date:** 2025-12-30
**Purpose:** Identify which backend APIs are NOT yet integrated in Swift

---

## Backend API Inventory

The Python backend provides **8 route modules** with **61 total endpoints**:

### 1. Documents API (`/api/documents`) - 11 endpoints

| Endpoint | Method | Swift Status | Notes |
|----------|--------|--------------|-------|
| `/documents` | GET | ✅ USED | DocumentStore.loadCollections() |
| `/documents/collections` | GET | ❌ MISSING | Could optimize loading |
| `/documents/roots` | GET | ❌ MISSING | Get root-level docs only |
| `/documents/{doc_id}` | GET | ⚠️ PARTIAL | DocumentStore has this logic |
| `/documents/{doc_id}/children` | GET | ❌ MISSING | Not used (loads all docs instead) |
| `/documents/{doc_id}/ancestors` | GET | ❌ MISSING | For breadcrumbs! |
| `/documents` | POST | ❌ MISSING | Create new document/collection |
| `/documents/{doc_id}` | PUT | ❌ MISSING | Update document metadata |
| `/documents/{doc_id}` | DELETE | ❌ MISSING | Delete document |
| `/documents/reorder` | POST | ❌ MISSING | Reorder documents |
| `/documents/{doc_id}/move` | PUT | ❌ MISSING | Move to different parent |

**MISSING: DocumentService.swift**

### 2. Ingest API (`/api/ingest`) - 3 endpoints

| Endpoint | Method | Swift Status | Notes |
|----------|--------|--------------|-------|
| `/ingest/file` | POST | ⚠️ PARTIAL | Called from DocumentStore (wrong!) |
| `/ingest/folder` | POST | ❌ MISSING | Not implemented at all |
| `/ingest/status/{task_id}` | GET | ❌ MISSING | Track ingestion progress |

**MISSING: ImportService.swift** (identified in ARCHITECTURE_FIXES.md)

### 3. Storage API (`/api/storage`) - 4 endpoints

| Endpoint | Method | Swift Status | Notes |
|----------|--------|--------------|-------|
| `/storage/thumbnail/{doc_id}` | GET | ❌ MISSING | Get document thumbnail |
| `/storage/display/{doc_id}` | GET | ❌ MISSING | Get display-quality image |
| `/storage/source/{doc_id}` | GET | ❌ MISSING | Get original file |
| `/storage/stats` | GET | ❌ MISSING | Storage usage stats |

**MISSING: StorageService.swift**

### 4. Search API (`/api/search`) - 7 endpoints

| Endpoint | Method | Swift Status | Notes |
|----------|--------|--------------|-------|
| `/search` | POST | ✅ USED | SearchService.search() |
| `/search/stats` | GET | ❌ MISSING | Search index statistics |
| `/search/reindex` | POST | ❌ MISSING | Rebuild search index |
| `/search/embed/{doc_id}` | POST | ❌ MISSING | Create embeddings for doc |
| `/search/saved` | POST | ✅ USED | SavedSearchService |
| `/search/saved` | GET | ✅ USED | SavedSearchService |
| `/search/saved/{search_id}/duplicate` | POST | ❌ MISSING | Duplicate saved search |
| `/search/saved/{search_id}` | DELETE | ❌ MISSING | Delete saved search |
| `/search/saved/reorder` | POST | ❌ MISSING | Reorder saved searches |

**PARTIAL: SearchService.swift** (missing index management, embeddings)

### 5. Chat API (`/api/chat`) - 8 endpoints

| Endpoint | Method | Swift Status | Notes |
|----------|--------|--------------|-------|
| `/chat` | POST | ✅ USED | ChatService.sendMessage() |
| `/chat/conversations` | GET | ✅ USED | ConversationService |
| `/chat/conversations/{id}` | GET | ✅ USED | ConversationService |
| `/chat/conversations/{id}/duplicate` | POST | ❌ MISSING | Duplicate conversation |
| `/chat/conversations/{id}` | DELETE | ❌ MISSING | Delete conversation |
| `/chat/conversations/reorder` | POST | ❌ MISSING | Reorder conversations |
| `/chat/providers` | GET | ✅ USED | ChatService.loadProviders() |
| `/chat/extract-text` | POST | ❌ MISSING | Extract text from documents |

**PARTIAL: ChatService.swift** (missing conversation management)

### 6. Providers API (`/api/providers`) - 13 endpoints

| Endpoint | Method | Swift Status | Notes |
|----------|--------|--------------|-------|
| `/providers/catalog` | GET | ✅ USED | ProviderService |
| `/providers/catalog/{provider_type}` | GET | ❌ MISSING | Get specific provider catalog |
| `/providers/models/{provider_type}` | GET | ❌ MISSING | Get available models |
| `/providers` | GET | ✅ USED | ProviderService.listProviders() |
| `/providers` | POST | ✅ USED | ProviderService.addProvider() |
| `/providers/{provider_id}` | GET | ❌ MISSING | Get provider details |
| `/providers/{provider_id}` | PATCH | ❌ MISSING | Update provider config |
| `/providers/{provider_id}` | DELETE | ❌ MISSING | Delete provider |
| `/providers/{provider_type}/api-key` | POST | ❌ MISSING | Set API key |
| `/providers/{provider_type}/api-key` | DELETE | ❌ MISSING | Remove API key |
| `/providers/{provider_type}/api-key/status` | GET | ❌ MISSING | Check if API key set |
| `/providers/{provider_type}/test` | POST | ❌ MISSING | Test provider connection |
| `/providers/{provider_id}/models` | GET | ❌ MISSING | List provider's models |
| `/providers/{provider_id}/models` | POST | ❌ MISSING | Add model to provider |
| `/providers/{provider_id}/models/{model_id}` | DELETE | ❌ MISSING | Remove model |

**PARTIAL: ProviderService.swift** (missing CRUD operations, API key management, testing)

### 7. Workflows API (`/api/workflows`) - 15 endpoints

| Endpoint | Method | Swift Status | Notes |
|----------|--------|--------------|-------|
| `/workflows/tools` | GET | ✅ USED | WorkflowService.loadTools() |
| `/workflows/tools/grouped` | GET | ❌ MISSING | Get tools grouped by category |
| `/workflows/tools/{tool_name}` | GET | ❌ MISSING | Get tool details |
| `/workflows/tools/{tool_name}/create-node` | POST | ❌ MISSING | Create node from tool |
| `/workflows/run` | POST | ⚠️ PARTIAL | Used but streaming not implemented |
| `/workflows` | POST | ✅ USED | WorkflowStore.createWorkflow() |
| `/workflows/import` | POST | ❌ MISSING | Import workflow from JSON |
| `/workflows/{workflow_id}/export` | GET | ❌ MISSING | Export workflow to JSON |
| `/workflows` | GET | ✅ USED | WorkflowStore.loadWorkflows() |
| `/workflows/{workflow_id}` | GET | ✅ USED | WorkflowStore.getWorkflow() |
| `/workflows/{workflow_id}` | PUT | ✅ USED | WorkflowStore.updateWorkflow() |
| `/workflows/{workflow_id}` | DELETE | ❌ MISSING | Delete workflow |
| `/workflows/{workflow_id}/duplicate` | POST | ❌ MISSING | Duplicate workflow |
| `/workflows/reorder` | POST | ❌ MISSING | Reorder workflows |
| `/workflows/{workflow_id}/run` | POST | ⚠️ PARTIAL | Streaming not used |

**PARTIAL: WorkflowService.swift** (missing import/export, duplicate, reorder, streaming)

### 8. Models API (`/api/models`) - 3 endpoints (HuggingFace)

| Endpoint | Method | Swift Status | Notes |
|----------|--------|--------------|-------|
| `/models/huggingface/tasks` | GET | ❌ MISSING | List HF task categories |
| `/models/huggingface` | GET | ❌ MISSING | Search HF models |
| `/models/huggingface/{model_id:path}` | GET | ❌ MISSING | Get HF model details |

**MISSING: HuggingFaceService.swift** (not needed for MVP)

---

## Summary Statistics

| Category | Total Endpoints | Used | Partial | Missing | Coverage |
|----------|-----------------|------|---------|---------|----------|
| Documents | 11 | 1 | 1 | 9 | **18%** |
| Ingest | 3 | 0 | 1 | 2 | **33%** |
| Storage | 4 | 0 | 0 | 4 | **0%** |
| Search | 7 | 3 | 0 | 4 | **43%** |
| Chat | 8 | 4 | 0 | 4 | **50%** |
| Providers | 13 | 3 | 0 | 10 | **23%** |
| Workflows | 15 | 6 | 2 | 7 | **53%** |
| Models (HF) | 3 | 0 | 0 | 3 | **0%** |
| **TOTAL** | **64** | **17** | **4** | **43** | **33%** |

**Only 33% of backend APIs are integrated in Swift!**

---

## Critical Missing Features

### 🔴 P0 - Blocking Core Features

1. **ImportService.swift** (Ingest API)
   - ❌ File import is scattered (see ARCHITECTURE_FIXES.md)
   - ❌ No folder import
   - ❌ No progress tracking

2. **DocumentService.swift** (Documents API)
   - ❌ Can't create collections from UI
   - ❌ Can't rename documents
   - ❌ Can't move documents
   - ❌ Can't delete documents properly
   - ❌ No breadcrumb navigation (no /ancestors endpoint)
   - ❌ No drag-and-drop reordering

3. **StorageService.swift** (Storage API)
   - ❌ No thumbnails displayed
   - ❌ No document previews
   - ❌ No storage stats

### 🟡 P1 - Missing UX Features

4. **Enhanced SearchService** (Search API)
   - ❌ No reindex capability
   - ❌ No search stats
   - ❌ No manual embedding creation

5. **Enhanced ChatService** (Chat API)
   - ❌ Can't delete conversations
   - ❌ Can't duplicate conversations
   - ❌ No conversation reordering
   - ❌ No text extraction from documents

6. **Enhanced ProviderService** (Providers API)
   - ❌ Can't update provider settings
   - ❌ Can't delete providers
   - ❌ No API key management UI
   - ❌ No connection testing
   - ❌ No model management

7. **Enhanced WorkflowService** (Workflows API)
   - ❌ No workflow import/export
   - ❌ Can't delete workflows
   - ❌ Can't duplicate workflows
   - ❌ No workflow reordering
   - ❌ No streaming execution (exists but not used)

---

## Recommended Implementation Priority

### Phase 0: Architecture (ARCHITECTURE_FIXES.md) - **DO FIRST**

1. Create `ImportService.swift`
2. Create `DocumentService.swift`
3. Create `StorageService.swift`
4. Reorganize folder structure

### Phase 1: Core Document Management (P0)

**DocumentService.swift**
```swift
@MainActor
class DocumentService: ObservableObject {
    // Create
    func createCollection(name: String, parentId: String?) async throws -> Document
    func createDocument(...) async throws -> Document

    // Read
    func getDocument(_ id: String) async throws -> Document
    func getChildren(_ parentId: String) async throws -> [Document]
    func getAncestors(_ id: String) async throws -> [Document]  // For breadcrumbs!
    func getRoots() async throws -> [Document]

    // Update
    func updateDocument(_ id: String, updates: DocumentUpdate) async throws -> Document
    func moveDocument(_ id: String, to newParentId: String?) async throws -> Document
    func reorderDocuments(_ ids: [String]) async throws

    // Delete
    func deleteDocument(_ id: String) async throws
}
```

**ImportService.swift** (already designed in ARCHITECTURE_FIXES.md)

**StorageService.swift**
```swift
@MainActor
class StorageService: ObservableObject {
    func getThumbnail(_ docId: String) async throws -> NSImage
    func getDisplayImage(_ docId: String) async throws -> NSImage
    func getSourceFile(_ docId: String) async throws -> URL
    func getStats() async throws -> StorageStats
}
```

### Phase 2: Enhanced Features (P1)

1. **SearchService** - Add reindex, stats, embedding methods
2. **ConversationService** - Add delete, duplicate, reorder
3. **ProviderService** - Add full CRUD, API key management, testing
4. **WorkflowService** - Add import/export, delete, duplicate, streaming

### Phase 3: Nice-to-Have (P2)

1. **HuggingFaceService** - For model browsing (future feature)

---

## Impact on User Experience

### What Users CAN'T Do Right Now

**Document Management:**
- ❌ Create new collections from UI
- ❌ Rename documents/collections
- ❌ Move documents to different collections
- ❌ Delete documents permanently
- ❌ See breadcrumb navigation
- ❌ Drag-and-drop reordering

**Import:**
- ❌ Import entire folders
- ❌ See import progress
- ❌ Choose LINK vs COPY mode
- ❌ Configure text extraction

**Viewing:**
- ❌ See document thumbnails
- ❌ Quick preview without download
- ❌ Storage usage statistics

**Conversations:**
- ❌ Delete old conversations
- ❌ Duplicate conversations
- ❌ Reorder conversation list

**Providers:**
- ❌ Edit provider settings
- ❌ Delete providers
- ❌ Test provider connections
- ❌ Manage provider API keys from UI

**Workflows:**
- ❌ Import workflows from files
- ❌ Export workflows to share
- ❌ Delete workflows
- ❌ Duplicate workflows
- ❌ See streaming execution progress

---

## Next Steps

1. **Review ARCHITECTURE_FIXES.md** - Do Phase 0 first
2. **Implement missing services** - Start with P0 (DocumentService, ImportService, StorageService)
3. **Add UI for new features** - Menus, toolbars, context menus
4. **Test end-to-end** - Each service with real backend
5. **Then do SwiftUI cleanup** - SWIFTUI_AUDIT_PLAN.md

---

## Files to Create

```
Services/
├── APIClient.swift ✅ (exists)
├── ImportService.swift ❌ CREATE (Phase 0)
├── DocumentService.swift ❌ CREATE (Phase 1)
├── StorageService.swift ❌ CREATE (Phase 1)
├── DocumentStore.swift ✅ (exists, refactor)
├── WorkflowStore.swift ✅ (exists, enhance)
├── ChatService.swift ✅ (exists, enhance)
├── ConversationService.swift ✅ (exists, enhance)
├── SearchService.swift ✅ (exists, enhance)
├── SavedSearchService.swift ✅ (exists, enhance)
├── ProviderService.swift ✅ (exists, enhance)
├── ModelService.swift ✅ (exists)
├── WorkflowService.swift ✅ (exists, enhance)
├── DragDropService.swift ✅ (exists, UI helper)
├── ErrorService.swift ✅ (exists, refactor - see SWIFTUI_AUDIT_PLAN.md)
└── PerformanceService.swift ✅ (exists, UI helper)
```

---

**Created By:** Claude Code
**Last Updated:** 2025-12-30
**Status:** Ready for review and prioritization
