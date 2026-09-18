# Automation Surface — Design Spec

> Milestone: automation
> Manual: TBD — a "Schedules & Triggers" note explaining that a schedule runs a workflow on
> a timer and a trigger runs it when a watched folder changes, that both live in the
> sidebar next to workflows, and that a schedule/trigger can be paused, resumed, or run
> immediately without waiting for its timer/watch to fire.

> Design-led (Testing Constitution). The Fichero creative director owns intent; tests
> enforce it; code makes them pass. **Status: DRAFT.** Grounded in a read-only code map —
> every claim below is `file:line` against this worktree, 2026-09-18. This is an
> AREA spec for *policy and placement* (what the automation surface is, what it is built
> on, what it is missing); the pane-by-pane RENDITION of a schedule/trigger node (which
> pane shows what) is owned by `modes-to-panes.md` and only cross-referenced here.
>
> Tags: **[OK]** true today · **[BROKEN]** regression, code contradicts a ruling ·
> **[GAP]** intended, never built · **[PROPOSED]** decided here, not yet built.

## Intent (the design)

Schedules and triggers are **sidebar nodes**, exactly like workflows — not a separate
"mode" the app switches into (creative-director ruling, 2026-09-18, `modes-to-panes.md`).
A schedule runs a workflow on a timer; a trigger runs a workflow when a watched folder
changes. Selecting one in the sidebar shows its detail/edit surface beside the Library
(never instead of it — the Library pane is always the navigator and panes never collapse
by selection, `panes-workspaces.md`); its run history belongs in the Reader rendition and
its configuration in the Inspector, per `modes-to-panes.md`'s per-surface-owns-its-
rendition rule — that placement is **not yet built** (see Behaviors, `automation.run-
history.rendition`). An unattended run started by a schedule or trigger is still
background work: it must never peg the user's machine, so it inherits the same
auto-throttle/low-priority discipline as embedding and other background compute. Every
capability here — create, pause, resume, run-now, delete a schedule or trigger — is one
typed, audited backend action; a run is an actor in the audit log like any other agent
action. The surface stays dead-simple: no separate on/off toggle beyond the single
dev-tier feature flag that gates whether Automation is visible at all.

## What exists today (grounded, 2026-09-18)

Automation is **not greenfield** — both engines are fully implemented backend-side, with a
matching Swift service and detail/editor UI. What's missing is wiring into the audited
action layer, unattended-run throttling, and the pane-rendition split `modes-to-panes.md`
calls for; the sidebar-node UX is real but sits behind a dev-only flag and one Library-
takeover regression shared with every other sidebar mode.

