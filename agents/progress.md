# Fichero Refactoring Progress

> **Last Updated:** 2026-02-20
> **Status:** Batch 2 complete — 6/37 files refactored

---

## Summary

| Metric | Count |
|--------|-------|
| Total target files | 37 |
| Completed | 6 |
| In Progress | 0 |
| Remaining | 31 |

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

## Batch 3 — Providers & Activity (NEXT)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 7 | `Views/AIProviders/ProvidersView.swift` | 528 | <200 | pending | — |
| 8 | `Views/Sidebar/Modes/ActivitySidebarContent.swift` | 509 | <200 | pending | — |
| 9 | `Views/Chat/ChatInspector.swift` | 509 | <200 | pending | — |

## Batch 4 — Comparison & Batch Views

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 10 | `Views/ModelComparison/ModelComparisonView.swift` | 503 | <200 | pending | — |
| 11 | `Views/Batch/BatchDetailView.swift` | 484 | <200 | pending | — |
| 12 | `Views/Workflow/DynamicConfigView.swift` | 479 | <200 | pending | — |

## Batch 5 — Actions & Workflow Output

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 13 | `Views/Actions/ActionLibraryView.swift` | 478 | <200 | pending | — |
| 14 | `Views/Workflow/WorkflowOutputLog.swift` | 477 | <200 | pending | — |
| 15 | `Views/Automation/ScheduleEditorView.swift` | 455 | <200 | pending | — |

## Batch 6 — Sidebar, Providers, Inspectors

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 16 | `Views/Chat/ComparisonDetailView.swift` | 443 | <200 | pending | — |
| 17 | `Views/Sidebar/SidebarView.swift` | 436 | <200 | pending | — |
| 18 | `Views/AIProviders/AddProviderSheet.swift` | 427 | <200 | pending | — |

## Batch 7 — Activity, Workflow, Library Views

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 19 | `Views/Workflow/WorkflowInspector.swift` | 423 | <200 | pending | — |
| 20 | `Views/Activity/ActivityProgressView.swift` | 423 | <200 | pending | — |
| 21 | `Views/Components/WorkflowExecutionRow.swift` | 419 | <200 | pending | — |

## Batch 8 — Remaining Views

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 22 | `Views/Library/ArtifactsBrowserView.swift` | 409 | <200 | pending | — |
| 23 | `Views/Automation/TriggerDetailView.swift` | 401 | <200 | pending | — |

## Batch 9 — Models

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 24 | `Models/WorkflowTypes.swift` | 695 | <300 | pending | — |
| 25 | `Models/DocumentStore.swift` | 610 | <300 | pending | — |
| 26 | `Models/SidebarItem.swift` | 598 | <300 | pending | — |
| 27 | `Models/LibraryManager.swift` | 577 | <300 | pending | — |

## Batch 10 — App Entry Point & Types

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 28 | `FicheroApp.swift` | 570 | <300 | pending | — |
| 29 | `Services/ActivityTypes.swift` | 616 | <300 | pending | — |

## Batch 11 — Services (Non-Generated)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 30 | `Services/WorkflowStreamService.swift` | 594 | <300 | pending | — |
| 31 | `Services/ActionLibraryService.swift` | 569 | <300 | pending | — |
| 32 | `Services/ModelComparisonService.swift` | 567 | <300 | pending | — |

## Batch 12 — Services (Non-Generated, continued)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 33 | `Services/AppleScriptSupport.swift` | 532 | <300 | pending | — |
| 34 | `Services/ProviderService.swift` | 484 | <300 | pending | — |
| 35 | `Services/AutomationService.swift` | 481 | <300 | pending | — |

## Batch 13 — Services (Final)

| # | File | Lines | Target | Status | Issue |
|---|------|-------|--------|--------|-------|
| 36 | `Services/IntegrationsService.swift` | 473 | <300 | pending | — |
| 37 | `Services/WorkflowExecutionObserver.swift` | 406 | <300 | pending | — |
| 38 | `Services/DragDropService.swift` | 401 | <300 | pending | — |

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
