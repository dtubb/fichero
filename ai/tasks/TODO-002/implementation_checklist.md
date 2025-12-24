# Implementation Checklist for TODO-002: Complete In Line Rename

## Planning Phase
- [x] Review TODO-001 analysis for inline rename requirements
- [x] Review existing codebase structure
- [x] Identify backend API endpoints for rename operations
- [x] Review existing services (DocumentService, SavedSearchService, etc.)
- [x] Review existing RenameDialog.swift implementation
- [x] Understand current context menu structure

## Implementation Phase

### 1. Backend API Verification
- [x] Verify PUT /documents/{doc_id} supports name updates
- [x] Verify PATCH /search/saved/{search_id} supports name updates  
- [x] Verify PATCH /chat/conversations/{conv_id} supports title updates
- [x] Verify PATCH /workflows/{workflow_id} supports name updates

### 2. Service Layer Implementation
- [x] Add rename methods to services if missing:
  - DocumentService.renameDocument() - ✅ Added
  - SavedSearchService.renameSavedSearch() - ✅ Already exists
  - ConversationService.renameConversation() - ✅ Already exists  
  - WorkflowService.renameWorkflow() - ✅ Already exists

### 3. UI Implementation
- [x] Create inline rename text field component
- [x] Add state management for rename mode
- [x] Implement Enter to confirm, Escape to cancel
- [x] Integrate with context menu "Rename..." actions
- [x] Add visual feedback during rename operations
- [x] Handle errors gracefully

### 4. Integration
- [x] Connect UI to service layer
- [x] Fix compile errors and scope issues
- [x] Move InlineRenameField to be nested in SidebarView
- [x] Add missing renamingItemId parameters to all SidebarItemRow instantiations
- [x] Fix pre-existing build issues (EmptyResponse, unreachable catch blocks)
- [ ] Test with all item types (documents, searches, conversations, workflows)
- [ ] Ensure proper state updates after rename
- [ ] Verify UI updates correctly

## Testing Phase
- [ ] Test document rename functionality
- [ ] Test saved search rename functionality
- [ ] Test conversation rename functionality
- [ ] Test workflow rename functionality
- [ ] Test keyboard shortcuts (Enter/Escape)
- [ ] Test error handling
- [ ] Test edge cases (empty names, duplicates, etc.)

## Review Phase
- [ ] Self-review code quality
- [ ] Verify follows established patterns
- [ ] Check error handling and logging
- [ ] Prepare for human review

## Files to Modify
- `Fichero/Views/Sidebar/SidebarView.swift` - Add rename state and logic
- `Fichero/Views/Sidebar/SidebarItemRow.swift` - Add inline rename UI
- `Fichero/Services/DocumentService.swift` - Add renameDocument method if needed
- `Fichero/Services/SavedSearchService.swift` - Verify rename method
- `Fichero/Services/ConversationService.swift` - Verify rename method
- `Fichero/Services/WorkflowService.swift` - Verify rename method
