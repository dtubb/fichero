# TODO-127: Universal Creation - Enable All Create Commands Everywhere

## What to do
Allow all item creation commands (folder, search, chat, workflow, chain, comparison, schedule, trigger) to work from any sidebar mode, automatically switching to the appropriate mode when items are created.

## Steps
- [ ] Step 1: Remove conditional logic in `sidebarFocusedValues` - always provide all handlers
- [ ] Step 2: Update creation functions to switch sidebar mode appropriately (e.g., `createNewChat()` sets `sidebarMode = .chat`)
- [ ] Step 3: Update `FocusedCommandButtons.swift` to remove `.disabled()` checks where not needed
- [ ] Step 4: Test all creation flows from each sidebar mode
- [ ] Step 5: Verify Data menu items are never grayed out inappropriately

## Files
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Views/Sidebar/SidebarView.swift` (sidebarFocusedValues extension)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Views/Sidebar/SidebarViewExtensions.swift` (SidebarFocusedValuesConfig)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Views/Menu/FocusedCommandButtons.swift` (button disabled states)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/FicheroApp.swift` (Data menu commands)

## Questions for Human
- [ ] Question 1: Should creation always switch sidebar modes, or should items be created in the background?
    Answer: Switch sidebar modes - more discoverable and user can see the newly created item immediately
- [ ] Question 2: Should the bottom toolbar show mode-specific items only, or all items?
    Answer: Keep bottom toolbar mode-specific, but Data menu should be universal

## Implementation Notes

### Current Behavior
- Handlers are conditionally provided in `SidebarFocusedValuesConfig`
- Data menu items get disabled when handlers are nil
- Context menu shows grayed out items

### Target Behavior
- All handlers always available (never nil)
- Creation functions handle mode switching internally
- Example: `createNewSchedule()` sets `sidebarMode = .automation` before showing creation sheet

### Code Changes

```swift
// SidebarView.swift - sidebarFocusedValues (line 205)
// Remove Optional wrapping - always provide handlers
.sidebarFocusedValues(config: SidebarFocusedValuesConfig(
    selectedItem: selectedItem,
    createFolder: handleCreateNewFolder,
    importFiles: importFiles,
    renameItem: handleRenameSelectedItem,
    deleteItem: handleDeleteSelectedItem,
    createSearch: createNewSearch,
    createChat: createNewChat,
    createWorkflow: createNewWorkflow,
    createChain: createNewChain,         // Not optional
    createComparison: createNewComparison, // Not optional
    createSchedule: createNewSchedule,   // Not optional
    createTrigger: createNewTrigger      // Not optional
))
```

```swift
// SidebarViewExtensions.swift - SidebarFocusedValuesConfig (line 211)
// Remove Optional types
struct SidebarFocusedValuesConfig {
    let selectedItem: SidebarItem?
    let createFolder: () -> Void
    let importFiles: (IngestMode) -> Void
    let renameItem: () -> Void
    let deleteItem: () -> Void
    let createSearch: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
    let createChain: () -> Void          // No longer optional
    let createComparison: () -> Void     // No longer optional
    let createSchedule: () -> Void       // No longer optional
    let createTrigger: () -> Void        // No longer optional
}
```

```swift
// FocusedCommandButtons.swift - Remove nil checks (line 293+)
struct FocusedNewChainButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Chain") {
            sidebarActions?.createChain()  // Remove the ? after createChain
        }
        .disabled(sidebarActions == nil)  // Only check if sidebarActions exists
    }
}
// Repeat for comparison, schedule, trigger buttons
```

## Need help?
- Verify all edge cases where handlers might be unavailable
- Test keyboard shortcuts work from all sidebar modes
