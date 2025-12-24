# TODO-032: Refactor Sidebar Component Structure

## What to do
Refactor the monolithic SidebarView.swift by extracting nested components to separate files to improve code organization and maintainability.

## Steps
- [ ] Step 1: Create new SwiftUI file for SidebarItemRow component
- [ ] Step 2: Create new SwiftUI file for InlineRenameField component
- [ ] Step 3: Create new SwiftUI file for SectionHeader component
- [ ] Step 4: Move component code from SidebarView.swift to respective files
- [ ] Step 5: Update imports and dependencies in SidebarView.swift
- [ ] Step 6: Test each component individually
- [ ] Step 7: Verify overall sidebar functionality

## Files
- File to change: Fichero/Fichero/Views/SidebarView.swift
- New file: Fichero/Fichero/Views/SidebarItemRow.swift
- New file: Fichero/Fichero/Views/InlineRenameField.swift
- New file: Fichero/Fichero/Views/SectionHeader.swift

## Questions for Human
- [ ] Question 1: Should I preserve the exact same component structure and naming?
    Answer: Make it better. Do the right thing.
- [ ] Question 2: Are there any specific SwiftUI patterns or conventions I should follow?
    Answer: Follow best practices. Look up sample code if need be. Look in sample_code for ideas and best practices. 

## Answers and Implementation
- [Summary of decisions made]
- [Implementation approach chosen]

## Need help?
- Ask if anything is unclear
- Keep it simple