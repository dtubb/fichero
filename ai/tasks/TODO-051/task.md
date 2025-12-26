# TODO-051: Remove "Move to Folder" from Context Menu

## What to do
Remove the unused "Move to Folder" menu item from the sidebar context menu.

## Steps
- [ ] Step 1: Locate sidebar context menu code in SidebarView or related components
- [ ] Step 2: Remove "Move to Folder" menu item
- [ ] Step 3: Run swiftlint to ensure code quality
- [ ] Step 4: Build and test in Xcode
- [ ] Step 5: Verify context menu displays correctly without the item

## Files
- File to change: Fichero/Fichero/Views/Browser/SidebarView.swift (or related component)

## Questions for Human
- [ ] Question 1: Should this functionality be completely removed or just hidden?
    Answer: Completely removed as user specified "we do not need" it
- [ ] Question 2: Are there any related backend endpoints to deprecate?
    Answer: Will check during implementation, remove if unused

## Answers and Implementation
- Simple removal of menu item
- Ensure no broken references remain
- SwiftLint compliance required

## Need help?
- Check if "Move to Folder" was ever implemented
- Ensure removal doesn't break other menu functionality
