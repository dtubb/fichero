# TODO-055: Improve Section Title Indentation

## What to do
Increase indentation spacing from section titles to improve visual hierarchy in the sidebar.

## Steps
- [ ] Step 1: Locate section title styling in sidebar code
- [ ] Step 2: Increase leading padding for items under section headers
- [ ] Step 3: Review visual appearance in Xcode preview
- [ ] Step 4: Adjust spacing to match macOS standard sidebar patterns
- [ ] Step 5: Run swiftlint
- [ ] Step 6: Build and test visual changes

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
