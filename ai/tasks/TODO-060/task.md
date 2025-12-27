# TODO-060: Human UI Testing Checklist for TODO-050 through TODO-059

## What to do
Manual UI testing and verification of all sidebar improvements from TODO-051 through TODO-059.

## Pre-Testing Setup
- [X] Clean rebuild: Product > Clean Build Folder, then rebuild
- [X] Start FastAPI backend on port 8765: `PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765`
- [X] Launch Fichero app from Xcode

---

## TODO-051: Remove "Move to Folder" from Context Menu ✓
- [x] Right-click any sidebar item
- [x] Confirm context menu only shows: Rename, Duplicate, Delete
- [x] Confirm "Move to Folder" option is gone
- [x] **Notes:** All removed - verified complete

---

## TODO-052: Inline Rename Functionality ⚠️ BUG FIXED - RETEST
**Fix Applied**: Replaced deprecated `onCommit` with `.onSubmit`, added `@FocusState` for auto-focus, fixed validation bug

- [X] Select a document in Library section
- [X] Choose "Rename" from context menu (or press Return)
- [X] **Critical**: Verify TextField appears inline with current name selected
- [X] **Critical**: Verify TextField automatically receives focus (cursor should be blinking)
IT works.
- [X] Type a new name and press Enter
Ot wprls.
- [ ] Confirm name updates in UI immediately
Does not update im UI, and not sure if backend also updates.
- [ ] Refresh/restart app - verify rename persisted to backend
- [ ] Test: Click outside TextField while renaming - should cancel
- [ ] Test: Press Escape while renaming - should cancel
- [ ] Test: Try empty name (just spaces) - should reject and cancel
- [ ] Test: Try name over 255 characters - should reject and cancel
- [ ] Test: Rename on double-click (if supported)
- [ ] Test rename on: searches, chats, workflows (may not work - needs backend support)
- [ ] **Notes:**

---

## TODO-053: Delete Functionality
- [ ] Right-click a document in Library
- [ ] Select "Delete" from context menu
- [ ] Confirm confirmation dialog appears
- [ ] Click "Delete" and verify item disappears from UI
- [ ] Test: Press Cmd+Delete on selected item - should show same dialog
- [ ] Verify deleted items don't reappear after app restart
- [ ] Test deleting: searches, chats, workflows
- [ ] Verify error alert appears if deletion fails
- [ ] **Notes:**

---

## TODO-054: Drag and Drop Folder Hierarchy ⚠️ CRITICAL - NEEDS CLEAN REBUILD
**Critical**: Must do Product > Clean Build Folder first!

- [ ] Create test folder structure (Folder A, Folder B inside A, Folder C)
- [ ] Drag Folder C and hover over Folder A
- [ ] Verify visual feedback: accent color highlight at 20% opacity on drop target
- [ ] Drop Folder C onto Folder A
- [ ] Confirm Folder C becomes child of Folder A in hierarchy
- [ ] Test: Try dragging folder into its own child - should prevent (check logs)
- [ ] Test: Drag document into folder - should work
- [ ] Test: Multi-select drag (Cmd+click multiple items, drag together)
- [ ] Refresh UI - verify hierarchy persists
- [ ] **Notes:**
- [ ] **Known Issues**: `isDescendant()` is placeholder - may not prevent all circular references

---

## TODO-055: Section Title Indentation
- [ ] Open sidebar and observe all four sections (Library, Searches, Chat, Workflows)
- [ ] Verify items under section headers have subtle 4pt left indent
- [ ] Compare section titles vs. items - items should be slightly indented
- [ ] Check "New..." buttons also have matching indent
- [ ] **Notes:**

---

## TODO-056: Drop on Section Headers
**Note**: Blocked by TODO-059 previously, now should work

### Search Section:
- [ ] Drag a document from Library
- [ ] Hover over "Search" section header
- [ ] Verify accent color background appears (20% opacity)
- [ ] Drop the document
- [ ] Verify app switches to Search view
- [ ] Check console logs for "Dropped X items on Search header"
- [ ] **Notes:**

### Chat Section:
- [ ] Drag one or more documents from Library
- [ ] Hover over "Chat" section header
- [ ] Verify accent color background appears
- [ ] Drop the document(s)
- [ ] Verify app switches to Chat view
- [ ] Verify new chat is created with documents as context
- [ ] Open chat and confirm documents are attached
- [ ] **Notes:**

### Workflows Section:
- [ ] Drag a document from Library
- [ ] Hover over "Workflows" section header
- [ ] Verify accent color background appears
- [ ] Drop the document
- [ ] Verify app switches to Workflow view
- [ ] Check console logs for "Dropped X items on Workflow header"
- [ ] **Notes:**
- [ ] **Known Issues**: Search and Workflow don't pass document context yet (only navigate)

---

## TODO-057: Drag from Finder to Ingest Files ⚠️ CRITICAL TEST
**Note**: Was blocked by build issues, now should work

