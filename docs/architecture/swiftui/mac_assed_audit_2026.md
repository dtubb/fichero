# Mac-assed / 2026-SwiftUI Conventions Audit

**Date:** 2026-06-08 · **Scope:** whole SwiftUI app, surface-by-surface ·
**Rubric:** A state(`@Observable`) · B native `List`/`Table` · C no local paths · D no
`NotificationCenter`/`DispatchQueue`/`print` · E file size · F Mac-assed gaps (No-Selection,
Liquid Glass, keyboard) · G reactivity/observers. Conventions: `SWIFTUI_PRINCIPLES.md` (2026).

## Headline

The app is **already substantially modern** — most surfaces use native `List`/`Table`,
`ContentUnavailableView`, OSLog, `@State`, and load via services (no local paths). Workflow,
Automation, Research, Sidebar nav, and Settings/Providers are close to exemplary. The real work
is a finite set of **systemic** gaps, below, plus per-surface polish.

## Systemic findings (do these first)

| # | Theme | Severity | Where |
|---|---|---|---|
| S1 | **Local file paths** (breaks remote engine + bypasses typed client/auth) | **HIGH** | `LocalModelsSettingsView` (4 hardcoded `127.0.0.1:8765` URLSession calls — fix exists unmerged in a worktree); `LibraryView+FilterAndBatch` "Reveal in Finder" `URL(fileURLWithPath:)` |
| S2 | **`NotificationCenter` mutation bus** | **HIGH** | KG: `.ficheroClaim*` posted/observed across 6 files (`ClaimSummaryCard+Details`, `ClaimReviewQueueSheet`, `ContradictionTriageSheet`, `ClaimSummaryCardView`, `EntityDetailView`) — replace with an `@Observable` store |
| S3 | **View-local `ObservableObject` → `@Observable`** | MED | Sidebar `RenameStateManager`/`DeleteStateManager`; KG `OntologyBrowserLoadState`; `AgentSettings`; `ImageEditorModel` (#1858); `ResearchService` (shared-ish) |
| S4 | **Custom list → native `List`/`Table`** | MED | `AIModelCatalog`, `AIModelSelectionView`, `ActivityConsoleView`, `FilesNodeConfig` (→`OutlineGroup`), `WorkflowOutputLog` (→`Grid`/`Table`), `ModelComparison` sidebar, `AgentConfiguration` tool list, Search icon/map modes, Research Notes tab |
| S5 | **Missing "No Selection"/empty states** (ties #1854) | MED | MCPServers detail, Agents detail, KG viz panes (Timeline/Map/Digest), Activity detail |
| S6 | **Observer refresh missing** (ties #1851) | MED | Providers/local-models, Research Tasks/Notes, Search rows — hold fetched copies, no mutation refresh |
| S7 | **Liquid Glass not adopted anywhere** (ties #1852) | LOW(app-wide) | all chrome uses `windowBackgroundColor`/`controlBackgroundColor` |
| S8 | **Oversized files** (split) | NOTE | `SidebarView+ViewComponents` (831), `LibraryView+FilterAndBatch` (705), `WorkflowListView` (551), `ClaimSummaryCard+Details` (413) |
| S9 | **Silent truncation** (`.prefix(5/20)`) — violates show-all/Finder-like | LOW | Activity overview/cards |

## Per-surface verdicts

- **Settings / Providers / Models:** modern (native `List`, `Form`, OSLog, empty states). Only
  real issue = S1 `LocalModelsSettingsView`; plus AIModel catalog/selection custom lists (S4).
- **Activity / Automation / Batch:** Automation **exemplary**. Activity modern in state; list/affordance
  gaps (S4 console, segmented strip, S5 empty state, S9 caps). Batch (lives in `LibraryView+FilterAndBatch`) has the S1 local path + S8 size.
- **Research:** clean + modern (native `List`, `ContentUnavailableView`, confirmations). Minor: Notes tab S4/S5, pane widths not `@SceneStorage`, Tasks/Notes S6.
- **Workflow editor:** **reference-grade** (native `List`/`Table`, `@Observable` `WorkflowExecutionObserver`, observer-driven refresh). Gaps: `FilesNodeConfig` tree (S4), `WorkflowOutputLog` matrix (S4), `WorkflowListView` size (S8), no Liquid Glass.
- **Chat / Search:** modern state; primary modes native. Gaps: Search icon/map modes lack keyboard nav (S4, ties #1843); Chat icon/table/map transcript modes are an oddity; Chat awaits full RAG response (no token streaming) — coordinate with #1846.
- **Sidebar:** strong (native `List(selection:)` + `DisclosureGroup` + symmetric drag + a11y). Gaps: two `ObservableObject` state managers (S3), one `print()` (D), file splits (S8).
- **KG / ModelComparison / MCP / Agents / Integrations:** mostly modern. Biggest debt is here: S2 NotificationCenter bus, S3 `OntologyBrowserLoadState`/`AgentSettings`, S4 lists, S5 empty states.

## Backend reactivity (the consistency question)

Today the frontend observer pattern is **optimistic local refresh**: a view mutates via HTTP,
then reloads / updates its own `@Published`. The backend only emits a **consistent push stream for
workflow runs** (SSE → `WorkflowStreamService` → the `@Observable` `WorkflowExecutionObserver`).
There is **no uniform change-event stream** for entities/claims/documents/etc., so a mutation from
another window / a background workflow / the chat agent won't push to other views.

**Target:** a single backend **change-event stream** (SSE/WebSocket) keyed off the
one-audited-action-layer (#1848) / provenance (#1832) — every action emits `{type, ids, run_id,
actor}`; the frontend has one observer that fans those to the right `@Observable` stores. That
makes observers-everywhere (#1851) *real* (multi-source), and reuses the audit log as the event
source. Until then, observers only catch this-view's-own mutations.

## Already tracked (don't duplicate)
#1838 Mac-assed EPIC · #1840-1843 selection/menu/drag/keyboard · #1845-1847 chat · #1850 citations
tab · #1851 observers-everywhere · #1852 2026 stack + Liquid Glass · #1854 No-Selection chrome ·
#1855 no-sel collapse · #1856 horizontal layout · #1857 WebKit reactive · #1858 ImageEditorModel.
