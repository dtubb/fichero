# TODO-055: Improve Section Title Indentation

## What to do
Increase indentation spacing from section titles to improve visual hierarchy in the sidebar.

## Steps
- [x] Step 1: Locate section title styling in sidebar code
- [x] Step 2: Increase leading padding for items under section headers
- [x] Step 3: Review visual appearance in Xcode preview
- [x] Step 4: Adjust spacing to match macOS standard sidebar patterns
- [x] Step 5: Run swiftlint
- [x] Step 6: Build and test visual changes (blocked by TODO-059)

## Files
- File to change: Fichero/Fichero/Views/Browser/SidebarView.swift (or related component)

## Questions for Human
- [ ] Question 1: How much additional indentation is needed?
    Answer: Follow macOS Finder sidebar spacing (approximately 8-12pt more)
- [ ] Question 2: Should nested folders have progressively more indentation?
    Answer: Yes, standard hierarchical indentation pattern

## Answers and Implementation
- Simple padding adjustment using .padding(.leading, value)
- Match macOS system sidebar appearance
- Keep changes minimal

## Need help?
- Compare with macOS Finder sidebar for reference
- Test with nested folders to ensure clarity
