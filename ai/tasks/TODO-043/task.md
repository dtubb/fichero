# TODO-043: Fix Sidebar Build Errors

## What to do
Fix compilation errors in SidebarItemRow.swift to resolve build failures

## Steps
- [ ] Step 1: Analyze the specific errors in SidebarItemRow.swift
- [ ] Step 2: Identify missing types: CacheModel and InlineFolderCreation
- [ ] Step 3: Fix contextual base references for opacity and scale
- [ ] Step 4: Remove unused variable 'newFolder'
- [ ] Step 5: Test build after fixes

## Files
- File to change: Fichero/Fichero/Views/Sidebar/SidebarItemRow.swift

## Questions for Human
- [ ] Question 1: Where should CacheModel be imported from or defined?
    Answer: Need to check existing codebase for CacheModel definition or import
- [ ] Question 2: What is the correct implementation for InlineFolderCreation?
    Answer: Need to check if this is a custom type or should be imported
- [ ] Question 3: What should be the contextual base for opacity and scale references?
    Answer: Likely need to prefix with appropriate view or animation context

## Answers and Implementation
- Will analyze the codebase to find existing CacheModel and InlineFolderCreation implementations
- Will fix contextual references based on SwiftUI view hierarchy
- Will remove unused variables and clean up code

## Need help?
- May need clarification on expected behavior for folder creation
- Keep it simple and focused on compilation fixes