### Drag to Sidebar:
- [ ] Open Finder and locate test files (PDF, TXT, image)
- [ ] Drag file from Finder to sidebar Library section
- [ ] Verify visual drop target feedback appears
- [ ] Drop file and watch for progress indicator
- [ ] Confirm file appears in Library after import completes
- [ ] Test with unsupported file type - should show error
- [ ] **Notes:**

### Drag to Folder:
- [ ] Create a folder in Library
- [ ] Drag file from Finder onto that specific folder
- [ ] Verify file is imported as child of that folder
- [ ] **Notes:**

### Batch Import:
- [ ] Select multiple files in Finder (Cmd+click)
- [ ] Drag all files to sidebar at once
- [ ] Verify all files import successfully
- [ ] **Notes:**

### Folder Import:
- [ ] Drag entire folder from Finder to sidebar
- [ ] Verify folder hierarchy is preserved
- [ ] Check all files in folder were imported
- [ ] **Notes:**

---

## TODO-058: Menu Commands and Toolbar

### File Menu:
- [ ] Menu Bar > File > New Folder (or Cmd+N)
- [ ] Verify new folder appears in Library
- [ ] Menu Bar > File > Import Files (or Cmd+O)
- [ ] Verify file picker opens
- [ ] Select file(s) and confirm they import
- [ ] Menu Bar > File > Import Folder (or Cmd+Shift+O)
- [ ] Verify folder picker opens
- [ ] Select folder and confirm it imports with hierarchy
- [ ] **Notes:**

### Edit Menu:
- [ ] Select a document
- [ ] Menu Bar > Edit > Rename (or press Return)
- [ ] Verify inline rename activates
- [ ] Select a document
- [ ] Menu Bar > Edit > Delete (or Cmd+Delete)
- [ ] Verify confirmation dialog appears
- [ ] **Notes:**

### Sidebar Toolbar:
- [ ] Locate toolbar at top of sidebar (4 buttons)
- [ ] Click "New Folder" button (folder.badge.plus icon) - should create folder
- [ ] Click "Import Files" button (square.and.arrow.down icon) - should open picker
- [ ] Select item, click "Rename" button (pencil icon) - should activate rename
- [ ] Verify Rename button is disabled when nothing selected
- [ ] Select item, click "Delete" button (trash icon) - should show confirmation
- [ ] Verify Delete button is disabled when nothing selected
- [ ] Hover over each button - verify tooltips appear
- [ ] **Notes:**

---

## TODO-059: Hierarchical Folder Structure
This was a build fix - no specific UI tests, but verify:
- [ ] All TODO-054, TODO-056, TODO-057 tests work (those depend on this)
- [ ] App builds and runs without errors
- [ ] SidebarItemBuilder methods work correctly in ContentView
- [ ] **Notes:**

---

## Quick Smoke Test (5 minutes)

If you're short on time, test these critical paths:

- [ ] Rename a document (inline TextField appears, Enter commits)
- [ ] Delete a document (Cmd+Delete works, confirmation shows)
- [ ] Drag document from Finder to sidebar (imports successfully)
- [ ] Drag document onto Chat section header (creates new chat)
- [ ] Use toolbar buttons (all 4 buttons work)
- [ ] Use File menu > New Folder (creates folder)

---

## Bug Fixes Applied During Testing
- [x] **TODO-052 Critical Fix #1**: Fixed missing `return` in empty name validation (SidebarView.swift:586-588)
- [x] **TODO-052 Critical Fix #2**: Replaced deprecated `onCommit` with modern `.onSubmit` modifier
- [x] **TODO-052 Critical Fix #3**: Added `@FocusState` for automatic TextField focus when rename starts
- [x] **TODO-052 Critical Fix #4**: Added `.task` modifier to set focus automatically
- [x] **TODO-052 Critical Fix #5**: Added `.onChange(of: focus)` to cancel rename if user clicks away
- [x] **TODO-052 Critical Fix #6**: Added `documentStore.refresh()` to update UI after rename (SidebarView.swift:632-634)

---

## Issues Found

### Issue 1:
- **Test Item:**
- **Expected:**
- **Actual:**
- **Error Messages:**
- **Severity:** Critical / High / Medium / Low
- **Steps to Reproduce:**

### Issue 2:
- **Test Item:**
- **Expected:**
- **Actual:**
- **Error Messages:**
- **Severity:** Critical / High / Medium / Low
- **Steps to Reproduce:**

### Issue 3:
- **Test Item:**
- **Expected:**
- **Actual:**
- **Error Messages:**
- **Severity:** Critical / High / Medium / Low
- **Steps to Reproduce:**

---

## Summary

### Passed: __ / __
### Failed: __ / __
### Blocked: __ / __

### Overall Status: ⬜ Not Started | 🟡 In Progress | 🟢 Passed | 🔴 Failed

### General Notes:
