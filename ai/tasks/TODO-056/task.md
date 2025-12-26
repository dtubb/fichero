# TODO-056: Enable Drop on Search, Chat, and Workflow Sections

## What to do
Allow files and folders to be dropped on Search, Chat, and New Workflow section headers with appropriate actions.

## Steps
- [ ] Step 1: Identify Search, Chat, and Workflow section views
- [ ] Step 2: Add .dropDestination to each section header
- [ ] Step 3: Implement drop handling for Search (add to search scope)
- [ ] Step 4: Implement drop handling for Chat (initiate chat about document)
- [ ] Step 5: Implement drop handling for Workflow (add to workflow inputs)
- [ ] Step 6: Add visual feedback for valid drop zones
- [ ] Step 7: Run swiftlint
- [ ] Step 8: Test dropping files/folders on each section

## Files
- File to change: Fichero/Fichero/Views/Browser/SidebarView.swift (or related component)
- May need: Chat view, Search view, Workflow view integrations

## Questions for Human
- [ ] Question 1: What should happen when dropping on Search?
    Answer: Open Search view with dropped item in scope
- [ ] Question 2: What should happen when dropping on Chat?
    Answer: Open Chat view with dropped item as context
- [ ] Question 3: What should happen when dropping on Workflow?
    Answer: Open Workflow editor with dropped item as input

## Answers and Implementation
- Each section needs .dropDestination modifier
- Navigation to respective views with dropped item context
- Visual feedback during drag (highlight section)
- Handle multiple items if batch drop supported

## Need help?
- Depends on TODO-054 for core drag and drop patterns
- May need to update navigation state management
