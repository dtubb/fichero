# TODO-052: Fix Inline Rename to Use SwiftUI Default Pattern

## What to do
Implement native SwiftUI inline editing for folder and file rename functionality using standard macOS patterns with modern SwiftUI best practices.

## Steps
- [x] Step 1: Search Apple documentation for TextField and onSubmit patterns
- [x] Step 2: Review sample_code/Date Planner.swiftpm/App/TaskRow.swift for @FocusState pattern
- [x] Step 3: Add @FocusState to SidebarItemRow for focus management
- [x] Step 4: Replace deprecated onCommit with .onSubmit modifier
- [x] Step 5: Add .focused() modifier for automatic focus when rename starts
- [x] Step 6: Add .task modifier to set focus when renaming begins
- [x] Step 7: Add .onChange(of: focus) to cancel rename if focus is lost
- [x] Step 8: Keep validation (non-empty, max 255 chars) and Escape key cancellation
- [x] Step 9: Run SwiftLint and fix any violations
- [x] Step 10: Build with Xcode to verify compilation
- [x] Step 11: Write Xcode unit tests for rename functionality
- [ ] Step 12: Manual testing - verify TextField appears, accepts input, submits on Return

## Files
- File to change: Fichero/Fichero/Views/Sidebar/SidebarView.swift
- Reference: sample_code/Date Planner.swiftpm/App/TaskRow.swift
- Apple docs: https://developer.apple.com/documentation/swiftui/textfield

## Research Requirements
- [x] Search sosumi (Apple docs) for TextField onSubmit patterns
- [x] Review TextField best practices for inline editing
- [x] Study @FocusState usage in sample code

## Testing Requirements
- [x] SwiftLint must pass (or document new violations)
- [x] Xcode build must succeed
- [ ] Unit tests for:
  - Rename starts with correct focus
  - Return key submits rename
  - Escape key cancels rename
  - Empty name validation rejects
  - 255+ character name validation rejects
  - Focus loss cancels rename

## Questions for Human
- [x] Question 1: Should rename validation prevent empty names or special characters?
    Answer: Yes, basic validation - no empty names, max 255 chars, backend handles special chars
- [x] Question 2: Should there be a maximum length for names?
    Answer: Follow macOS file system limits (255 characters)

## Implementation Pattern
```swift
@FocusState private var isRenameFocused: Bool

TextField("Name", text: $renameState.editingName)
    .focused($isRenameFocused)
    .onSubmit { commitRename() }
    .onExitCommand { renameState.cancelRename(); isRenameFocused = false }
    .task { isRenameFocused = true }
    .onChange(of: isRenameFocused) { _, isFocused in
        if !isFocused && renameState.renamingItemId != nil {
            renameState.cancelRename()
        }
    }
```

## Known Issues from Initial Implementation
- Bug fixed: Missing `return` in empty name validation
- Bug fixed: Deprecated `onCommit` caused TextField to flash/disappear
- Bug fixed: No auto-focus when rename started

## Need help?
- See sosumi Apple docs for TextField modern patterns
- Review sample_code/Date Planner.swiftpm for complete example
- Test with edge cases (long names, special characters, focus loss)
