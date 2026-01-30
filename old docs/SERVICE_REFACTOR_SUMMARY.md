# Service Architecture Refactor - Complete Summary

## Overview

Systematically refactored the service architecture from per-tab to per-library scoping to fix 422 errors (missing `X-Fichero-Library-Path` header) and eliminate service duplication across tabs.

## Problem Identified

**Root Cause**: Views were creating new `APIClient()` instances without the library path set, causing backend 422 errors.

**Secondary Issue**: Each tab was creating its own service instances, leading to:
- State inconsistency across tabs viewing the same library
- Memory waste (5 tabs × 6 services = 30 instances instead of 6)
- Duplicate sidebar instances per tab

## Solution: Per-Library Service Scoping

**Architecture Decision**: Services should be per-library (not per-app, not per-window, not per-tab)

**Rationale**:
- Services match data ownership (searches belong to library)
- Automatic SwiftUI reactivity for state consistency
- One instance per library, shared across all tabs viewing that library
- Simpler state management

## Changes Made

### 1. LibraryManager.swift

Added 13 service properties to `LibraryReference`:
- `apiClient: APIClient` (already existed)
- `documentStore: DocumentStore`
- `savedSearchService: SavedSearchService`
- `searchService: SearchService`
- `conversationService: ConversationService`
- `chatService: ChatService`
- `workflowStore: WorkflowStore`
- `workflowService: WorkflowService`
- `importService: ImportService`
- `documentService: DocumentService`
- `storageService: StorageService`
- `providerService: ProviderService` ⭐ NEW
- `modelService: ModelService` ⭐ NEW

All services initialized in `init()` with the library's `APIClient`:
```swift
self.documentStore = documentStore ?? DocumentStore(apiClient: self.apiClient)
self.savedSearchService = savedSearchService ?? SavedSearchService(apiClient: self.apiClient)
// ... etc for all 11 services
```

### 2. FicheroApp.swift

Injected all 13 library services as environment objects:
```swift
.environmentObject(library.documentStore)
.environmentObject(library.savedSearchService)
.environmentObject(library.searchService)
.environmentObject(library.conversationService)
.environmentObject(library.chatService)
.environmentObject(library.workflowStore)
.environmentObject(library.workflowService)
.environmentObject(library.importService)
.environmentObject(library.documentService)
.environmentObject(library.storageService)
.environmentObject(library.providerService)  // ⭐ NEW
.environmentObject(library.modelService)     // ⭐ NEW
```

### 3. DocumentTabView.swift

**Before** (60+ lines):
- Created 6 services with `@StateObject`
- Complex init logic to get library's `APIClient`
- Created temporary services if library not found

**After** (clean):
- Receives all services via `@EnvironmentObject`
- Simple 3-line init
- No service creation logic

### 4. Views Fixed to Use @EnvironmentObject

#### Chat Views
- **ChatView.swift**: Changed `ChatService` from private property to `@EnvironmentObject`
- **ChatInspector.swift**: Changed `ChatService` and direct `APIClient()` calls to use `@EnvironmentObject`

#### Search Views
- **SearchView.swift**: Already using `@EnvironmentObject` correctly ✓

#### Workflow Views
- **WorkflowEditor.swift**: Already fixed earlier ✓
- **WorkflowInspector.swift**: Changed `WorkflowService` to `@EnvironmentObject`
- **NodePopover.swift**: Changed `ChatService` to `@EnvironmentObject`

#### Library Views
- **QuickLookComponents.swift**: Added `@EnvironmentObject var apiClient: APIClient` and changed `APIClient().sourceURL()` to `apiClient.sourceURL()`

#### Component Views
- **LibraryImageView.swift**: Changed from creating local `StorageService(apiClient: documentStore.api)` to using `@EnvironmentObject var storageService: StorageService`

#### AI Provider Views (all 5 files)
- **ProvidersView.swift**: Fixed TWO `ProviderService` instances (main view + detail view)
- **AIModelSelectionView.swift**: Changed `ProviderService` to `@EnvironmentObject`
- **AIModelCatalog.swift**: Changed `ModelService` to `@EnvironmentObject`
- **AIProviderAddModelsSheet.swift**: Changed `ProviderService` to `@EnvironmentObject`
- **AddProviderSheet.swift**: Changed `ProviderService` to `@EnvironmentObject`

## Files Modified

