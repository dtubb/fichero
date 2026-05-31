# Reality Check: Activity & Automation Milestone — 2026-05-31

Read-only audit. No code was run or modified.

---

## Open Issues Audited

| # | Title | Verdict | Evidence | Action |
|---|-------|---------|----------|--------|
| 1264 | Standalone live Activity window (Apple Mail Connection-Doctor style) | **OPEN** | No `openWindow` / `WindowGroup` for a floating activity window found anywhere. `ActivityDetailView` only renders inside the main 3-column layout. `ActivityBrowserView` is embedded in `ContentView+Navigation.swift` — not a standalone NSWindow. | Build the new windowing layer. |
| 1226 | Stop, pause, delete controls for active workflow runs in Activity | **PARTIAL** | `WorkflowStreamService.stopWorkflow(threadId:)` and `WorkflowExecutionObserver.cancelExecution(workflowId:)` exist. But no Stop/Pause/Delete buttons appear in `ActivityDetailView` (stats bar and section bar have no such controls). The sidebar context menu has pause/cancel only for `.batch` type items, not `.activityRun`. Backend routes exist (`/api/workflows/{id}/cancel` likely via activity.py) but the Activity UI surface is unconnected. | Wire `stopWorkflow` call into `ActivityDetailView`'s stats bar and/or a toolbar button. |
| 1225 | Consolidate Activity Viewer tabs into single view with step completion grid | **DONE** | `ActivityDetailView` uses a custom horizontal `sectionBar` (scrollable `HStack` of buttons for Overview / Console / Progress / Log) — no `TabView` found anywhere in the Activity directory. `ActivityOverviewView+Cards.swift` contains `docStepGrid()` for the step completion grid. The multi-tab architecture described in the issue is no longer present. | Safe to close. |
| 1224 | Activity viewer should use user-facing names instead of internal artifact names | **PARTIAL** | `activityRunDisplayName(for:)` and `activityExtractWorkflowName(from:)` exist in `ActivityDataProcessing.swift` and are used when building `SidebarItem` names. However, `ActivityLogView` renders raw backend log strings without any name-mapping layer — internal artifact IDs in log output are not translated to user-facing names. The "2 more" grouped-collapse issue has no implementation of an expanded summary view visible in the codebase. | Name-mapping is partial; collapsed-group display improvement still needed. |
| 494 | [Release Gate] 0.1.6 — Wire: Automation (Triggers + Schedules) | **OPEN** | This is a future release gate (0.1.6). Automation infrastructure (schedules, triggers, routes) is built, but the test checklist is the gate criteria for 0.1.6, which has not been validated. | Roadmap item, not closeable until 0.1.6 QA. |
| 493 | [Release Gate] 0.1.5 — Wire: Activity Monitor | **OPEN** | Future release gate (0.1.5). Activity infrastructure exists but several P1 issues (#1226, #1264) block it. | Roadmap item, not closeable until 0.1.5 QA. |
| 280 | Re-enable Integrations menu after 0.0.2 hardening | **PARTIAL** | `isIntegrationsEnabled` flag exists in `FeatureManager.swift` (line 119) and `FicheroApp.swift` guards the Integrations menu behind it (line 243). `IntegrationsView.swift` is fully built. The flag defaults to `false` (only enabled via `allFeaturesEnabled`). Acceptance criteria: "hidden by default through 0.0.2" — this is satisfied. But "re-enable once promoted" requires a milestone decision, not just code. | Partially done as a gate; close or defer to the integration promotion milestone. |
| 255 | Promote minimal Automation slice from off to beta | **OPEN** | `automationEnabledInternal` defaults `false`; `isAutomationEnabled` is `allFeaturesEnabled || automationEnabledInternal`. No default promotion has been made — automation is off unless `allFeaturesEnabled`. The sidebar, schedules, and triggers are all wired but gated. | Requires a deliberate `@AppStorage` default flip or a settings toggle for beta users. |
| 253 | Promote Activity from off to beta | **OPEN** | Same pattern: `activityEnabledInternal` defaults `false`. Activity mode icon and view are fully wired behind the flag but not promoted. | Same as #255 — requires a flag default change. |

---

## Summary

| Category | Count |
|----------|-------|
| Total open issues audited | 9 |
| DONE (safe to close now) | 1 |
| PARTIAL | 3 |
| OPEN (genuinely needs work) | 5 |

---

## Safe to Close Now

- **#1225** — Tabs consolidation is done. `ActivityDetailView` uses a section bar, not `TabView`. Step completion grid exists in `ActivityOverviewView+Cards.swift`.

---

## Partially Done — Needs Scoped Follow-up

- **#1224** — Workflow-name mapping is in place for sidebar rows; raw log strings in `ActivityLogView` still show internal IDs. Grouped "2 more" collapse summaries not addressed.
- **#1226** — `stopWorkflow` / `cancelExecution` exist in services but are not surfaced in the Activity detail UI. Only batch items in the sidebar context menu have stop/cancel wiring.
- **#280** — Gate is correctly in place. Whether to "promote" is a product decision; the code is ready.

---

## Needs Real Work

- **#1264** — Standalone floating Activity window does not exist yet.
- **#255, #253** — Feature flags need a default flip to expose automation/activity to beta users. Trivial code change; product decision needed.
- **#494, #493** — Release gates; depend on QA passing all checklist items.

---

*Verified via jCodemunch AST index + direct file reads. No execution.*
