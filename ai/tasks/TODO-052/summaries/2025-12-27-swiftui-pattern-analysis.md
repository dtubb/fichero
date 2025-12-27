# TODO-052: SwiftUI Pattern Analysis - 2025-12-27

## Problem
User reported: "Didn't work. But, this feels very manual. Is there not a better, more swiftui way of doing this?"

The `.id(refreshCounter)` hack didn't work and felt wrong because it IS wrong.

## Root Cause: Architecture Anti-Pattern

### Current (Broken) Pattern
```
ContentView (@StateObject documentStore)
    ├─> Computes libraryItems: [SidebarItem] (snapshot)
    └─> Passes to SidebarView(libraryItems: [SidebarItem])  ❌ STATIC DATA
```

**Why It Breaks:**
1. `documentStore.collections` is `@Published` ✓
2. ContentView computes `libraryItems` from `collections` ✓
3. But SidebarView receives `libraryItems` as **plain array parameter** ❌
4. When `collections` updates, SwiftUI doesn't know to recompute `libraryItems`
5. Even with `.id(refreshCounter)`, the timing is wrong

### Proper SwiftUI Pattern (from Apple Docs)

**From sosumi/ObservedObject:**
> Add the `@ObservedObject` attribute to a parameter of a SwiftUI View when the input is an Observable Object and you want the view to update when the object's published properties change.

**Correct Architecture:**
```
ContentView (@StateObject documentStore, savedSearchService, conversationService, workflowService)
    └─> SidebarView(
          @ObservedObject documentStore,           ✓ OBSERVES
          @ObservedObject savedSearchService,      ✓ OBSERVES
          @ObservedObject conversationService,     ✓ OBSERVES
          @ObservedObject workflowService          ✓ OBSERVES
        )
        ├─> Computes libraryItems internally from documentStore.collections
        ├─> Computes searchItems internally from savedSearchService.searches
        ├─> Computes chatItems internally from conversationService.conversations
        └─> Computes workflowItems internally from workflowService.workflows
```

**How It Works:**
1. ContentView owns stores with `@StateObject` (ownership)
2. SidebarView receives stores with `@ObservedObject` (observation)
3. SidebarView computes items as `private var` computed properties
4. When `@Published` properties change, SwiftUI **automatically** re-renders
5. No manual refresh, no counters, no hacks!

## Implementation Attempted

Changed SidebarView signature from:
```swift
struct SidebarView: View {
    let libraryItems: [SidebarItem]  ❌ Static
    var documentStore: DocumentStore?  ❌ Optional
```

To:
```swift
struct SidebarView: View {
    @ObservedObject var documentStore: DocumentStore  ✓
    @ObservedObject var savedSearchService: SavedSearchService  ✓
    @ObservedObject var conversationService: ConversationService  ✓
    @ObservedObject var workflowService: WorkflowService  ✓

    private var libraryItems: [SidebarItem] {
        SidebarItemBuilder.buildLibraryHierarchy(from: documentStore.collections)
    }
    // ... same for search, chat, workflow items
}
```

## Why Implementation Failed

The refactoring cascaded into too many changes:
1. Removed `conversations` and `savedSearches` @State from ContentView
2. Broke `refreshConversations()` and `refreshSavedSearches()` functions
3. Broke references in SearchView and ChatView callbacks
4. Broke sidebar item selection logic
5. Services need to manage their own @Published data properly

## The Right Way Forward

### Phase 1: Make Services Observable (Backend Work)
Each service needs to manage its own data:
```swift
class SavedSearchService: ObservableObject {
    @Published var savedSearches: [SavedSearch] = []

    func loadSavedSearches() async {
        // Fetch from backend
        // Update @Published property
    }
}
```

### Phase 2: Update SidebarView (Frontend Work)
Remove static parameters, use @ObservedObject:
```swift
struct SidebarView: View {
    @ObservedObject var documentStore: DocumentStore
    @ObservedObject var searchService: SavedSearchService
    // etc...
}
```

### Phase 3: Remove Manual Refresh Logic
Delete all:
- `refreshCounter` hacks
- `.id()` modifiers
- Manual `refresh()` calls after CRUD operations
- `handleDocumentChange()` counter increments

SwiftUI handles it automatically!

## Key Lessons

1. **@StateObject vs @ObservedObject**
   - Parent owns with `@StateObject`
   - Children observe with `@ObservedObject`

2. **Computed Properties in Views**
   - SwiftUI re-evaluates them when dependencies change
   - No manual tracking needed

3. **@Published Properties**
   - Changes automatically trigger view updates
   - Only for `@ObservedObject` or `@StateObject`

4. **Anti-Patterns to Avoid**
   - Passing computed snapshots as parameters
   - Manual refresh counters
   - `.id()` hacks for forcing re-renders
   - Optional store parameters (`DocumentStore?`)

## Current State

Changes **stashed** (not committed). The `.id(refreshCounter)` approach is fundamentally wrong.

Need to:
1. Audit all services to ensure they're proper ObservableObjects with @Published properties
2. Refactor SidebarView to observe services directly
3. Remove all manual refresh logic throughout the app

This is a larger architectural fix but will make the app much more maintainable and "SwiftUI-native".

## References
- Apple docs: https://developer.apple.com/documentation/swiftui/observedobject
- Sample pattern: ContentView owns @StateObject, passes to children as @ObservedObject
- Key quote: "SwiftUI updates any view that depends on the object"