| Layer | Schedules | Triggers (file-watch) |
|---|---|---|
| **Engine** | `fichero-server/src/fichero_server/workflows/scheduler.py` — `WorkflowScheduler` (`:113`), APScheduler-backed, SQLite-persisted (`_init_database` `:170`). CRUD (`create_schedule` `:297`, `update_schedule` `:707`, `delete_schedule` `:761`), `pause_schedule`/`resume_schedule` (`:661`/`:681`), manual `trigger_now` (`:831`), run history `get_schedule_runs` (`:792`). **BUILT.** | `fichero-server/src/fichero_server/workflows/file_watcher.py` — `FileWatcherManager` (`:212`) on `watchdog`'s `FileSystemEventHandler` (`FileWatchHandler` `:119`), `TriggerConfig`/`FileTrigger`/`TriggerExecution` (`:67`/`:84`/`:106`), same CRUD + pause/resume + execution-history shape. **BUILT.** |
| **REST API** | `fichero-server/src/fichero_server/api/routes/workflow/schedules.py` — full CRUD + `/pause` `/resume` `/trigger` `/runs` (`:195`–`:406`), mounted at `/api/schedules` (`api/main.py:1805,1969`). **BUILT.** | `fichero-server/src/fichero_server/api/routes/workflow/triggers.py` — same shape at `/api/triggers` (`:208`–`:403`; `api/main.py:1807,1970`). **BUILT.** |
| **Swift service** | `fichero/fichero/Services/AutomationAPIService.swift` (`:13`, `@MainActor @Observable`) + `AutomationServiceTypes.swift` DTOs — wraps both routers through the generated client, held per-library (`LibraryManager.swift:402`, `LibraryReference.automationService` `:110`). **BUILT.** | Same service, same file. **BUILT.** |
| **Detail/editor UI** | `Views/Library/Automation/ScheduleDetailView.swift`, `ScheduleEditorView.swift` (+`+Category`), `ScheduleCreationSheet.swift`. **BUILT.** | `TriggerDetailView.swift` (+`+ExecutionHistory`, `+Configuration`, `+Helpers`), `TriggerEditorView.swift` (+`TriggerEditorFormPanel`/`PreviewPanel`), `TriggerCreationSheet.swift`. **BUILT.** |
| **Sidebar node + creation** | `SidebarItem.ItemType.schedule` (`SidebarItem.swift:104`), `.fromSchedule` factory (`SidebarItem+MoreFactories.swift:52`), listed via `SidebarView+UnifiedLibrarySections.swift:156-172,244-245` — **only when `FeatureManager.shared.isAutomationEnabled`**. "New Schedule" in `AddItemMenu.swift:92`. **HALF-BUILT** (gated, off by default). | `.trigger` (`SidebarItem.swift:105`), `.fromTrigger` (`:69`), same gate, `AddItemMenu.swift:96`. **HALF-BUILT.** |
| **Feature flag** | `FeatureTiers.generated.swift:427-433` — `.automation`, `tier: .dev`, flag `fichero.features.automation`, default OFF (`FeatureManager.swift:100,350`). Promote-to-beta tracked by issue #255 (OPEN). **HALF-BUILT** (works, gated). |
| **Pane placement** | `AppViewMode.automation/.schedule(nil)/.trigger(nil)` (`SidebarViewTypes.swift:14-16`). `PaneContentPlan.swift:131-137` plans `.automation` as `library: .content` (Library stays the navigator) but `preview`/`reader`/`inspector` all `.empty(...)`. **The live router disagrees:** `ContentView+Navigation.swift:332-337`'s OLD mode switch (the same one `modes-to-panes.md` names as the one Library-takeover defect, epic #4705) renders a `ContentUnavailableView("Automation", …, "Select a schedule or trigger in the sidebar")` **into the Library pane itself** when nothing is selected — the dead end this spec's Behaviors section calls **[BROKEN]**. Once a schedule/trigger IS selected, `.schedule`/`.trigger` cases route to the real detail/editor views correctly. **HALF-BUILT.** |
| **Audit / action layer** | Zero references to `schedules`/`triggers` in `actions/registry.py` or `actions/audit_chain.py` (the one-audited-action-layer, #18xx program) — confirmed by search. A schedule/trigger CRUD or run is **not** a typed audited action; it goes straight from FastAPI route to the scheduler/file-watcher. **STUB** against that ruling. |
| **Unattended-run throttling** | `core/background_compute.py` is the app's real throttle primitive (drops a thread to background QoS / `nice`, `:69`); neither `scheduler.py`'s `_execute_schedule`/`_run_single`/`_run_batch` (`:406-527`) nor `file_watcher.py`'s execution path calls it — a scheduled 3am run competes for CPU exactly like an interactive one. **STUB** against the "user machine always useful" rule. |
| **Timezone correctness** | Fixed: naive/UTC datetime bug (#2134, CLOSED) pinned by `fichero-server/tests/unit/workflows/test_scheduler_tz.py`. **OK.** |
| **Tests** | Backend: `tests/unit/api/test_routes_schedules.py`, `test_routes_triggers.py` (CRUD, pause/resume, run/execute, OpenAPI schema). Swift: `SchedulesMigrationTests.swift`, `TriggersMigrationTests.swift`, `AutomationServiceTypesTests.swift`, `ScheduleFormattingTests.swift` (cron→plain-language, duration formatting). **OK**, real coverage on both sides — see Test matrix. |

## Behaviors

- `automation.schedule.crud` [OK] — create/read/update/delete a schedule end-to-end
  (`scheduler.py:297,707,761` → `schedules.py` routes → `AutomationAPIService`). Pinned:
  `test_routes_schedules.py` (`TestCreateSchedule`, `TestGetSchedule`, `TestDeleteSchedule`,
  `TestListSchedules`).
- `automation.trigger.crud` [OK] — same for file-watch triggers (`file_watcher.py` → `triggers.py`).
  Pinned: `test_routes_triggers.py` (`TestCreateTrigger`, `TestGetTrigger`, `TestDeleteTrigger`,
  `TestListTriggers`).
- `automation.schedule.pause-resume` [OK] — `scheduler.py:661,681`, exposed as
  `/pause`/`/resume` (`schedules.py`); same for triggers. Pinned: `test_routes_schedules.py`
  (`TestPauseResumeSchedule`), `test_routes_triggers.py` (`TestPauseResumeTrigger`).
- `automation.run-now` [OK] — a schedule or trigger can be run immediately without waiting
  for its timer/watch (`WorkflowScheduler.trigger_now` `:831`, `POST /schedules/{id}/trigger`).
  Pinned: `test_routes_schedules.py` (`TestTriggerSchedule`).
- `automation.run-history.backend` [OK] — `get_schedule_runs` (`:792`) / trigger
  `/executions` return a persisted run history. Pinned: `test_routes_schedules.py`
  (`TestScheduleRuns`), `test_routes_triggers.py` (`TestTriggerExecutions`).
- `automation.creation-affordance` [PARTIAL] (implemented, unpinned; #4799) — "New
  Schedule"/"New Trigger" reachable from `AddItemMenu.swift:92,96`.
- `automation.feature-gated` [OK] — dev-tier flag, off by default; promoting it to beta is
  separately tracked future work, not a defect in this behavior. Pinned:
  `FeatureManagerTests`.
- `automation.sidebar-node.dead-end` [BROKEN] — with the flag on and zero schedules/
  triggers created, selecting Automation from the View menu replaces the Library pane's
  content with a "Select a schedule or trigger in the sidebar" placeholder instead of
  leaving the Library visible with nothing new to select — the Library-takeover defect
  epic → #4705 tracks generally (increment 4 names retiring this exact mode). Owned by
  `modes-to-panes.md`; automation is one instance of it, not a separate bug.
- `automation.run-history.rendition` [OK] (ba7871c09, #4741 closed) — a schedule's or trigger's run
  history renders in the Reader pane as `modes-to-panes.md` calls for, through shared read-only
  views (`ScheduleRunHistoryView`, `TriggerRunHistoryView`) that the Preview detail view mounts
  too — one renderer, two mounts. Pinned: `PaneContentPlanTests.automationKindsLandOnTheRunHistoryReaderSurface`,
  `PaneContentPlanTests.readerSubjectFromNamesTheRightEntity`. No render test yet (the same
  honest coverage gap as the workflow run log). Whether Preview keeps its copy is an open
  question for the creative director, recorded in `modes-to-panes.md`.
- `automation.audit-trail` [GAP] — a schedule/trigger create/edit/pause/run is not routed
  through `actions/registry.py`'s typed audited-action layer, so an automation run is not
  an actor in the audit log. **(#4739).**
- `automation.unattended-throttle` [GAP] — a schedule/trigger-initiated workflow run does
  not drop to background QoS via `background_compute.py`; it can compete for CPU with the
  foreground app the same as an interactive run, which the "user machine always useful"
  rule requires it not to. **(#4740)** — corrected 2026-09-18: was mis-cited to #4739,
  #4740 is this behavior's own issue by title.
- `automation.timezone-correctness` [OK] — #2134 (CLOSED), pinned by `test_scheduler_tz.py`.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | cron→plain-language + duration formatting, off-main | `fichero/Tests/Unit/general/Views/Library/ScheduleFormattingTests.swift` |
| Pure rule (backend) | y | naive/UTC datetime normalization (next-run computation) | `fichero-server/tests/unit/workflows/test_scheduler_tz.py` |
| Availability (Swift) | y | `AutomationAPIService` reachable from a library reference | `LibraryManager.swift:402,110` (needs a pinning test — none found citing this specifically) |
| Backend (pytest) | y | schedule/trigger CRUD, pause/resume, run-now, OpenAPI schema | `fichero-server/tests/unit/api/test_routes_schedules.py`, `test_routes_triggers.py` |
| Backend (pytest) — trigger MATCHING | n today | which file events a `TriggerConfig` matches (glob/extension/event-type) | **[GAP]** — `file_watcher.py`'s `FileWatchHandler` has no dedicated matching-policy test file found |
| Backend (pytest) — throttling policy | n today | a scheduled run drops to background QoS like `background_compute.py`'s other callers | **[GAP]** — no test exists because no call site exists (`automation.unattended-throttle`) |
| Swift contract | y | response decoding, error surfacing (never silent-empty) | `Contract/TriggersMigrationTests.swift`, `Services/SchedulesMigrationTests.swift` |
| MCP | n | not exposed as an MCP tool today | — |
| CLI | n | not exposed as a CLI command today | — |
| Click-around (XCUITest, Mac) | n | create → pause → run-now → see it in run history | **[GAP]** — no automation flow in `fichero/Tests/UI` |
| iPhone / iPad | n | automation is dev-tier only; not scoped for touch yet | — |
| Load (#4634) | n | not exercised at scale | — |

## Open questions for the creative director

1. **What can a trigger watch, beyond a folder?** Today `file_watcher.py` only watches
   filesystem paths (`watchdog`). Should a trigger ever watch an in-app event (new ingest,
   a KG update — memory already floats "watched entities trigger on new ingest", #2360/
   #2361, OPEN) as the same node type, or is that a distinct future kind?
   **Recommendation:** keep triggers filesystem-only for now; treat entity-watch as a
   separate future node type rather than widening `TriggerConfig`.
2. **Does an unattended run ever need confirmation before it acts?** A schedule can run a
   workflow that writes to the library with nobody watching. **Recommendation:** no
   confirmation gate (breaks "unattended"); rely on the audit trail (once wired,
   `automation.audit-trail`) plus a real failure surface (next question) so a bad run is
   visible after the fact, not blocked before it.
3. **Where does a failed unattended run surface to the user?** Today a failed run sits in
   `ScheduleRun`/`TriggerExecution` rows, visible only if the user opens that schedule's
   detail view. **Recommendation:** surface failures in Activity (the existing run-history
   surface for interactive runs, #1474/#1830) rather than inventing a second failure feed
   for automation specifically.
4. **Where does run history live once `modes-to-panes.md` lands — Reader, or Activity, or
   both?** `automation.run-history.rendition` is a GAP either way; this spec can't resolve
   it alone. **Recommendation:** Reader shows the selected schedule/trigger's own run
   list (per `modes-to-panes.md`'s per-node rendition rule); Activity keeps the
   cross-node aggregate view. Not both authoring the same data independently.
5. **Should Automation be promoted from dev to beta now, or after #4705 increment 4
   retires the placeholder?** Promoting while the dead-end regression is live means a beta
   user can hit it. **Recommendation:** hold #255 until #4705's automation increment
   lands, not in parallel.
6. **Does throttling apply uniformly, or should a user-triggered "run now" run at normal
   priority since a human is waiting on it?** **Recommendation:** background QoS for
   schedule/trigger-initiated runs; normal priority for `trigger_now` (a human clicked
   it) — mirrors interactive vs. background elsewhere in the app.
7. **Is a single dev-tier flag enough, or does Automation need its own per-schedule
   enable/disable beyond pause/resume?** **Recommendation:** no — pause/resume already
   covers "off for one item"; a second toggle would violate "no needless toggles."
8. **Should trigger/schedule creation go through the one-audited-action-layer as a
   prerequisite for `automation.audit-trail`, or is a lighter-weight audit log
   acceptable given these are engine-internal, not chat-initiated?** **Recommendation:**
   same layer — "one audited action layer" is a hard rule with no carve-out named for
   background-initiated actions, and an automation run acting on the library is exactly
   the kind of unsupervised write the rule exists for.

## Sources

- Backend: `fichero-server/src/fichero_server/workflows/scheduler.py`,
  `workflows/file_watcher.py`, `api/routes/workflow/schedules.py`,
  `api/routes/workflow/triggers.py`, `api/main.py:1805-1970`,
  `api/feature_tiers_generated.py:184-236`, `actions/registry.py`, `actions/audit_chain.py`,
  `core/background_compute.py`, `tests/unit/api/test_routes_schedules.py`,
  `tests/unit/api/test_routes_triggers.py`, `tests/unit/workflows/test_scheduler_tz.py`.
- Swift: `Services/AutomationAPIService.swift`, `Services/AutomationServiceTypes.swift`,
  `Models/SidebarViewTypes.swift`, `Models/SidebarItem.swift`,
  `Models/SidebarItem+MoreFactories.swift`, `Models/FeatureTiers.generated.swift`,
  `Models/FeatureManager.swift`, `Models/FeatureManager+Accessors.swift`,
  `App/ViewSettings.swift`, `App/Menus/AddItemMenu.swift`, `App/Menus/ViewMenuCommands.swift`,
  `Views/Library/Automation/**`, `Views/Shell/PaneContentPlan.swift`,
  `Views/Shell/ContentView/ContentView+Navigation.swift`,
  `Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift`,
  `Tests/Unit/general/Contract/TriggersMigrationTests.swift`,
  `Tests/Unit/general/Services/SchedulesMigrationTests.swift`,
  `Tests/Unit/general/Views/Library/ScheduleFormattingTests.swift`.
- Issues: #255, #494, #1429, #1474, #1728 (CLOSED), #1742, #1830, #2134 (CLOSED),
  #2360, #2361, #4002 (CLOSED), #4102, #4335, #4705.
- Cross-references: `docs/contributor_manual/specs/ui/modes-to-panes.md` (node rendition,
  Library-always-navigator), `docs/contributor_manual/specs/ui/panes-workspaces.md`
  (panes never collapse by selection).

## Issue map (milestone `automation` #295, redone 2026-09-18 after the truncated-fetch bug was
fixed — first pass under-counted at 4 issues; the real count is 10)

| Issue | Title | Behavior | Note |
|-------|-------|----------|------|
| #4739 | `automation.audit-trail` — a scheduled/triggered run is not an audited actor | `automation.audit-trail` | cited |
| #4740 | `automation.unattended-throttle` — scheduled/triggered runs never call the background throttle | `automation.unattended-throttle` | cited (fixed last pass — was mis-cited to #4739) |
| #4741 | `automation.run-history.rendition` — run history renders in the Reader, not only its detail view | `automation.run-history.rendition` | cited (fixed last pass — was mis-cited to #4739) |
| #4799 | ui/automation.md: 1 behavior implemented but unpinned | `automation.creation-affordance` | cited (this pass's own bucket issue) |
| #255 | Promote minimal Automation slice from off to beta | `automation.feature-gated` (discussed, not machine-cited) | **deliberately not cited** — `automation.feature-gated` is `[OK]`; citing an OPEN #255 there would be a false rule-e finding (the behavior text explicitly says promoting to beta is separately tracked, "not a defect") |
| #494 | Wire: Automation (Triggers + Schedules) | `automation.schedule.crud` / `.trigger.crud` (superseded by, not cited) | **UNCOVERED, recommend closing** — schedule/trigger CRUD is now `[OK]` with real pinning tests (`test_routes_schedules.py`/`test_routes_triggers.py`); citing this OPEN issue on an OK behavior would be a false rule-e finding the same way #255 would be |
| #1742 | [Automation] Wire AutomationService end-to-end before enabling the feature | (superseded by shipped work, see #494) | **UNCOVERED, recommend closing** — same reasoning as #494; the feature is enabled and gated (`automation.feature-gated`), not blocked on end-to-end wiring anymore |
| #1429 | Wire 37 Activity & Automation endpoints into SwiftUI | — | **UNCOVERED** — spans Activity too, broader than this milestone's surface; recommend re-scoping to just its automation-specific endpoints or re-homing |
| #1430 | Wire 19 Tasks & Migrations endpoints into SwiftUI | — | **UNCOVERED, likely misfiled** — Tasks & Migrations is not automation; recommend re-homing |
| #1832 | [EPIC] Workflow-run provenance + reversible output (delete-by-run + undo) | — | **UNCOVERED, likely misfiled** — this is workflow-run provenance, the same theme as `workflows.md`'s #4312 EPIC; recommend moving to milestone `workflows` |

**Coverage: 4 of 10 cited, 2 deliberately-uncited (avoiding false rule-e), 4 UNCOVERED.** No
cluster/sub-spec proposal — the 4 uncovered-and-not-recommended-for-closing issues (#1429,
#1430, #1832, plus #494/#1742 recommended for closing) are heterogeneous wiring/scope issues
that mostly read as either superseded by already-shipped work or misfiled on this milestone,
not a coherent new surface needing its own spec.
