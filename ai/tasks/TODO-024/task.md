# TODO-024: Fix Frontend Import UI and Update Issues

## What to do
Investigate and fix the SwiftUI import interface issues where the UI doesn't update after file/folder import and shows layout recursion warnings.

## Steps
- [ ] Step 1: Reproduce the import issue described in human_note.md
- [ ] Step 2: Identify the source of layout recursion warnings in SwiftUI
- [ ] Step 3: Fix the UI update mechanism after successful import
- [ ] Step 4: Test import functionality with both files and folders
- [ ] Step 5: Review delete functionality as mentioned in the note
- [ ] Step 6: Update TODO-004 if backend changes are needed

## Files
- File to change: Fichero/Fichero/Views/Browser/* (import-related views)
- File to change: Fichero/Fichero/Services/APIClient.swift (if API integration issues)
- File to review: human_note.md (original issue description)

## Questions for Human
- [ ] Question 1: Should I focus only on the UI issues or also investigate backend integration?
    Answer: [Focus on frontend UI issues first, backend is separate task]
- [ ] Question 2: Are there specific SwiftUI views or components that handle import functionality?
    Answer: [Need to identify import-related views in Browser module]
- [ ] Question 3: Should delete functionality review be part of this task or separate?
    Answer: [Include basic review, create separate task if major issues found]

## Answers and Implementation
- [Will investigate layout recursion warnings and UI update mechanism]
- [Will test with sample files from human_note.md paths]
- [Will coordinate with TODO-004 backend import endpoint work]

## Need help?
- Ask if anything is unclear
- Keep it simple