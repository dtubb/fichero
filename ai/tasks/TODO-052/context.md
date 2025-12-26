# Context for TODO-052: Fix Inline Rename to Use SwiftUI Default Pattern

## Background
Current rename functionality doesn't use the standard SwiftUI inline editing pattern. Need to implement native macOS-style inline rename.

## What you need to know
- SwiftUI TextField with @FocusState is the standard pattern
- Use .onSubmit for Enter key handling
- Use .onExitCommand for Escape key cancellation
- sample_code directory has TextField examples
- Backend API endpoint for rename should already exist (check from TODO-002)
- Follow macOS Finder rename behavior as reference
