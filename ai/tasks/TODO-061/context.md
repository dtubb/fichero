# TODO-061: Context

## Purpose
Refactor the app to use proper SwiftUI observable pattern instead of manual refresh hacks. This fixes the root cause of rename/delete not updating UI.

## Background
Currently the app uses an anti-pattern:
- ContentView computes snapshot arrays from stores
- Passes snapshots to SidebarView as plain parameters
- Uses manual refresh counters and .id() hacks
- Doesn't work reliably

Proper SwiftUI pattern:
- Parent owns stores with @StateObject
- Child observes stores with @ObservedObject
- Child computes items internally
- SwiftUI automatically updates on @Published changes

## Related Tasks
- TODO-052: Inline rename (broken UI refresh)
- TODO-053: Delete (broken UI refresh)
- Root cause for both is the architecture

## Known Risks
- Large refactoring touching many files
- Must ensure services have @Published properties
- Must update all store references throughout app
- Callbacks in SearchView/ChatView may need updates

## Why This Matters
This is the foundation for all UI updates. Getting this right means:
- Rename will work
- Delete will work
- Create will work
- All future CRUD will work
- No more manual refresh hacks needed
