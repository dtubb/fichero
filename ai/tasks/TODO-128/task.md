# TODO-128: Flatten Automation Sidebar - Remove Folder Structure

## What to do
Remove the folder-based organization (Schedules/Triggers disclosure groups with inline + buttons) from the Automation sidebar and replace with a flat list using item icons to distinguish types, matching other sidebar modes.

## Steps
- [ ] Step 1: Remove `DisclosureGroup` wrappers for Schedules and Triggers in `AutomationSidebarContent.swift`
- [ ] Step 2: Create flat list with both schedules and triggers as direct `SidebarItemRow` entries
- [ ] Step 3: Remove inline + buttons from disclosure group headers
- [ ] Step 4: Remove "Use + buttons above to add automation" hint message
- [ ] Step 5: Update section header to show total count (schedules + triggers)
- [ ] Step 6: Test selection, rename, delete, and context menu operations

## Files
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Views/Sidebar/Modes/AutomationSidebarContent.swift` (main changes)

## Questions for Human
- [ ] Question 1: Should schedules and triggers be intermixed or should schedules come first, then triggers?
    Answer: Group by type (schedules first, then triggers) for easier scanning
- [ ] Question 2: Should there be section headers separating the groups?
    Answer: No section headers - icons are sufficient to distinguish types (clock vs bolt)

## Implementation Notes

### Current Structure (Lines 66-92)
```swift
Section {
    // Schedules subsection (DisclosureGroup)
    schedulesSubsection(schedules)

    // Triggers subsection (DisclosureGroup)
    triggersSubsection(triggers)

    // Empty state hint
    if schedules.isEmpty && triggers.isEmpty && !isLoading {
        Text("Use + buttons above to add automation")
            .foregroundStyle(.secondary)
            .font(.caption)
            .padding(.vertical, 4)
    }
} header: {
    LibrarySectionHeader(...)
}
```

### Target Structure
```swift
Section {
    // Schedules (flat list)
    ForEach(scheduleItems) { item in
        SidebarItemRow(...)
            .tag(item.id)
    }

    // Triggers (flat list)
    ForEach(triggerItems) { item in
        SidebarItemRow(...)
            .tag(item.id)
    }

    // Empty state
    if schedules.isEmpty && triggers.isEmpty && !isLoading {
        Text("No automation items")
            .foregroundStyle(.secondary)
            .font(.caption)
            .padding(.vertical, 4)
    }
} header: {
    LibrarySectionHeader(
        library: library,
        itemCount: schedules.count + triggers.count,  // Combined count
        isCurrentLibrary: library.id == windowState.libraryId
    )
}
```

### Remove These Functions
- `schedulesSubsection(_:)` (lines 94-142)
- `triggersSubsection(_:)` (lines 144-192)

### Keep These
- `scheduleActionCallback(_:_:)` - needed for context menu actions
- `triggerActionCallback(_:_:)` - needed for context menu actions
- `handleSelection(_:)` - needed for item selection

## Visual Comparison

**Before:**
```
Global
  > Schedules (0) [+]
  > Triggers (0) [+]
  Use + buttons above to add automation
```

**After:**
```
Global (0)
  [No automation items]
```

Or with items:
```
Global (3)
  🕐 Weekly Report
  🕐 Daily Backup
  ⚡ New File Trigger
```

## Need help?
- Verify icon choices are clear (clock for schedules, bolt for triggers)
- Ensure action callbacks still work correctly in flat structure
