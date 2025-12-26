# TODO-058: Add Menu Commands and Toolbar Items

## What to do
Add macOS menu bar commands and toolbar items for common sidebar operations.

## Steps
- [ ] Step 1: Review macOS menu command patterns in sample code
- [ ] Step 2: Add CommandMenu for File operations (New Folder, Import, Delete)
- [ ] Step 3: Add keyboard shortcuts (Cmd+N for New, Cmd+Delete, etc.)
- [ ] Step 4: Add toolbar using .toolbar modifier
- [ ] Step 5: Implement toolbar items (New Folder, Import, Search, etc.)
- [ ] Step 6: Connect menu/toolbar actions to existing functionality
- [ ] Step 7: Run swiftlint
- [ ] Step 8: Test menu commands and keyboard shortcuts
- [ ] Step 9: Test toolbar items

## Files
- File to change: Fichero/Fichero/FicheroApp.swift (for CommandMenu)
- File to change: Main window view (for toolbar)
- Reference: sample_code for menu and toolbar patterns

## Questions for Human
- [ ] Question 1: Which operations should have menu commands?
    Answer: New Folder, Import File, Delete, Rename, Search
- [ ] Question 2: Which items should appear in toolbar?
    Answer: New Folder, Import, Search (common actions)
- [ ] Question 3: What keyboard shortcuts to use?
    Answer: Follow macOS standards (Cmd+N, Cmd+Delete, Cmd+F, etc.)

## Answers and Implementation
- Use CommandMenu in App struct for menu bar
- Use .toolbar modifier for toolbar items
- Standard macOS keyboard shortcuts
- Connect to existing sidebar functionality
- Follow Apple HIG for menu organization

## Need help?
- Review macOS standard keyboard shortcuts
- Check sample code for CommandMenu examples
- Test accessibility of menu commands
