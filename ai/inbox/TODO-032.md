# TODO-032: Refactor Sidebar Component Structure

## Description
Refactor the monolithic SidebarView.swift by extracting nested components to separate files to improve code organization and maintainability.

## Requirements
- Extract SidebarItemRow to separate file: `SidebarItemRow.swift`
- Extract InlineRenameField to separate file: `InlineRenameField.swift`
- Extract SectionHeader to separate file: `SectionHeader.swift`
- Maintain all existing functionality
- Ensure proper imports and dependencies

## Benefits
- Reduce main file size from 994 lines to more manageable size
- Improve code organization and readability
- Make components more reusable
- Easier to maintain and test individual components

## Approach
1. Create new SwiftUI files for each component
2. Move component code while preserving functionality
3. Update imports and dependencies
4. Test each component individually
5. Verify overall sidebar functionality

## Priority
P1 (High) - Architectural improvement

## Depends On
- TODO-031: Fix SwiftLint Violations (recommended but not required)

## Estimated Effort
3-5 hours