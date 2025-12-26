# TODO-053: Fix Delete Functionality in Sidebar and Backend

## What to do
Ensure delete removes items from sidebar UI and persists deletion to backend database.

## Steps
- [ ] Step 1: Review current delete implementation in sidebar
- [ ] Step 2: Add confirmation dialog using .confirmationDialog modifier
- [ ] Step 3: Implement delete in sidebar state (remove from UI)
- [ ] Step 4: Call backend API delete endpoint
- [ ] Step 5: Handle delete errors with user feedback
- [ ] Step 6: Verify backend persistence (check database)
- [ ] Step 7: Run swiftlint and fix violations
- [ ] Step 8: Test delete with files and folders

## Files
- File to change: Fichero/Fichero/Views/Browser/SidebarView.swift (or related component)
- Backend endpoint: Check existing delete API in backend

## Questions for Human
- [ ] Question 1: Should delete move to trash or permanently delete?
    Answer: Check backend implementation, prefer move to trash if available
- [ ] Question 2: Should there be a "Delete" keyboard shortcut (Cmd+Delete)?
    Answer: Yes, add keyboard shortcut for better UX

## Answers and Implementation
- Add confirmation dialog before delete
- Call backend delete API endpoint
- Remove from sidebar state after successful backend deletion
- Show error message if deletion fails
- Add keyboard shortcut support

## Need help?
- Check backend API documentation for delete endpoint
- Verify database deletion occurs properly
