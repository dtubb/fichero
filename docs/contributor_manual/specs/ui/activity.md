# Activity — Design Spec (#TBD)

> Milestone: activity
> Manual: TBD — the user manual needs a section on the Activity view: seeing what's running
> now and what ran before, per library, with an honest status (never a spinner for a run that
> already finished, failed, or died with its process).

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** Legacy milestone "Activity View"
> (#122) accumulated 9 open issues with no spec anchoring any of them. This is Pass 1: the
> spec these issues never got, written against the code as it stands today.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the intent (needs an issue).
>
> **Path and folder**: `ui/activity.md`, alongside `research.md`/`search.md` — a Library-
> adjacent surface, not a separate top-level concern.
>
> **Territory this spec does NOT own — read first, cited not restated:**
> - `harness/observable-data-layer.md` — the general "a view never assembles its own data, a
>   store does, and patches in place" rule. This spec cites that rule's OWN behaviors where
>   `ActivityStore` already follows it, rather than restating the architecture mandate.
> - `ui/workflows.md` — workflow EXECUTION correctness (cancellation, pause/resume boundaries,
>   the run's own lifecycle). This spec owns the VIEW that shows a run's state, not the
>   backend mechanics that produce that state. `workflows.run.controls-are-fire-and-forget`
>   is extended there with this fold's → #4402 evidence, not duplicated here.
> - The ratified Comparison design (`modes-to-panes.md`/→ #4705's territory): "Comparison is now
>   panes + a diff lens... never a chat tab, node, or window" — → #2277's own comparison-jump
>   half points at a design that has since moved; cross-referenced, not restated.

## Intent (the design)

Activity is the one place a researcher goes to answer "is that still running, and did the
last one work?" A run's shown status is always true: a spinner means the process is actually
alive and working, right now; a completed/failed/cancelled state is shown the moment the run
reaches it, never lingering as "running" after a restart, a crash, or a stop the user asked
for. A failure to LOAD a library's own history is shown honestly (a warning row naming which
library), never silently dropped so the run simply looks like it never happened. The view
itself never assembles or dedupes runs — it observes a store that does, and updates only the
rows a change actually touches, never a wholesale reload for a one-row event.

## Grounding: what exists today (verified against HEAD, 2026-09-19)

**`ActivityStore` already owns the run-list assembly and surfaces load failures** —
contrary to what one of this milestone's own issues describes at a now-stale line reference.
`ActivityStore.rebuildRuns(activeExecutions:library:)` (`fichero/fichero/Models/
ActivityStore.swift`) merges live executions with per-library historical queries, sorts, and
publishes `runs: [ActivityRun]`; failures from a library's own historical query are collected
into `runLoadFailures: [String]` — the store's own comment states the intent directly: "are
collected into `runLoadFailures` rather than silently dropped." `ActivityViewHelpers.swift`
renders `runLoadFailures` as a `ForEach` warning row. `ActivityBrowserView` (`Activity
ViewHelpers.swift:153`) no longer contains the `loadHistoricalRuns`/`loadRuns` methods a
now-stale issue names — the code has moved since it was filed.

**Change events apply selectively, not as a wholesale reload** — `ActivityStore.
applyActivityEvent` explicitly separates an in-place indicator update (backend-work signals)
from a domain-store-routed mutation, with an inline comment stating the discipline directly:
"must NOT bump `refreshToken` — that would reload the whole run list on every mutation
(no-wholesale re-render)."

**Cancellation now has a general per-item boundary, not only the parallel fan-out branch** —
contrary to one issue's own "exactly one place" finding: `builder.py` now has TWO cancellation
check sites. The newer one is a shared per-item progress-reporting callback reached by every
per-item tool loop (not the fan-out-specific branch the issue named), with a code comment
citing the issue by number and explaining why: "checking here reaches all of them without
editing thirty loops, and cannot drift out of sync with them the way thirty separate checks
would." Pause shares the identical boundary, checked after cancel on purpose ("a run that was
both paused and stopped is stopped"). **Not confirmed**: whether a single long call inside one
node with no per-item loop, or a boundary purely on the serial (non-looping) path, is now
covered — the fix targets per-item loops specifically, and the issue's own broader ask
("between nodes on the serial path... during a long call, by cancelling the request rather
than waiting for it") was not independently re-verified beyond the per-item case.

**No standalone Activity window exists** — no `Window`/`WindowGroup` scene named "activity"
was found anywhere under `fichero/fichero/`; the `.activity` sidebar mode remains the only
surface. Two issues in this milestone ask for the same standalone, Mail-Connection-Doctor-
style window; neither is built.

## Behaviors

### A. The run list — assembly, honesty, and live updates

- `activity.store-owns-run-assembly` — **[PARTIAL]** (#3231, #493) `ActivityStore.rebuildRuns` merges live
  and historical runs, sorts, and dedupes — the view only renders `runs`/`runLoadFailures`,
  never assembles them itself. Verified at HEAD by direct code read; no dedicated pinning test
  name found this pass for `rebuildRuns` specifically — PARTIAL rather than OK for that reason
  alone, not because the mechanism is unproven.
- `activity.load-failures-are-honest` — **[PARTIAL]** (#3231) a per-library historical-query failure
  is collected into `runLoadFailures` and rendered as a warning row, never silently dropped —
  the exact "no-silent-fallback" honesty rule a legacy issue on this milestone asked for.
  Verified at HEAD: `ActivityStore.swift`'s own comment states the intent;
  `ActivityViewHelpers.swift` renders the `ForEach`. No dedicated pinning test found this pass
  — PARTIAL for that reason.
- `activity.change-events-patch-not-reload` — **[OK]** an activity change event updates the
  affected indicator/row in place; only a genuine domain mutation routes to the domain stores,
  and neither path bumps `refreshToken` for a one-row event. Verified at HEAD:
  `applyActivityEvent`'s own inline comments state this discipline directly (no-wholesale
  re-render). Pinned: `ActivityStoreTests.swift`'s "folded change frame does NOT bump
  refreshToken (no wholesale run reload)".
- `activity.spinner-reflects-process-liveness` — **[BROKEN]** (#4346) seen live in maintainer/
  field testing: after a workflow run stops, its activity row keeps showing an active spinner
  — reproduced on the current integration tree, after the terminal-path finalization and
  per-row busy-state fixes the issue itself names as already landed. Not diagnosed further
  this pass; the issue's own triage notes (observer/store merge, SSE stream ending without a
  terminal frame) are the live leads, not re-verified here.
- `activity.stale-runs-settle-across-restarts` — **[BROKEN]** (#4384) runs from days ago show
  a "running" indicator across app and engine restarts — a process cannot genuinely run that
  long, so these are dead runs never settled. The issue's own two open questions (does the
  stale-run sweep run on every startup or only when a prior run is detected; does it settle
  runs whose pid is not merely gone but unrecognisable after a reboot, where pid reuse makes
  "is this pid alive" the wrong question and the run's start time relative to the current boot
  is the honest signal instead) were not independently re-verified this pass — recorded as the
  issue's own diagnosis, not confirmed against current code.

### B. Cross-cutting correctness — cited from its owning spec, not restated

- `activity.cancellation-boundary-generalized` — **[PARTIAL]** (→ #4402) the Stop control's
  underlying cancellation check is no longer scoped to the parallel fan-out branch alone — a
  shared per-item boundary now covers every per-item tool loop, with pause sharing the same
  checkpoint. Whether a single long call with no per-item loop, or a purely serial (non-
  looping) node boundary, is also covered was not independently re-verified. This is
  `ui/workflows.md`'s own `workflows.run.controls-are-fire-and-forget` behavior, extended with
  this fold's evidence there — not duplicated as a second claim here; cited so this milestone's
  own issue isn't lost from view.

### C. Standalone window and view reorganization (not built)

- `activity.standalone-window` — **[GAP]** (#1264, #1559 — the same ask, filed twice roughly a
  week apart) a standalone, Mail-Connection-Doctor-style Activity window (live job list, a
  status dot/spinner per row, fan-out sub-items as disclosure rows, opened via the Window menu
  + a toolbar button + a keyboard shortcut, independent of the library window's focus) does not
  exist — only the `.activity` sidebar mode does. Both issues describe the identical feature;
  folded as one behavior rather than two. **Open questions the issues themselves raise, not
  decided here**: minimal "Checking…" bar vs. full table by default (auto-collapse when only
  one job is active?); keep a finished row briefly before fading, or clear immediately; does
  clicking a row jump to the full Activity mode or open the document directly.
- `activity.delete-by-workflow-run` — **[GAP]** (#1830) no capability exists to delete a
  specific workflow run's output (or all runs of a workflow type) while leaving source
  documents and other runs' derived data untouched — today the only path is deleting the
  whole library and redoing the work. Needs a CLI + endpoint + a UI affordance in the
  Activity/run view, gated on provenance stamps already existing on derived data.
- `activity.columns-move-into-activity-view` — **[GAP]** (#2277, half of this issue's own ask)
  workflow activity columns (progress, status detail) live in the workflow node editor today;
  the issue asks for them to move into the Activity view itself, where a researcher already
  looks for run state. Not built.
- `activity.step-click-jumps-to-comparison` — **[GAP, design has moved on]** (#2277, the
  other half) this issue's own ask — clicking a workflow step jumps to "the comparison of that
  step" — was written against a 2026-06 reform master-plan design (a chat-tab/node Comparison
  surface) the maintainer has since superseded: Comparison is now panes plus a diff
  lens, a "run with A and B" action that leaves two sibling artifacts in two Reader panes,
  never a chat tab, node, or window (`modes-to-panes.md`/→ #4705's own territory). Whether a
  step-click should drive that newer panes-based Comparison is a live, undecided question —
  not the same claim as this issue's original ask, and not decided here.

## Redirect, not folded here

- **#3231** ("ActivityBrowserView swallows per-library history failures... store-boundary
  violation") — **verify-close, not a live gap.** The store-boundary violation this issue
  named (the VIEW assembling its own run list, at `ActivityBrowserView.loadHistoricalRuns`)
  no longer exists at that location; `ActivityStore.rebuildRuns` now owns exactly this
  assembly, and `runLoadFailures` surfaces load errors honestly. See
  `activity.store-owns-run-assembly` and `activity.load-failures-are-honest` above. Evidence
  posted, left open, not closed here.
- **#493** ("Wire: Activity Monitor") — **verify-close, not a live gap.** Every item on this
  issue's own test checklist has a real file behind it: live progress (`ActivityStore`/
  `ActivityProgressView+LiveProgress.swift`), a log stream (`ActivityLogView.swift`), code
  output (`ActivityConsoleView.swift`), an execution diagram home
  (`ActivityMonitorModel.swift`), a trace view (`RunTraceView.swift`), and run history
  (`ActivityStore.runs`, historical merge). Whether every checklist item passes exactly as
  worded (e.g. "execution diagram renders the workflow graph") was not individually re-run
  this pass — recorded as strong structural evidence, not a full re-test.
- **→ #4402** — see `activity.cancellation-boundary-generalized` above; this is really
  `ui/workflows.md`'s own subject, cross-referenced here so the milestone fold doesn't lose
  it, not folded as this spec's own claim.

## Fold plan for the 9 issues — Pass 2 EXECUTED 2026-09-19

**Moved onto #320 (activity), each now backing a named behavior above:**
- #1264, #1559 → `activity.standalone-window` (one behavior, two issues — the same ask; both
  left OPEN, note posted on each pointing at the other, closing neither)
- #1830 → `activity.delete-by-workflow-run`
- #2277 → `activity.columns-move-into-activity-view` + `activity.step-click-jumps-to-comparison`
- #4346 → `activity.spinner-reflects-process-liveness`
- #4384 → `activity.stale-runs-settle-across-restarts`

**Verify-close, evidence posted, none closed:**
- #493 → `activity.store-owns-run-assembly`/general Activity-monitor build evidence
- #3231 → `activity.store-owns-run-assembly`, `activity.load-failures-are-honest`

**Redirect, cross-referenced not moved onto this milestone** (ruling: an issue lives on the
milestone of the spec that OWNS its behaviour):
- #4402 → moved onto milestone `workflows` (#293) instead, cited from `ui/workflows.md`'s own
  `workflows.run.controls-are-fire-and-forget`; `activity.cancellation-boundary-generalized`
  above keeps only the arrow-prefixed cross-reference, not ownership.

**Net effect: #122 ("Activity View") reached 0 open issues and was closed** — #4402 was the
one issue this milestone would otherwise have kept, and it now lives on `workflows` (#293)
instead, per the ownership ruling above.
