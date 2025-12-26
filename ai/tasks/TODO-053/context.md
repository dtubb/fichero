# Context for TODO-053: Fix Delete Functionality in Sidebar and Backend

## Background
Delete functionality needs to work in both sidebar (UI removal) and backend (database persistence). User reported this is currently broken.

## What you need to know
- SwiftUI .confirmationDialog for confirmation UI
- Backend API should have delete endpoint (check API client)
- Delete should update @Observable state to trigger UI refresh
- Follow macOS confirmation dialog patterns
- Backend context: ai/contexts/backend/overview.md
- Error handling is critical - show user if delete fails