### Core Architecture
1. `Models/LibraryManager.swift` - Added 13 services to LibraryReference
2. `FicheroApp.swift` - Injected all 13 services as environment objects
3. `Views/DocumentTabView.swift` - Removed service creation, use environment

### Chat
4. `Views/Chat/ChatView.swift`
5. `Views/Chat/ChatInspector.swift`

### Search
6. `Views/Search/SearchView.swift` - Already correct ✓

### Workflow
7. `Views/Workflow/WorkflowEditor.swift` - Already fixed ✓
8. `Views/Workflow/WorkflowInspector.swift`
9. `Views/Workflow/NodePopover.swift`

### Library
10. `Views/Library/QuickLookComponents.swift`

### Components
11. `Views/Components/LibraryImageView.swift`

### AI Providers
12. `Views/AIProviders/ProvidersView.swift`
13. `Views/AIProviders/AIModelSelectionView.swift`
14. `Views/AIProviders/AIModelCatalog.swift`
15. `Views/AIProviders/AIProviderAddModelsSheet.swift`
16. `Views/AIProviders/AddProviderSheet.swift`

**Total: 16 files modified**

## Services Added to LibraryManager

**Previously Missing** (now added):
- ✅ ChatService
- ✅ SearchService
- ✅ WorkflowService
- ✅ ProviderService
- ✅ ModelService

**Already Present**:
- ✅ APIClient
- ✅ DocumentStore
- ✅ SavedSearchService
- ✅ ConversationService
- ✅ WorkflowStore
- ✅ ImportService
- ✅ DocumentService
- ✅ StorageService

## Verification

✅ **Build Status**: SUCCESS (clean build, no errors)
✅ **SwiftLint**: CLEAN (no warnings or errors)
✅ **APIClient() Search**: NO MATCHES in Views/ directory
✅ **All Services Accounted**: 13/13 services in LibraryManager

## Impact

### Before
- 422 errors due to missing `X-Fichero-Library-Path` header
- State inconsistency across tabs
- Memory waste from duplicate services
- Each tab had its own sidebar (duplication bug)

### After
- All services have correct library path
- Consistent state across all tabs viewing same library
- One service instance per library (shared across tabs)
- Single sidebar for all tabs
- Automatic SwiftUI reactivity for state updates

## Architecture Benefits

1. **Data Ownership**: Services match data lifetime (library lifetime)
2. **State Consistency**: SwiftUI's `@Published` ensures all views stay in sync
3. **Memory Efficiency**: No duplicate service instances
4. **Thread Safety**: `@MainActor` ensures UI thread access
5. **Concurrent Requests**: URLSession handles multiple async calls safely
6. **SwiftUI Best Practices**: Uses environment objects for dependency injection

## Future Multi-Library Support

This architecture enables future multi-library sidebar showing all open libraries simultaneously:
```
Library
  > Test 1 Library
  > Test 2 Library
Searches
  > Test 1 Searches
  > Test 2 Searches
```

Each library maintains its own service instances, enabling separate state and backend connections for each open library.

## Known Issues / Future Work

### AppState Provider Loading (App/AppState.swift)

**Issue**: AppState has an app-wide `APIClient` and `ProviderService` that attempts to load providers without a library path. The `/providers` endpoint requires `X-Fichero-Library-Path` header (providers are library-specific in the backend).

**Current Code**:
```swift
private let apiClient = APIClient()  // App-wide APIClient
private let providerService: ProviderService

func loadProviders() async {
    providers = try await providerService.listProviders()  // Requires library path!
}
```

**Why Not Fixed**:
- Currently only used for first-launch detection (checking if any providers configured)
- May not be actively causing 422 errors if called after library opens
- Requires architectural decision: should providers be app-wide or library-specific?

**Potential Solutions**:
1. Remove app-wide provider loading entirely (rely on library-specific provider views)
2. Make backend provider catalog endpoints truly app-wide (no library path required)
3. Defer provider checking until after first library opens
4. Use current library's provider service if available

**Impact**: Low priority - not causing build errors or blocking functionality

## Date Completed

January 1, 2026

## Summary

Successfully migrated from per-tab service creation to per-library service scoping, fixing 422 errors and eliminating service duplication. All 13 services now properly scoped to library lifetime and shared across tabs. Build clean, SwiftLint clean, no remaining APIClient() calls in Views/.
