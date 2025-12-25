# TODO-043: Fix Sidebar Build Errors

## What to do
Fix compilation errors in SidebarItemRow.swift to resolve build failures

## Steps
- [x] Step 1: Analyze the specific errors in SidebarItemRow.swift
- [x] Step 2: Identify missing types: CacheModel and InlineFolderCreation
- [x] Step 3: Fix contextual base references for opacity and scale
- [x] Step 4: Remove unused variable 'newFolder'
- [x] Step 5: Test build after fixes

## Additional Steps Completed
- [x] Added 9 missing files to Xcode project to resolve "cannot find type in scope" errors
- [x] Fixed syntax errors in multiple files (CacheModel, PerformanceService, etc.)
- [x] Resolved type conformance issues (ObservableObject, Equatable)
- [x] Fixed API usage patterns and naming conflicts
- [x] Improved view modifier chaining
- [x] Simplified complex expressions causing compiler timeouts

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
- [x] Found and added CacheModel.swift to Xcode project (was missing from project file)
- [x] Found and added InlineFolderCreation.swift to Xcode project (was missing from project file)
- [x] Fixed contextual references by wrapping if-else in Group for proper view modifier chaining
- [x] Removed unused variables and cleaned up code
- [x] Fixed syntax errors in string interpolation and Color/NSColor conversion
- [x] Added ObservableObject conformance to PerformanceService for @StateObject usage
- [x] Resolved naming conflicts in ErrorService using self. disambiguation
- [x] Fixed benchmark API usage patterns throughout the codebase

## Need help?
- May need clarification on expected behavior for folder creation
- Keep it simple and focused on compilation fixes