# Context: Flatten Automation Sidebar

## Problem
The Automation sidebar uses a different organizational pattern than other sidebars:
- Uses `DisclosureGroup` folders for Schedules and Triggers
- Has inline + buttons in the disclosure group headers
- Shows a hint message "Use + buttons above to add automation"
- Inconsistent with Library, Search, Chat, and Workflows sidebars (which use flat lists)

## User Feedback
> "The schedules and triggers have their folders, I don't think that's needed. we can have them as a single list like the other sidebars, and then they have different icons. we don't need the right + button to add them or that message: Use + buttons above to add automations."

## Current Implementation

### AutomationSidebarContent.swift Structure
- Lines 66-92: Section with disclosure groups
- Lines 94-142: `schedulesSubsection()` with inline + button
- Lines 144-192: `triggersSubsection()` with inline + button
- Line 80: Hint message

### Why It Was Designed This Way
Likely to provide quick access to creation (inline + buttons), but:
- Inconsistent with rest of app
- Adds visual clutter
- Bottom toolbar already has + button
- Data menu already has creation commands

## Target Design

### Consistency with Other Sidebars
Match the pattern used in:
- **LibrarySidebarContent**: Flat list of documents/folders with icons
- **SearchSidebarContent**: Flat list of saved searches with icons
- **ChatSidebarContent**: Flat list of conversations with icons
- **WorkflowsSidebarContent**: Flat list of workflows with icons

### Visual Hierarchy
```
Library Header (Total Count)
  Icon | Schedule Name
  Icon | Schedule Name
  Icon | Trigger Name
```

Icons distinguish types:
- 🕐 (clock) for Schedules
- ⚡ (bolt) for Triggers

### Creation Flow
Users create schedules/triggers via:
1. Bottom toolbar + button → menu with "New Schedule" / "New Trigger"
2. Data menu → "New Schedule" / "New Trigger"
3. Context menu (when supported)

No need for inline + buttons.

## Benefits
1. **Consistency**: Matches all other sidebar modes
2. **Clarity**: Simpler visual hierarchy
3. **Reduced clutter**: No extra disclosure groups or + buttons
4. **Icon-based distinction**: Proven pattern from other sidebars

## Related Code
- `AutomationSidebarContent.swift` - Main file to modify
- `SidebarItemRow.swift` - Used for rendering (no changes needed)
- `SidebarItem.swift` - Model with `.schedule()` and `.trigger()` cases (no changes needed)

## Testing Considerations
- Verify icons are clear and distinguishable
- Check selection, rename, delete work correctly
- Ensure context menu actions (pause/resume/trigger) still function
- Test empty state messaging
