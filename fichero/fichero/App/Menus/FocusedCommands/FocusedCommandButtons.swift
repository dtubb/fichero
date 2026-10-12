// Focused command buttons for menu items.
//
// This module is split across several extension files for clarity:
// - FocusedCommandButtons+FocusedValues.swift: FocusedValueKey definitions and FocusedValues extension
// - FocusedCommandButtons+SidebarActions.swift: Sidebar action buttons (New Folder, Import, Open in New Tab/Window)
// - FocusedCommandButtons+ItemVerbs.swift: the item verbs (Rename, Delete, Exclude, Bookmark, Add to Workspace,
//   Export a Copy), one item each for the context menus and Edit / File
// - FocusedCommandButtons+CreationActions.swift: Creation buttons (Chat, Workflow, Chain, Comparison, Schedule)
//   (menu audit 2026-09-17: this listed a "Search" button that has never existed here — removed)
// - FocusedCommandButtons+UndoNavigation.swift: Navigation and undo buttons
// - FocusedCommandButtons+Workflow.swift: Workflow execution button
