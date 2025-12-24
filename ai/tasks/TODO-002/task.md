# TODO-002: Complete In Line Rename

## What to do
Implement inline rename functionality for sidebar items in the Fichero frontend.

## Steps
- [x] Step 1: Review TODO-001 analysis for inline rename requirements
- [x] Step 2: Implement text field editing when "Rename..." context menu is selected
- [x] Step 3: Add Enter to confirm, Escape to cancel functionality
- [x] Step 4: Integrate with backend API for rename operations
- [x] Step 5: Fix compile errors and build issues
- [ ] Step 6: Test with different item types (documents, folders, searches, etc.)

## Files
- File to change: Fichero/Views/SidebarView.swift
- File to change: Fichero/Views/SidebarItemRow.swift
- File to reference: src/fichero/api/routes/documents.py (backend update endpoint)

## Questions for Human
- [ ] Question 1: Should inline rename support all sidebar item types equally?
    Answer: Yes.
- [ ] Question 2: Any specific UI/UX requirements for the rename text field?
    Answer: Use macOS conventions. Should come standard with sidebarpy look at apple docs. 

## Answers and Implementation
- [Summary of decisions made]
- [Implementation approach chosen]

## Need help?
- Ask if anything is unclear
- Keep it simple