# Context: Universal Creation

## Problem
Currently, item creation commands (New Folder, New Search, New Chat, etc.) are conditionally enabled based on which sidebar mode is active. This creates a poor UX where:
- Data menu items are grayed out when in "wrong" sidebar
- Context menu shows disabled items
- Users must switch sidebars before creating items

## User Request
> "I should be able to add anywhere any of them… e.g. be in the search sidebar, and add a chat, the sidebar changes to chat, and its adds a chat"

## Current Architecture

### Focused Values System
The app uses SwiftUI's `@FocusedValue` pattern for menu commands:
1. `SidebarView` provides handlers via `sidebarFocusedValues`
2. `FocusedCommandButtons` read these values to enable/disable menu items
3. Handlers are marked optional (`createChain: (() -> Void)?`)
4. When optional handlers are nil, buttons are disabled

### Why Items Get Disabled
- `SidebarFocusedValuesConfig` has optional handler properties
- Handlers are conditionally provided (e.g., `createSchedule` only set in automation mode)
- Buttons check `sidebarActions?.createSchedule == nil` and disable

## Solution Architecture

### Make All Handlers Non-Optional
Change from:
```swift
var createSchedule: (() -> Void)?
```

To:
```swift
let createSchedule: () -> Void
```

### Always Provide Handlers
Instead of conditional provision, always provide all handlers in `sidebarFocusedValues`.

### Mode Switching in Handlers
Each creation function switches to appropriate sidebar mode:
```swift
func createNewSchedule() {
    sidebarMode = .automation  // Switch first
    sidebarState.showingScheduleCreation = true  // Then show UI
}
```

## Benefits
1. **Discoverability**: Users see all creation options always available
2. **Flexibility**: Create items from any context
3. **Natural UX**: System handles mode switching automatically
4. **Consistency**: Matches macOS patterns (e.g., Finder's File menu works everywhere)

## Related Files
- `SidebarView.swift` - Main sidebar with creation functions
- `SidebarViewExtensions.swift` - Config structs
- `FocusedCommandButtons.swift` - Menu button implementations
- `FicheroApp.swift` - Data menu definition
- `SidebarBottomToolbar` - Bottom + button menu

## Testing Considerations
- Test all creation flows from each sidebar mode
- Verify keyboard shortcuts work everywhere
- Ensure sidebar switches to correct mode
- Check that newly created items are selected/visible
