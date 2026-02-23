# Fichero Refactoring Progress

> **Last Updated:** 2026-02-22
> **Status:** All refactoring done + SwiftLint 330→69 violations

---

## Summary

| Metric | Count |
|--------|-------|
| Total target files | 37 |
| Completed | 35 |
| In Progress | 0 |
| Blocked | 1 |
| Skipped | 2 |
| Remaining | 0 |

---

## Batch 1 — High-Priority Views (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 1 | `Views/Library/DocumentInspector.swift` | 605→139 | <200 | done | [#145](https://github.com/dtubb/fichero/issues/145) |
| 2 | `Views/Automation/TriggerEditorView.swift` | 605→221 | <200 | done | [#146](https://github.com/dtubb/fichero/issues/146) |
| 3 | `Views/Settings/SettingsView.swift` | 589→33 | <200 | done | [#147](https://github.com/dtubb/fichero/issues/147) |

## Batch 2 — Sidebar & Workflow (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 4 | `Views/Sidebar/SidebarItemRow.swift` | 567→146 | <200 | done | [#148](https://github.com/dtubb/fichero/issues/148) |
| 5 | `Views/Workflow/WorkflowEditor.swift` | 540→161 | <200 | done | [#144](https://github.com/dtubb/fichero/issues/144) |
| 6 | `Views/Workflow/WorkflowChainListView.swift` | 527→147 | <200 | done | [#149](https://github.com/dtubb/fichero/issues/149) |

## Batch 3 — Providers & Activity (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 7 | `Views/AIProviders/ProvidersView.swift` | 528→138 | <200 | done | [#150](https://github.com/dtubb/fichero/issues/150) |
| 8 | `Views/Sidebar/Modes/ActivitySidebarContent.swift` | 509→166 | <200 | done | [#151](https://github.com/dtubb/fichero/issues/151) |
| 9 | `Views/Chat/ChatInspector.swift` | 509→73 | <200 | done | [#152](https://github.com/dtubb/fichero/issues/152) |

## Batch 4 — Comparison & Batch Views (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 10 | `Views/ModelComparison/ModelComparisonView.swift` | 503→39 | <200 | done | [#153](https://github.com/dtubb/fichero/issues/153) |
| 11 | `Views/Batch/BatchDetailView.swift` | 484→146 | <200 | done | [#154](https://github.com/dtubb/fichero/issues/154) |
| 12 | `Views/Workflow/DynamicConfigView.swift` | 479→95 | <200 | done | [#155](https://github.com/dtubb/fichero/issues/155) |

## Batch 5 — Actions & Workflow Output (PARTIAL)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 13 | `Views/Actions/ActionLibraryView.swift` | 478 | <200 | blocked | [#156](https://github.com/dtubb/fichero/issues/156) |
| 14 | `Views/Workflow/WorkflowOutputLog.swift` | 477→168 | <200 | done | [#157](https://github.com/dtubb/fichero/issues/157) |
| 15 | `Views/Automation/ScheduleEditorView.swift` | 455→141 | <200 | done | [#158](https://github.com/dtubb/fichero/issues/158) |

## Batch 6 — Sidebar, Providers, Inspectors (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 16 | `Views/Chat/ComparisonDetailView.swift` | 443→46 | <200 | done | [#159](https://github.com/dtubb/fichero/issues/159) |
| 17 | `Views/Sidebar/SidebarView.swift` | 436→183 | <200 | done | [#160](https://github.com/dtubb/fichero/issues/160) |
| 18 | `Views/AIProviders/AddProviderSheet.swift` | 427→96 | <200 | done | [#161](https://github.com/dtubb/fichero/issues/161) |

## Batch 7 — Activity, Workflow, Components (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 19 | `Views/Workflow/WorkflowInspector.swift` | 424→174 | <200 | done | [#162](https://github.com/dtubb/fichero/issues/162) |
| 20 | `Views/Activity/ActivityProgressView.swift` | 424→39 | <200 | done | [#163](https://github.com/dtubb/fichero/issues/163) |
| 21 | `Views/Components/WorkflowExecutionRow.swift` | 420→211 | <200 | done | [#164](https://github.com/dtubb/fichero/issues/164) |

## Batch 8 — Remaining Views (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 22 | `Views/Library/ArtifactsBrowserView.swift` | 409 | <200 | skipped | — (not in Xcode project) |
| 23 | `Views/Automation/TriggerDetailView.swift` | 402→144 | <200 | done | [#165](https://github.com/dtubb/fichero/issues/165) |

## Batch 9 — Models (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 24 | `Models/WorkflowTypes.swift` | 696→272 | <300 | done | [#166](https://github.com/dtubb/fichero/issues/166) |
| 25 | `Models/DocumentStore.swift` | 611→185 | <300 | done | [#167](https://github.com/dtubb/fichero/issues/167) |
| 26 | `Models/SidebarItem.swift` | 599→184 | <300 | done | [#168](https://github.com/dtubb/fichero/issues/168) |
| 27 | `Models/LibraryManager.swift` | 577→198 | <300 | done | [#169](https://github.com/dtubb/fichero/issues/169) |

## Batch 10 — App Entry Point & Types (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 28 | `FicheroApp.swift` | 571→223 | <300 | done | [#170](https://github.com/dtubb/fichero/issues/170) |
| 29 | `Services/ActivityTypes.swift` | 617→230 | <300 | done | [#171](https://github.com/dtubb/fichero/issues/171) |

## Batch 11 — Services (Non-Generated) (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 30 | `Services/WorkflowStreamService.swift` | 595→294 | <300 | done | [#172](https://github.com/dtubb/fichero/issues/172) |
| 31 | `Services/ActionLibraryService.swift` | 569 | <300 | skipped | — (not in Xcode project) |
| 32 | `Services/ModelComparisonService.swift` | 567→226 | <300 | done | [#173](https://github.com/dtubb/fichero/issues/173) |

## Batch 12 — Services (Non-Generated, continued) (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 33 | `Services/AppleScriptSupport.swift` | 533→206 | <300 | done | [#174](https://github.com/dtubb/fichero/issues/174) |
| 34 | `Services/ProviderService.swift` | 485→172 | <300 | done | [#175](https://github.com/dtubb/fichero/issues/175) |
| 35 | `Services/AutomationService.swift` | 482→158 | <300 | done | [#176](https://github.com/dtubb/fichero/issues/176) |

## Batch 13 — Services (Final) (DONE)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 36 | `Services/IntegrationsService.swift` | 474→235 | <300 | done | [#177](https://github.com/dtubb/fichero/issues/177) |
| 37 | `Services/WorkflowExecutionObserver.swift` | 407→158 | <300 | done | [#178](https://github.com/dtubb/fichero/issues/178) |
| 38 | `Services/DragDropService.swift` | 402→265 | <300 | done | [#179](https://github.com/dtubb/fichero/issues/179) |

## Post-Refactoring Tasks

| # | Task | Status | Issue |
|---|------|--------|-------|
| A | SwiftLint violations 330→69 (261 fixed) | done | [#181](https://github.com/dtubb/fichero/issues/181) |
| B | Library View 18-week UX transformation | in-progress | [#180](https://github.com/dtubb/fichero/issues/180) |
| B.1 | Keyboard shortcuts (Delete/Return/Space) | done | [#184](https://github.com/dtubb/fichero/issues/184) |
| B.2 | Inline document title editing (table view + context menu) | done | [#185](https://github.com/dtubb/fichero/issues/185) |
| B.3 | Type-to-select: jump to matching document by typing | done | [#186](https://github.com/dtubb/fichero/issues/186) |
| B.4 | Selection modifiers: Shift+click range, Cmd+click toggle | done | [#187](https://github.com/dtubb/fichero/issues/187) |
| B.5 | Arrow key navigation in icon/grid views | done | [#188](https://github.com/dtubb/fichero/issues/188) |
| B.6 | Tab key to cycle focus between sidebar, content, inspector | done | [#189](https://github.com/dtubb/fichero/issues/189) |
| B.7 | Persist inspector tab selection across sessions | done | [#190](https://github.com/dtubb/fichero/issues/190) |
| B.8 | Sort menu with persisted sort order in library view | done | [#191](https://github.com/dtubb/fichero/issues/191) |
| C | Add XCTest coverage — SSE + ActivityTypes + SidebarItem (89 tests) | done | [#182](https://github.com/dtubb/fichero/issues/182) |
| D | Resolve TODOs and stale docs | done | [#183](https://github.com/dtubb/fichero/issues/183) |

---

## Status Legend

- `ready` — Issue created, ready for agent pickup
- `pending` — Not yet started, no issue created
- `in-progress` — Agent actively working on it
- `done` — Refactored, built, pushed, issue closed
- `blocked` — Waiting on dependency

## Notes

- All file paths are relative to `fichero-swiftui/fichero-swiftui/`
- View targets: <200 lines. Model/Service targets: <300 lines
- Generated files (`*Generated.swift`) are excluded — do not touch
- Issues are created on `dtubb/fichero` via GitHub MCP tools
