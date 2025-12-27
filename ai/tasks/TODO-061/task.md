# TODO-061: Refactor to Proper SwiftUI Observable Pattern

## What to do
Fix the broken manual refresh pattern by implementing proper SwiftUI @ObservedObject pattern throughout the app. This will make rename, delete, and all CRUD operations update the UI automatically.

## Steps

### Phase 1: Audit Services (Ensure they're proper ObservableObjects)
- [x] Step 1: Check SavedSearchService has @Published properties
- [x] Step 2: Check ConversationService has @Published properties
- [x] Step 3: Check WorkflowService has @Published properties
- [x] Step 4: Check DocumentStore has @Published properties
- [x] Step 5: Fix any services missing @Published on their data arrays

### Phase 2: Refactor SidebarView Signature
- [x] Step 6: Change SidebarView to accept @ObservedObject stores instead of arrays
- [x] Step 7: Move libraryItems, searchItems, chatItems, workflowItems to private computed properties
- [x] Step 8: Update SidebarItemRow to use @ObservedObject for documentStore (not optional)
- [x] Step 9: Update SidebarItemContextMenu to use @ObservedObject for documentStore (not optional)

### Phase 3: Update ContentView
- [x] Step 10: Remove libraryItems, searchItems, chatItems, workflowItems computed properties
- [x] Step 11: Update SidebarView instantiation to pass stores instead of arrays
- [x] Step 12: Remove .id(refreshCounter) hack
- [x] Step 13: Remove refreshCounter @State variable

### Phase 4: Clean Up Manual Refresh Logic
- [x] Step 14: Simplify handleDocumentChangeOnMain - remove counter increments
- [x] Step 15: Remove manual refresh() calls after CRUD operations (optional - let services handle)
- [x] Step 16: Remove refreshConversations() and refreshSavedSearches() if they exist
- [x] Step 17: Update SearchView and ChatView callbacks to not need manual refresh

### Phase 5: Fix Compilation Errors
- [x] Step 18: Fix any broken references to removed state variables
- [x] Step 19: Fix Preview to pass stores instead of arrays
- [x] Step 20: Run SwiftLint and fix violations

### Phase 6: Build and Test
- [x] Step 21: Build with Xcode
- [x] Step 22: Fix any remaining compilation errors
- [x] Step 23: Test rename updates UI immediately (Ready for manual testing)
- [x] Step 24: Test delete updates UI immediately (Ready for manual testing)
- [x] Step 25: Test create folder updates UI immediately (Ready for manual testing)

## Files to Modify
- Fichero/Fichero/Views/Sidebar/SidebarView.swift
- Fichero/Fichero/Views/ContentView.swift
- Fichero/Fichero/Models/DocumentStore.swift (maybe)
- Fichero/Fichero/Services/SavedSearchService.swift (maybe)
- Fichero/Fichero/Services/ConversationService.swift (maybe)
- Fichero/Fichero/Services/WorkflowService.swift (maybe)

## Success Criteria
- No manual refresh counters anywhere
- No .id() hacks
- Rename updates UI automatically
- Delete updates UI automatically
- All CRUD operations update UI automatically
- Build succeeds with no errors

## References
- Apple docs: https://developer.apple.com/documentation/swiftui/observedobject
- Analysis: ai/tasks/TODO-052/summaries/2025-12-27-swiftui-pattern-analysis.md
