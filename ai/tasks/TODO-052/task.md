# TODO-052: Fix Inline Rename to Use SwiftUI Default Pattern

## What to do
Implement native SwiftUI inline editing for folder and file rename functionality using standard macOS patterns.

## Steps
- [ ] Step 1: Review current rename implementation in sidebar
- [ ] Step 2: Check sample_code for SwiftUI TextField inline editing patterns
- [ ] Step 3: Implement inline rename using TextField with .onSubmit
- [ ] Step 4: Add proper keyboard handling (Enter to confirm, Escape to cancel)
- [ ] Step 5: Update backend API call to persist rename
- [ ] Step 6: Run swiftlint and fix violations
- [ ] Step 7: Test rename with various file and folder names

## Files
- File to change: Fichero/Fichero/Views/Browser/SidebarView.swift (or related component)
- Reference: sample_code for TextField patterns

## Questions for Human
- [ ] Question 1: Should rename validation prevent empty names or special characters?
    Answer: Yes, basic validation - no empty names, backend will handle special chars
- [ ] Question 2: Should there be a maximum length for names?
    Answer: Follow macOS file system limits (255 characters)

## Answers and Implementation
- Use SwiftUI TextField with focus state
- Implement standard macOS rename behavior
- Validate input before API call
- Show error feedback if rename fails

## Need help?
- Review sample_code for TextField best practices
- Test with edge cases (long names, special characters)
