# UI — Activity as a pane — Design Spec (#6441)

> Milestone: activity
> Manual: TBD — the "Activity" section must say that Activity is a pane like Library or Reader: it can sit in any window beside the Inspector, be grouped by run or by file, and that Run Automatically is a setting.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-11-08, Fable). A COMPANION of `activity-and-automatic-work.md` (APPROVED 2026-10-27, 2997 lines: the one job model, the window, lanes, durability, automatic work) and of `panes-workspaces.md` (the pane and workspace system). This file holds only the DELTA the owner asked for on 2026-11-08: Activity becomes a PANE KIND; the generic Activity window is that pane plus the existing Inspector; one hierarchical table with disclosure triangles, grouped by run or by file over the same data; several versions of one step as siblings; history kept and filterable; Run Automatically a setting. Everything the big spec already pins (the job model, the one-bar row, the groups, the details view's content, lanes, retries) stays as written there and is cited, not restated. Menu items and chords go through the one command table of `menus-and-commands.md` (#6435).
> Tags: **[OK]** built · **[PARTIAL]** exists in part · **[GAP]** designed, not built.
>
> **Revised 2026-11-13 night (owner, through the manager; Fable).** This file is now THE Activity spec to build from: the companion
> `activity-and-automatic-work.md` keeps the job model, the lanes, the throttle and the history of what was built; where the two
> disagree, this file wins and the other's bullet is marked superseded (`activity.run.quit-pauses`, `activity.relaunch.only-running-work-resumes`,
> `recipes-run.restart.requeues-unfinished`). `ai/run-failure-alerts.md` keeps the failure table; decisions 8 and 9 there carry
> tonight's rulings. Issues: #6441 (the pane), #6583 (delete), #6584 (nothing restarts), #6354 (failures).
> **Revised again the same night after the manager-commissioned Fable review of fe7332ad2f** (its eight must-change items and
> its answers to the open questions accepted): Archive added, Delete redefined as real removal with Undo, ONE states table, ONE
> column table and ONE verb list, concrete numbers, the less-is-more cuts as the table's acceptance, 2.5 split in two.

## Audit — what the window does today, what the pane needs (verified at origin/integration 09950f6408)

| Today (file) | What it does | What the pane needs instead |
|---|---|---|
| `Window("Activity", id: monitorWindowID)` and `Window("Activity Detail", id: detailWindowID)` in `FicheroApp.swift` (lines 662, 694) | two scenes of their own; the detail window mounts `ActivityDetailsView` alone | ONE generic window = an Activity pane + the Inspector column, built from the pane kind; no detail window |
| `Views/Activity/Window/ActivityMonitorWindow.swift` | a SwiftUI `Table` with disclosure rows over the one job model (`ActivityJobNode`, `GET /api/activity/jobs`, `/jobs/{id}`), columns name, state, progress, started, time, cost, errors, model; its own selection state (`ActivityWindowSelectionState.shared`); the details view embedded at line 63; a toolbar | the same table as a PANE's content, its selection the window's selection, its details in the Inspector; the hierarchy recipe › step › version › item; Group by Run or by File; a filter bar |
| `ActivityGroupsView.swift`, `ActivityWindowGroups.swift` (both deleted, #6441) | NOW, UP NEXT, DONE TODAY (`activity.window.now-upnext-done-today`), the one button per row | kept as the table's section rows; the one button kept; no second list |
| `Views/Activity/Detail/ActivityDetailsView.swift`, `ActivityDetails.swift` (+Recipe, +RunStages, +ToCheck, Log, StageCards, PageGrid) | the ONE details view (#5561, `activity.details.one-view`): heading, state and why, pages, failed pages with Read Again, log, resources, actions; also mounted in the sidebar mode (`ContentView+DetailLayout.swift:285`, `ContentView+Navigation.swift:385`) | the same view, mounted ONCE, as the Inspector's Activity section for the selected row |
| the sidebar `.activity` mode: `SidebarViewTypes.activity(ActivitySelection?)`, `ActivityJobsView.swift` (`ActivityJobRow`), `OpeningSelection` "activity-browser" | a mode whose content is a job list plus the details view | RE-HOMED: the mode's content is the Activity pane (the modes → panes ruling, `modes-to-panes.md`); the list view deleted |
| `Views/Shell/Toolbar/ActivityStatusToolbarItem.swift` (`ActivityModeButton`, `BackendWorkPill`, `ActivityPopoverSummaryView`) | the toolbar status item: the mode button toggles automatic work, the pill, the popover SUMMARY (`activity.popover.summary`) | the popover stays a summary and its Show reveals the pane; the mode toggle leaves the toolbar: Run Automatically is a SETTING, the pane shows its state |
| `Models/ActivityStore+RunTrees.swift` (`loadRunTree`, `setJobPaused`, `cancelJob`, `retryJob`, `useNextCandidate`, `readPagesAgain`), `Services/ActivityJobTypes.swift` (`ActivityJobNode.kind`, `children`, `leaves`, `Failure.retried`) | the one store and the job tree, read per run, patched by the change stream (`activity.window.table`) | the same store serves both groupings; the versions of a step come from the tree and the run record, never a second read |
| engine: `GET /api/activity` (`types`, `levels`, `since`, `until`, `search`), `GET /api/activity/jobs`, `/jobs/{id}` (`depth`), `/jobs/{id}/pages?stage=` (`activity.run.page-states`), the run record (`activity.run.record-keeps-all-history`), `group: "earlier"` (`activity.window.history-group`) | every fact the pane needs exists: per run, per stage, per page, with history | no new route; one provisional query parameter named below |
| `Models/PaneList.swift` (`PaneKind`: library, preview, reading, inspector, chat, segments; `PaneScope`; `PaneConfig`), `Views/Shell/PaneHead/PaneKindSelector.swift` | the pane system: a leaf has a kind and a scope; the kind switcher on every head (`panes.head.kind-switcher-everywhere`) | `PaneKind.activity`, scoped by library (nil = every open library, as the window merges today, `activity.window.all-projects`) |
| `menus-and-commands.md` command table: Window › Activity ⌥⌘0 KEEP; Project › Activity › Stop, Read Again (`menus.project.activity-stop-read-again`, `FocusedActivityRunButtons`) | the commands act on the window's one selected run | the same commands act on the pane's selection wherever the pane is; new verbs join the table, no new chord |

## Decisions (owner, 2026-11-08, from #6441 and its comments)

1. **Activity is a pane kind**, embeddable in the main view like Library, Reader or Segments; the generic Activity window is that pane plus the existing Inspector.
2. **One hierarchical table** with disclosure triangles: recipe › step › versions or attempts › items; the Inspector on the right shows the selected row.
3. **Several versions of one step are siblings** under the step, never a second tree.
4. **Group by Run or Group by File** is ONE switch in the pane header over the SAME data; the pane OPENS grouped BY RUN and By File is one switch away (DECIDED by the owner 2026-11-08 15:45); a row shows what runs now and expands to what has run per file; a file expands to its path through the steps (step, model, version, result, time, cost).
5. **History is kept and filterable** by recipe, step, model, state, date and file.
6. **Run Automatically is a SETTING** in Settings (a plain label and one sentence; global and per project); the pane only shows its state and has Pause/Resume and the per-run actions; the Pause and Run wording must be unambiguous.
7. **No new API where one fits**: the per-page records, the run details and the job tree are the data.
8. **Less text, more indicator** (owner feedback 2026-11-08: too many clocks, too much text, the whole app too discursive): Mac-style spinners and state glyphs, fewer columns by default, errors as a red X with a short line and fix buttons, a text budget per row. The app-wide rule is `menus.less-text-more-indicator` in `menus-and-commands.md`.
9. This companion supersedes, for the pane, the "replaces the list with a back arrow" clause of `activity.window.open-a-run`: opening a row expands and selects it, and its details appear in the Inspector; the content of the opened run (stage bar, page grid, failed pages, what it made, details and log disclosures) is unchanged and lives in the Inspector's section.

### Ruled 2026-11-13 night (owner, through the manager; paraphrased)

10. **One good window.** One Activity window (the pane is its content) with the selected row's detail inside it, in place of
    the detail windows, sheets and popovers that duplicate it; see the inventory under `activity.one-window`.
11. **Full CRUD, Mac-like.** A plain table: standard selection, the Delete key and ⌘⌫, a context menu with the same verbs as
    the toolbar, Undo where it applies; Pause, Stop, Continue, Retry (failed only) and Delete on the row itself, multi-select
    for Delete; automatic runs delete like any other, one at a time or many at once.
12. **The table says what ran on what.** Per row: which file, page or folder; which recipe and which step it is on now; the
    step trail (gone through, running, left); model or provider; state; started and elapsed; result; cost. Icons say at a
    glance where work came from (automatic, a person, a recipe) and what kind of step it is.
13. **Less is more.** Cut every column, badge and panel that does not answer "what is being worked on, how far along, and what
    do I do if it failed". The step trail and cost may live in the Inspector if the table gets busy.
14. **Nothing starts by itself at launch.** After a quit the relaunch never starts runs. Unfinished work (interrupted, quit-paused,
    waiting) is listed in ONE alert at launch with Continue All, Choose… (opens Activity) and Leave Paused (the default). This
    replaces the auto-resume of `activity.run.quit-pauses` and the "Interrupted; carries on" requeue.
15. **A failed run is never re-queued by itself**: not at launch, not by automatic work, not by a recipe re-trigger. Retry is the
    person's.
16. **Never hammer a provider.** One cap per kind of work across every run, recipe, batch and automatic job: cloud calls per
    provider (a few at a time, a setting), local model and Kraken pages by the machine and its memory; everything above the cap
    waits, shown as waiting. A 429 backs off (Retry-After honoured, exponential with jitter, capped); repeated 429s PAUSE the run
    with an alert that names the provider and the fix. Never a tight retry loop, never a silent requeue.
17. **Load a model once.** One loaded instance per model per engine, shared and fed pages from a queue, kept warm while work for
    it waits, released when idle or under memory pressure.
18. **Never repeat work already done.** A run that continues, or a recipe re-run over the same pages, reuses every result for the
    same step, input and model and sends only the missing or failed items to the model.
19. **Errors carry their solution.** No raw code, HTTP status or exception text as the message: one plain sentence of what
    happened plus the fix as a button or an exact instruction, in the table row too; the technical detail behind a disclosure
    or Copy Details. A failure kind with no solution is a spec gap to list, never shown bare.
20. **Cost is shown**: per row and totals per run and per provider, spent so far and the estimate to finish, from the spend
    records (`ai/cloud-permission-and-spend.md`); local work shows no cost and its time instead.
21. **Automatic and Run Now live in ONE place** (decision 6 made exact): the setting. The toolbar mode button, the detail view's
    copy of it and the window's copy go; see the inventory under `activity.automatic.one-place`.

## States and what a person may do in each

One vocabulary for the engine's rows (`jobs.state` plus the reason words it decides), the table's glyph, and the verbs. The
engine owns the transitions; the app shows the state and offers only the verbs the row allows. The set-aside state ("Stopped 3
times by the engine stopping; set aside") is RETIRED: interruptions pause, they never count.

| State | Glyph | Means | Pause | Stop | Continue | Retry | Archive | Delete |
|---|---|---|---|---|---|---|---|---|
| queued | hollow circle | waiting its turn in its lane; nothing holds it | yes | yes | — | — | — | yes |
| waiting for a slot | hollow circle, tooltip says for what | held by a cap (provider, model, memory, battery, thumbnails first) | yes | yes | — | — | — | yes |
| running | spinner | a lane thread works on it now | yes | yes | — | — | — | yes = Stop then Delete, one confirmation |
| pausing | spinner + pause, "Pausing at its next step" | asked to pause; finishes the item it is on | — | yes | yes (cancels the pause) | — | — | yes = Stop then Delete |
| paused | pause | held by a person ("Paused by you"), by the open ("Stopped when Fichero quit"), or for a cause (credit, cap, rate limit: that cause as its line) | — | yes | yes | — | — | yes |
| stopping | spinner + stop | asked to stop; finishes or drops the item it is on; after `STOPPING_TIMEOUT_SECONDS` (30) it reads stopped | — | — | — | — | — | yes (after the timeout) |
| stopped | stop | ended by a person (the engine's `cancelled`); what it did is kept | — | — | — | yes (the items not done) | yes | yes |
| failed | red X + one line + fix | ended on a failure; the reason and its fix shown | — | — | — | yes (the failed items) | yes | yes |
| done | check | finished every item | — | — | — | — | yes | yes |
| partial | check with a dot, "Done, 3 pages failed" | finished with failed items | — | — | — | yes (the failed items) | yes | yes |
| skipped | dash | an item or step the plan left out ("already done", "left out") | — | — | — | — | (with its run) | (with its run) |
| resuming / retrying | spinner, the word in the tooltip | a Continue or Retry taking effect; momentary | — | yes | — | — | — | — |

Transitions the engine makes by itself: queued → waiting for a slot → running (the lane); running → pausing → paused (Pause);
running → stopping → stopped (Stop); running → done, partial or failed (the work); pausing → done or failed (the item it was
on ended it); queued or waiting for a slot → paused or stopped directly (Pause or Stop before it ran); at the open every
unfinished row → paused "Stopped when Fichero quit", a pausing one → paused keeping "Paused by you", a stopping one → stopped.
Transitions only a person makes: paused → queued (Continue; then waiting for a slot or running as the lane has room); stopped,
failed or partial → queued for the items not done (Retry; never the items done); any → archived (Archive, Put Back restores);
any → deleted (Delete, Undo restores). Nothing else moves a row out of paused, failed, stopped or partial: not the open, not
automatic work, not a recipe re-trigger (decisions 14, 15).

**The Mail rule for several rows selected:** a verb is enabled when ANY selected row allows it; it is applied to those rows and
the rest are skipped, and the status bar says how many ("Deleted 4 · 1 running, skipped"). A menu item not applicable to the
selection is disabled, never hidden; the row's own button is absent when its state has no verb.

## The one column table and the one verb list

The table has these columns and no others (owner: less is more; one place defines them, the four earlier bullets defer here):

| Column | Default | Source | Says |
|---|---|---|---|
| Source glyph | on | `started_by` → `ActivityMonitorRow.source` | a person, automatic, a recipe's step, a schedule (word in tooltip) |
| Name | on | `name`, `ran_on` | "Run the recipe: Letters" · "Register 3 · 120 pages"; names are exempt from the word budget (middle ellipsis) |
| State | on | `state` + `reason` | ONE glyph; a failed row: red X + ≤ 8 words + the fix button |
| Trail | on | `stages` | "Import ✓ → Segment ✓ → Read ▶ 34/120 → Names ·" (the one progress; no stage bar, no subtitle) |
| Time | on | `started_at`, `seconds`, `estimate_seconds_left` | time left while running, duration when ended |
| Cost | on | `cost_usd`, the estimate | "$0.42 · ~$1.10 more"; blank for local work; "Not priced" when a call has no price |
| Model | off | `model` | the stage's model or provider (the runtime: Kraken, cloud, local) |
| Started by | off | `started_by` | the word (the glyph column carries it by default) |
| Started | off | `started_at` | the clock time |
| Kind glyph | off | `task_type` → `kindSymbol` | read, segment, names…, with the word in the tooltip |

Verbs, ONE list, the same in the context menu, Project › Activity and the row's one button: **Pause**, **Continue** (never
"Resume Run"), **Stop**, **Retry**, **Archive**, **Put Back** (archived rows), **Delete**, **Show in Activity**, **Copy Link**;
plus the table's: **Group by Run / File**, **Show Archived**, **Archive Finished…**, **Archive Failed**. The row's one button is
the primary fix on a failed row, else the state verb (Pause / Continue / Retry); everything else is in the context menu.
Undo covers Delete and Archive (in session; the engine's two actions are undoable); Pause has no Undo (Continue is its undo).

## Behaviors

- `activity.pane.is-a-pane-kind` — **[OK]** (built #6441: `PaneKind.activity`, the head's kind switcher, the sidebar's Activity mode shows the pane; #6441, decision 1; `panes.head.kind-switcher-everywhere`, `modes-to-panes.md`) `PaneKind` gains `.activity`: any pane can become Activity from its head's kind switcher, an Activity pane can be split, moved, saved in a workspace and restored like the others (`PaneList`, `PaneConfig`), and its `PaneScope.libraryId` says whose work it shows (nil: every open library merged, the project label as a prefix, `activity.window.project-prefix`; a library: that one). The sidebar `.activity` mode is RE-HOMED onto it: choosing Activity in the sidebar shows an Activity pane where the mode's job list stood, `ActivityJobsView` and the "activity-browser" opening selection are deleted, and the mode's selection is the pane's. Acceptance: a Reader pane switched to Activity shows the table scoped to the window's library; the workspace saved and restored has an Activity leaf; the sidebar's Activity shows the same pane. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneKindTests.swift`, the existing `PaneHeadKindSwitcherParityTests.swift`.
- `activity.pane.one-outline-table` — **[PARTIAL]** (built #6441: the flat two-level table, the remembered disclosure, double-click discloses, sortable columns (Name, State, Time, Cost, Model, Started); not built: pages under a multi-page file, which needs the engine's page nodes to name their document; #6441, decision 2; REVISED by the review 2026-11-13 night: flat and two levels) the pane's content is ONE outline table over the one job model, FLAT (no NOW / UP NEXT / DONE TODAY / History / background section rows: sorted by state then start, at most View › Group by State), TWO levels: a run row (or a job of its own) and, under a disclosure, its FILES (a document with its page count, pages under a further disclosure only for a multi-page document; a file row is one distinct `document_id` among the page nodes of the run's tree, in the tree's order, its state the worst of its pages' (failed over running over waiting over done) and its count the pages under it; a run whose tree names no document has no disclosure); steps and versions live in the Inspector (`activity.pane.versions-are-siblings` moves there); the columns and verbs are the one table and list above (no stage bar, no subtitle: the trail is the one progress; `errors` folded into state), sortable, the disclosure state remembered per row and per pane; a single click selects (multi-select as in Finder), a double-click DISCLOSES the row and selects it (one wording; decision 8); the context menu is the one verb list. The table is `ActivityMonitorWindow`'s `Table` moved into the pane kind, reading the same store (`ActivityStore+RunTrees`), not a new view. Acceptance: a recipe run over three documents opens to three file rows, a 120-page register to one file row that opens to its pages; the failed page's reason reads on its row; the disclosure state survives a window close and reopen; no section header row exists. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneOutlineTests.swift`, the existing `ActivityTableTests.swift`.
- `activity.pane.versions-are-siblings` — **[OK]** (built #6441: the versions in the Inspector for a run or file row, the one that counts marked, a one-page retry its own version; #6441, decision 3; `activity.retry.page-within-run`, `activity.retry.one-row`, `activity.run.record-keeps-all-history`) (shown in the Inspector's Activity section for the selected run, not as table rows: `activity.pane.one-outline-table`) when a step ran more than once — a Retry, Read Again, Use Next Candidate (`useNextCandidate`), a re-run with another model or settings — each run of it is a VERSION row, a SIBLING under the step (newest first), with its model (the card id), its version (the card id's `@version`, else the attempt number), its result (pages done, failed, the measured figure when the step has one), its time and its cost; the version whose results COUNT is marked ("counts"); the versions come from the job tree's attempts and the run record (`page_retry` marks a retried page, `run_account` prices each attempt), never from a second tree or a second read. Acceptance: a step read twice with two models shows two sibling rows naming each model, the second marked counts; retrying one failed page adds a version row holding that one page. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneVersionsTests.swift`, the existing `ActivityTableTests.swift`.
- `activity.pane.group-by-run-or-by-file` — **[OK]** (built #6441: the two groupings over the same rows, a selected file kept selected across the switch; #6441, decision 4) ONE switch in the pane header, **Group by: Run | File**, over the SAME data, a new pane opening BY RUN (decision 4, decided) with By File one click away: by Run is the outline above (recipe › step › version › items); by File lists each FILE (page or document) the scope's runs touched, a file row showing what runs on it NOW and expanding to its PATH THROUGH THE STEPS in run order (step › version, each with model, version, result, time, cost, the counting version marked), so a person reads a page's whole history in one place; the switch is per pane, remembered, and the selection survives it (the selected page stays selected in the other grouping); the data is the run trees and per-page states the store already holds (`loadRunTree`, `GET /api/activity/jobs/{id}/pages`) joined by document id in the app; for history older than the loaded trees the pane reads the runs that touched a file through `GET /api/activity/jobs` with a `document_id` filter — the ONE provisional contract point of this spec, one query parameter on an existing route, added only if the app-side join is too slow on a 100k-page library. Acceptance: Group by File on a project with two runs shows a page with two steps and, under the read step, the two versions with their models; switching back to Run keeps that page selected. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneGroupByFileTests.swift`, the existing `ActivityTableTests.swift`.
- `activity.pane.inspector-shows-the-selected-row` — **[PARTIAL]** (built #6441: `ActivityInspectorSection` in both Inspectors; not built: ActivityInspectorSectionTests.swift; #6441, decision 2; `activity.details.one-view`, #5561) the EXISTING Inspector column shows the selected row in an **Activity** section that IS the one details view (`ActivityDetailsView`: heading, state and why, stage bar and page grid for a run, pages done and failed with Read Again, what it made, details and log disclosures, resources, actions), mounted there and nowhere else: the Activity Detail window (`FicheroApp.swift:694`) and the details' mounts inside the window and the sidebar mode go; selecting a run, a step, a version or a file shows its details; with nothing selected the section shows nothing (`activity.window.no-empty-prose`); in a main window the Inspector shows the Activity section while the Activity pane holds the focus (the last pane clicked) and a row is selected, and the document's sections again once another pane takes the focus; the Inspector's other sections stay for a selected page (so a file row's Inspector shows the page's own sections too). Acceptance: selecting a version row shows its heading, model and pages in the Inspector; selecting nothing shows an empty section; no Activity Detail window exists. *Test:* `ActivityInspectorSectionTests.swift` (not yet written; the section per row kind, the empty state), the existing `ActivityDetailsTests.swift`.
- `activity.window.is-the-pane-plus-inspector` — **[OK]** (built #6441: one window, the pane plus `.inspector`; the popover's Show and Open Activity focus an Activity pane already in the window, else open the window; #6441, decision 1) the generic Activity window (Window › Activity, ⌥⌘0 kept in the command table) is ONE Activity pane plus the Inspector column, built from the pane kind with a `PaneList` of one leaf, not a view tree of its own: `ActivityMonitorWindow`'s body becomes the pane; its selection is the window's ONE selection: the Activity window is a single `Window` scene, so its selection is the one `ActivityWindowSelectionState` (Show in Activity writes it, then opens the window), while an Activity pane in a main window writes that window's `WindowState.activityPick`, which the main window's Inspector reads; the toolbar status item's popover stays the summary (`activity.popover.summary`) and its Show opens this window or reveals an Activity pane already in the front window. Acceptance: the window's view tree is a pane list with one Activity leaf and the Inspector; Show in the popover brings the pane forward. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityWindowIsAPaneTests.swift`.
- `activity.pane.history-kept-and-filterable` — **[OK]** (built #6441: one filter field, the tokens kept per pane; #6441, decision 5; `activity.window.history-group`, `activity.run.record-keeps-all-history`) history is KEPT (every ended run, of any kind, in the same flat table after the live rows, as the engine's `group: "earlier"` already marks it; no History section row; Archive Finished… and Archive Failed hide it, `activity.pane.archive-old-runs`) and FILTERABLE through one filter field in the pane header that takes tokens as Finder's search does — recipe, step, model, state, date (a day or a range), file, started by — combined with AND (typed as `key: value`, the value matched case-insensitively as a substring of the row's name, step trail, model, state words, file names or starter; `date:` takes `today`, `YYYY-MM-DD` or `YYYY-MM-DD..YYYY-MM-DD` against the row's start; text with no key matches the name; an unknown key is plain text), applied to both groupings, per pane and remembered; the engine's existing filters serve what they can (`GET /api/activity`'s `types`, `since`, `until`, `search`; the job list's kinds) and the rest is filtered in the app over the loaded trees; a filter that hides everything says "No activity matches" in one line. Acceptance: the token "model: Kraken" with "state: failed" shows the one failed Kraken version and its page; clearing the tokens shows everything; the tokens survive a relaunch. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneFiltersTests.swift`, the existing `ActivityHistoryGroupTests.swift` and `test_activity_order_live_run_first.py`.
- `activity.pane.run-automatically-is-a-setting` — **[PARTIAL]** (built #6441: Settings › General's switch, "Automatic work paused" in the status bar, Project › Activity's Pause / Resume Automatic Work, the toolbar's `ActivityModeButton` gone; not built: the project's own setting; #6441, owner ruling; `activity.window.background-group`, `activity.recipe.declares-automatic`) **Run Automatically** is a SETTING, not a toolbar mode: in Settings › General a plain label **Run automatically** with one sentence under it ("Fichero processes new and changed pages in the background: thumbnails, text, names and search."), and the same in each project's settings with "Use the app's setting" as its default (the project's answer wins when set); the toolbar's `ActivityModeButton` goes. The pane has no section rows (`activity.pane.less-is-more-table`), so it SHOWS the state only as the last item of its one status bar while automatic work is paused ("Automatic work paused"; nothing while it runs) and offers the two verbs in the command table, worded so that neither can be read as the other: **Pause Automatic Work** / **Resume Automatic Work** for the background lane; a row's verbs are the one verb list's (**Pause**, **Continue**, **Stop**, **Retry**), whose help and accessibility label name the row ("Pause Letters"). Acceptance: turning the setting off in Settings shows "Automatic work is paused" in every Activity pane and no background row starts; a running row's button reads Pause and a paused one's Continue (never Resume); the command reads "Pause Automatic Work". *Test:* `fichero/Tests/Unit/general/Models/RunAutomaticallySettingTests.swift`.
- `activity.pane.commands-through-the-table` — **[PARTIAL]** (built #6441: the verbs in Project › Activity through the focused pane, Pause / Resume Automatic Work, Show in Activity in a page's context menu and File menu, View › Activity ▸; not built: Copy Link, which waits on `profile.links.one-link-two-forms` (#6439); #6441; `menus.one-command-table`, `menus.chords-are-standard-mac`, #6435) every Activity verb lives in the one command table and acts on the pane's selection wherever the pane is: Window › Activity (⌥⌘0, kept); Project › Activity › Stop, Read Again (as built, `menus.project.activity-stop-read-again`, now on the pane's focused selection); Pause / Continue, Retry, Archive, Put Back, Delete, Pause Automatic Work / Resume Automatic Work, **Show in Activity** (from a page or folder's context menu: reveals the file's row in Group by File), **Group by Run** / **Group by File** and **Show Archived** (View › Activity ▸, no chord), Archive Finished…, Archive Failed, Copy Link (the row's deep link, `profile.links.one-link-two-forms`); each appears in the menu bar, the pane's context menu and the Inspector's actions from the one definition; no new chord (the uniqueness test is the judge). Acceptance: the command table lists each verb once with its surfaces; Show in Activity on a page reveals its file row; the uniqueness test passes unchanged. *Test:* the existing `MenuShortcutUniquenessTests.swift`; `fichero/Tests/Unit/general/Models/ActivityPane/ActivityCommandsTests.swift`.
- `activity.pane.one-glyph-per-state` — **[OK]** (built #6441: `ActivityPane.glyph`; #6441, decision 8) every row's STATE is ONE glyph, the system's where one exists, never a word beside it: waiting a hollow circle, running the indeterminate spinner (`ProgressView` circular, the Mac's), done a check in a filled circle, failed a RED X in a filled circle, paused the pause glyph, stopped the stop glyph, skipped a dash; the glyph carries the state's name as its accessibility label and tooltip, so the word exists for VoiceOver and hover only; no timestamp is written as text where a glyph or a bar says it (a running row shows its spinner and its trail, or "12 of 40" when it has no stages, not "started 14:02"; a done row shows its check and ONE time, the duration or the finish time by the column's choice, never both; "about 12 min left" stays, as the one time of a running row). Acceptance: a row in each of the seven states shows the glyph and no state word; a running row has no timestamp text; VoiceOver reads "running" on the spinner. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityStateGlyphTests.swift`, the existing `ActivityTableTests.swift`.
- `activity.pane.default-columns` — **[OK]** (built #6441: six on, four in the header menu, kept per pane; #6441, decision 8; REVISED by the review: Cost ON, the owner asked twice) the table's columns and their defaults are the one column table above (source glyph, name, state, trail, time, cost on; model, started by, started, kind glyph off), each a plain toggle in the header's menu (right-click, as every Mac table), remembered per pane; the Inspector shows every fact for the selected row, so nothing is lost by hiding a column. Acceptance: a fresh pane has the six default columns; turning Model on in the header menu adds it and survives a relaunch; the Inspector shows the model whether the column is on or off. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityDefaultColumnsTests.swift`, the existing `ActivityTableTests.swift`.
- `activity.pane.error-row-shape` — **[PARTIAL]** (built #6441: the red X, the one line, the one fix button, pages failing for one reason said once with their count; not built: Download (the fix button opens Settings); #6441, decision 8; `runtime.errors-are-typed`, `designer.budget.refusal-offers-the-fix`, `source.recipe.check-names-every-fault`) a failed row is a RED X, ONE SHORT LINE (the typed refusal's sentence, cut to the text budget: "Qwen 2 VL is not downloaded", "No key for OpenRouter", "Page image unreadable"), and the FIX the refusal itself offers as the row's ONE button (its primary action; the other offers — Download, Add Key…, Read Again, Use Next Candidate, Skip Page, the offers the engine's typed errors and the recipe check already carry, never invented in the view — in the context menu and the Inspector), with the full reason, the log and the stack a disclosure in the Inspector on demand; several failed pages under one step collapse to one line with the count and one set of fix buttons when their refusal is the same. Acceptance: a step whose model is missing shows the red X, the one line and Download; a run with twelve pages failing for the same reason shows one error line with "12 pages" and Read Again; the Inspector has the full text. *Test:* `fichero/Tests/Unit/general/Models/ActivityErrorRowTests.swift`, the existing `ActivityDetailsTests.swift`.
- `activity.pane.text-budget` — **[OK]** (built #6441: every cell held to eight words, no sentence; #6441, decision 8; the app-wide rule `menus.less-text-more-indicator`) a row is a LINE, never a paragraph: a word is a whitespace token; the NAME cell is exempt (a file's or recipe's name is cut with a middle ellipsis, as Finder does); a state line at most EIGHT words ("7 of 20 pages · about 12 min left"), an error line at most EIGHT words, no cell holds a sentence (no full stop inside a row), counts as figures with units ("3 pages", "2.1 MB", "$0.04"), no "Currently", "Successfully", "Please"; anything longer belongs in the Inspector. The budget is a test over the row model's strings, not a guideline. Acceptance: every row the fixture trees produce passes the word counts and holds no full stop; a failure's row words are the kind's own ≤ 8-word column (`run.fail.kinds-table`), never a sentence cut at a word boundary; the full sentence is in the Inspector. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityTextBudgetTests.swift`, the existing `ActivityRowSubtitleTests.swift`.
- `activity.foreground.rank-on-the-row-and-the-pick` — **[GAP]** (#6442; the engine half of `activity-and-automatic-work.md` Step 1.14, #6352, made concrete: `activity.foreground.open-jumps-the-queue`, `.order-is-the-views`, `.drops-back-when-moved-on`, `.background-never-starved`) the page IN VIEW is processed first. Facts read in the engine (not run): the one job model has no queue rank; the waiting reads order by `created_at` (`execution/jobs.py` 1149, 1348, 2523, 2769), FIFO apart from the `watched` flag (`activity.throttle.watched-first`: first in its lane, utility QoS, `jobs.watched`); `priority` in `execution/throttle.py` is the COMPUTE priority of a job once it runs, not its place in the queue; `enqueue` (jobs.py 1298) has `run_after` and `watched` but no rank, and REUSES a job of the same kind and subject already waiting. The ONE engine addition, the same one Step 1.14 names: `foreground_rank INTEGER DEFAULT 0` on the jobs row (an `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, as `watched` was added), the lane's pick `ORDER BY foreground_rank DESC, watched DESC, created_at`, and the bump an UPDATE of the EXISTING waiting jobs of the page in view — never a new row, never a re-run of done work (a done job is reused as today) — ranked in STEP ORDER so the page's pipeline completes in sequence: the thumbnail and working rendition, then Find Regions, Find Lines, the Reader (the pipeline order `KINDS` declares; the page in view highest, then its neighbours as 1.14's view order says). The rank is REVERTED to 0 when the person moves on (the client's next set replaces it) or when the set EXPIRES (1.14's 90 s without a heartbeat), and it never starves the rest (1.14's one pick in four and the five-minute age). The app tells the engine the page in view through the one report Step 1.14 defines (`PUT /api/activity/foreground`, the Preview, the browser and the Activity selection feeding one reporter, 300 ms settle, 30 s heartbeat): no such event exists today (checked: no view, focus or foreground route in `api/routes`), so that one route is the only API, and it is 1.14's, not a second one. Acceptance: page 23 opened in the Preview with its Find Lines and reading waiting: both rows get a rank above 0 with Find Lines ahead of the reading, the lane's next pick is Find Lines for page 23, and the row already done for the page is not touched; the person opens page 60: page 23's waiting rows return to 0 on the same call; a bulk run behind it still advances one pick in four. *Test:* `test_page_in_view_first_6442.py` (not yet written; the column, the pick order, the UPDATE of existing rows in step order, no new row, the revert, the aging), the existing `test_person_started_work_goes_first_5820.py`.
- `activity.foreground.one-glyph-not-words` — **[GAP]** (#6442, decision 8; supersedes, for the pane, the wording of `activity.foreground.shown-in-activity`) the Activity pane shows the jump with ONE INDICATOR and no sentence: a bumped waiting row carries the "in view" glyph (an eye, `eye.fill`) beside its state glyph and moves up to its pick place in the lane's order; the tooltip and the accessibility label carry the words ("Next: the page in view"); the summary line of the background section counts it in figures ("3 for the page in view · 212 more"), within the text budget; a row that dropped back loses the glyph and nothing else changes. Acceptance: with page 23 in view its two waiting rows show the eye and sit first in their lanes; moving to page 60 moves the eye; no row text changes. *Test:* `ActivityForegroundGlyphTests.swift` (not yet written; the glyph on bumped rows, the order, the summary figures), the existing `ActivityTableTests.swift`.

### Ruled 2026-11-13 night: the table that says what ran on what, nothing starts by itself, one cap, one window

- `activity.launch.nothing-starts-one-alert` — **[PARTIAL]** (#6584, decision 14; supersedes the auto-resume of `activity.run.quit-pauses`
  and the "Interrupted; carries on" requeue of `jobs.resume`, `activity.relaunch.only-running-work-resumes`) after a quit, crash or
  engine restart the open STARTS NOTHING. Engine: on library open every unfinished row no live lane thread owns (running, waiting,
  pausing, a workflow run the quit paused) becomes `paused` with the line "Stopped when Fichero quit" (a row already paused by a
  person or for a cause keeps its own line; a row set aside, failed, stopped or done is not touched; a deleted row ends, as
  `activity.window.delete-any-row` says); the lane is not woken for them; `GET /api/activity/stopped-at-quit` lists them (id,
  name, what it ran on, how far, when it stopped) for the alert, and `POST /api/activity/stopped-at-quit/continue` with `ids` (or
  `all: true`) lets the chosen ones go (the stored pause lifted, the lane woken), answering what it let go. The automatic kinds
  (thumbnails, embeds, names) are unfinished work too and wait with the rest; new material arriving after the open is new work
  and runs by the Run Automatically setting. App: ONE alert at launch when the list is not empty, titled by the count ("3 runs
  were stopped when Fichero quit") with each row's name and what it ran on, and three buttons: **Leave Paused** (the default,
  nothing runs; the rows stay paused in Activity with Continue), **Choose…** (opens Activity with those rows selected) and
  **Continue All**; the alert shows once per LIBRARY OPEN, deduplicated by row id (a project opened mid-session with quit-stopped rows gets its alert too); the automatic kinds are rolled into one line ("… and background work: 412 thumbnails, 80 embeds") and Continue All includes them; 400 paused thumbnail rows never hold the heavy work behind them (`activity.lane.no-wait-on-a-job-that-will-not-run`: the thumbnails-first hold reads paused rows as not coming). The list route is a convenience over `GET /api/activity/jobs` (paused rows with the quit reason); the continue route is the one batch verb decision 7 allows, a single row's Continue being `PUT /jobs/{id}/paused`. A rescan of a synced folder at open may RECORD what arrived but starts no recipe run: new material found at open is one more line of the alert ("12 new files in <folder>") with the same three buttons. Acceptance (engine): a library with rows running, waiting, pausing, failed,
  done and a quit-paused workflow run is opened by a fresh engine; with the lane's pick stubbed, no pick is requested (not a sleep), the running, waiting, pausing and quit-paused ones read `paused` "Stopped when Fichero quit", the failed one is failed
  with its reason, the done one done; the list route names exactly the four; continue with two ids starts those two and leaves
  two paused. Acceptance (app): the alert's default action sends nothing and the rows stay paused; Continue All posts
  `all: true`. **Built (2026-11-13 night):** engine `jobs.resume` pauses every unfinished row with `QUIT_REASON` (the
  set-aside after three interruptions is gone with the requeue), `jobs.stopped_at_quit`, `jobs.continue_after_quit`,
  `resume_quit_paused_runs` resumes only the thread ids the person chose (the launch passes none), the two routes; the
  contract regenerated. App: `StoppedAtQuitAlert` (title, message, Leave Paused default, Continue All) mounted over the main
  window by `StoppedAtQuitAlertModifier`, asked once per project as it opens; Choose… opens the Activity window; the automatic
  kinds roll into one line ("and background work: 412 thumbnails, 80 embeds") and a held folder read into "New files in a
  synced folder" (the review's answers, 2026-11-14). Not compiled here. Not built: the alert's rows selected in Activity on
  Choose…; the folder's name on the new-material line.
  *Tests:* `fichero-server/tests/unit/jobs/test_launch_starts_nothing_6584.py`,
  `fichero-server/tests/unit/jobs/test_launch_to_continue_end_to_end_6584.py` (quit with running, paused, waiting, automatic
  and new-material work → open → nothing picked → all listed → Continue two → only those two run),
  `fichero-server/tests/unit/jobs/test_rescan_at_open_holds_for_the_alert_6584.py`,
  `fichero-server/tests/unit/jobs/test_relaunch_resumes_only_running_work_6584.py`,
  `fichero-server/tests/unit/workflows/test_quit_paused_runs_resume_5357.py` (inverted: they stay paused),
  `fichero/Tests/Unit/general/Models/ActivityLaunchAlertTests.swift`.
- `activity.run.failed-is-never-requeued-by-itself` — **[PARTIAL]** (#6584, decision 15) a row that ended `failed` or `stopped` is run
  again ONLY by a person's Retry (the row's, the alert's, Read Again): not by the open (above), not by automatic work (the open's
  derivative recovery skips a document whose derivative failed, built in `jobs`/`derivatives` 2026-11-13; a recipe's automatic
  start runs only over material that ARRIVED, never over pages whose last run failed), not by a recipe that finds its awaited step
  run gone (`pause_recipe`: the recipe stays paused and says "Its step's run is gone. Continue to run that step again", instead of
  re-queueing it by itself), and not by a lane's attempts counter (`MAX_ATTEMPTS` applies to interruptions, and an interruption
  now pauses). Acceptance: a library with yesterday's failed recipe run, a failed thumbnail and a recipe parked on a step run that
  was deleted is opened and left for a minute with Run Automatically on: no new row, no model call, the failed rows unchanged, the
  parked recipe paused with the line above. **Built (2026-11-13 night):** the open touches no failed row; a document whose
  derivative failed is not queued again at open, and the failure is LOUD: a thumbnail or embed that cannot be made ends its
  job failed with a plain sentence and its fix ("The thumbnail for page.png could not be made. Try again, or open the file to
  check it is a readable image."), the raw error kept on the document for Copy Details (`derivatives.DerivativeFailed`); a
  rescan at open holds the synced folder's read for the launch alert instead of importing and starting a recipe run
  (`sync_folder.rescan(hold=True)`, `jobs.NEW_MATERIAL_REASON`). Not built: the parked recipe staying paused when its step run
  is gone (today a person's Continue re-runs that step; no self-restart was found there). *Tests:*
  `fichero-server/tests/unit/importers/test_derivative_failures_are_loud_6584.py`,
  `fichero-server/tests/unit/jobs/test_rescan_at_open_holds_for_the_alert_6584.py`,
  `fichero-server/tests/unit/jobs/test_relaunch_resumes_only_running_work_6584.py` (the failed and derivative halves);
  not yet written: test_failed_is_never_requeued_6584.py (the minute-long automatic tick).
- `activity.run.never-repeats-done-work` — **[PARTIAL]** (#6584, decision 18; the owner's standing rule that every model call reuses an
  existing result for the same input and model first, `reviewer-no-model-reruns`) when a run continues (Continue after a pause or a
  quit, Retry on a failed run, a recipe re-run over the same pages) every page or item that already has a result for the same
  key — (step id, inputs fingerprint, model card id, settings hash: a prompt change is a new key) — is reused and marked skipped ("already done"), and only the
  missing or failed items go to the model; the run's counts say "6 reused · 4 read". Acceptance: a run over 10 pages whose model
  fails after 6, retried, makes exactly 4 model calls and ends done with 10 results; a second recipe run over the same 10 pages with
  the same model makes 0 calls. **Built (2026-11-13 night):** the Retry half, pinned: a run of 10 pages whose model
  fails after 6, retried from its row, makes exactly 4 calls (`read_again` over the pages not done) and the new run
  ends done with 4. Not pinned: a recipe re-run over pages already read with the same model making 0 calls. *Tests:*
  `fichero-server/tests/unit/jobs/test_continue_makes_only_the_missing_calls_6584.py`; the existing
  `fichero-server/tests/unit/recipes/test_embed_once_after_reading_6186.py`.
- `activity.limits.one-cap-per-kind-across-everything` — **[PARTIAL]** (#6584, decision 16; built in part: the lanes `LANES` in
  `jobs.py` cap jobs per lane (`remote` 2, `network` 4, `local-ml` 1 with `LOCAL_READS_CEILING` 4 for the loaded local
  model), `MemoryShortError` and the throttle hold local work by memory and battery; NOT built: a cap per PROVIDER across runs,
  batches (`batch.py` `max_concurrent` 5 is per batch) and the workflow fan-out (`builder.py` semaphores are per process,
  not per provider), so three runs on one provider send three times the cap) ONE rule in the engine: a cap per kind of work that
  every path obeys because every model call and every page passes through the lane (`run_on_lane`) and the lane counts in flight
  per key — cloud calls per provider (default 4, the network lane's width, a setting `cloud_calls_at_once` 1–8 in Settings › AI with one sentence; the lane's own per-provider fairness is the finer rule for the work it runs), local
  model pages per loaded model by the machine (`reads_at_once_for_model`, memory-bound, 1–4), Kraken pages `kraken_pages_at_once`
  = 1 under 16 GB of RAM, 2 at or above (memory injected in tests), thumbnails 2, embeds 1; a batch or a fan-out of 500 pages queues 500 rows and the lane starts at most the cap; the rest read
  "waiting for a slot: 3 of 3 OpenRouter calls in flight"; the pane's background line counts "N running · M waiting". Acceptance:
  500 queued Kraken page jobs → at most the cap running at any moment over the whole run; 50 cloud calls across 3 runs to one
  provider → at most the provider cap in flight at any instant (a stub provider that records concurrency); a second provider's
  calls are not held by the first's cap. **Built (2026-11-13 night):** the per-PROVIDER cap, at the one retry layer every
  cloud call passes through (`circuit_breaker.call_with_breaker`: a threading semaphore per provider across every loop and
  thread, `PROVIDER_CALLS_AT_ONCE` 4 = the network lane's width, `FICHERO_CLOUD_CALLS_AT_ONCE` 1–8 until the setting exists;
  a call a lane thread runs is capped by the lane and takes no slot here; `calls_in_flight` for the words). Already there, verified 2026-11-14: the Kraken cap IS memory-bound in one place (`kraken_runtime.pages_at_once`:
  two pages for a person's run when memory holds two, else one; `test_kraken_page_gate_two_at_once.py`), and the local
  model's reads follow memory (`local_reads_at_once`, 1–4). Not built: the Settings › AI control, the "waiting for a slot"
  words on the row, the batch and fan-out semaphores folded onto the provider cap. *Tests:*
  `fichero-server/tests/unit/llm/test_one_cap_per_provider_6584.py`; the existing
  `fichero-server/tests/unit/jobs/test_kraken_page_gate_two_at_once.py`, `fichero-server/tests/unit/jobs/test_throttle.py`.
- `activity.limits.rate-limit-backs-off-then-pauses` — **[PARTIAL]** (#6584, #6354, decision 16; consistent with `run-failure-alerts.md`
  decision 2 and its `rate-limited` kind; built in part: `circuit_breaker.call_with_breaker` backs off with jitter honouring
  Retry-After up to 120 s, `retry.py` marks the provider dead for 30 s; NOT built: the pause — today the page FAILS after the
  retries and the run ends failed or partial) a 429 or rate-limit answer backs off honouring Retry-After (exponential with jitter,
  capped at the table's cap), while the provider's whole cap is held (no other call to that provider starts during the back-off);
  `RATE_LIMIT_PAUSE_AFTER` (3) consecutive calls whose bounded back-off was spent on 429s PAUSE every run calling that provider,
  with the row words "OpenRouter is limiting how fast you can send" and the fix "Wait 2 minutes, then Continue" — the wait is
  `RATE_LIMIT_WAIT_SECONDS` = max(Retry-After, 60); the Continue button enables when it is up; there is NO automatic Continue (the
  back-off IS the automatic retrying) and the alert of `run.fail.alert-on-a-failed-run` for the `rate-limited` kind; never a tight loop (no two sends to
  a rate-limited provider less than Retry-After apart), never a silent requeue. Acceptance: a stub provider answering 429 with
  Retry-After 2 sees gaps of at least 2 s between sends, at most the cap in flight, and after `RATE_LIMIT_PAUSE_AFTER` spent calls the run reads paused
  with those words and that fix and nothing is sent to that provider until Continue; the run continued after the provider recovers makes only the missing calls. **Built
  (2026-11-13 night):** at the one retry layer (`llm/retry.resilient`) a slow-down whose bounded back-off is spent (the
  provider's Retry-After the floor of every wait) asks the run this call belongs to to pause and records the cause
  (`paused_for_rate_limit`); the run's paused record carries the `rate-limited` failure with the provider (`_finish_as_paused`),
  whose words are now "<Provider> is limiting how fast Fichero can send" with the fix "Wait a few minutes, then continue
  the run…" and a `resume` action; Continue on the recipe row clears the cause with the cap's (`forget_rate_limit_pause`); the
  provider's fail-fast mark keeps its K-in-a-row rule (#950). **Numbers built (after the review):** `RATE_LIMIT_PAUSE_AFTER`
  (3) consecutive spent calls before the pause, `RATE_LIMIT_WAIT_SECONDS` (60) as the floor of the wait the row asks
  (`wait_seconds` on the recorded pause), no automatic Continue. Not built: the row's inline fix button with its wait
  (`activity.pane.failure-with-its-fix-in-the-row`); the whole provider cap held during a back-off (the slot is let go, as
  before). *Tests:*
  `fichero-server/tests/unit/llm/test_rate_limit_backs_off_then_pauses_6584.py`; the existing
  `fichero-server/tests/unit/workflows/test_paused_at_cap_event_6349.py`.
- `activity.limits.load-a-model-once` — **[PARTIAL]** (#6584, decision 17; built in part: `local_inference` keeps the engine's model
  server's one loaded model and the lane's `loaded_model`/`loaded_used_at` (`activity.lane.group-by-model`); to verify for Kraken:
  `kraken_runtime.py` loads per call) one loaded instance per model per engine, shared by every job that needs it: pages are fed
  to it from the lane's queue (grouped by model, as the lane already orders), it stays loaded while work for it waits and for
  `MODEL_IDLE_GRACE_SECONDS` (120) after, and is released when idle or when `MemoryShortError` asks; no path loads a second copy of a model the
  engine holds. Acceptance: 20 queued Kraken pages across 3 runs load the Kraken model exactly once (a counting stub loader) and
  release it once after the last; the same for the local reading model. **Already there, verified 2026-11-14 and pinned:**
  Kraken's resident cache (`kraken_runtime._resident` under `_LOAD_LOCK`: one segmenter, one reader template with a bounded
  copy pool, a replacement unloading the one held, `release_resident_models` when idle or before another heavy model) and the
  engine's one local model server. Not verified: the idle grace as a named constant (`MODEL_IDLE_GRACE_SECONDS` 120) and the
  reader pool's size against the cap. *Tests:* `fichero-server/tests/unit/llm/test_load_a_model_once_6584.py`; the existing
  `fichero-server/tests/unit/jobs/test_a_run_does_not_juggle_models_5939.py`.
- `activity.pane.row-says-what-ran-on-what` — **[PARTIAL]** (#6441, decision 12) every row of the table answers what ran on what: a
  RUN row names its recipe (or its kind in words for a job of its own), the folder, document or pages it runs over ("Register 3
  · 120 pages", "Folder Letters · 14 files"; never an id), its step NOW ("Read lines ▶ 34/120"), its model or provider, who started
  it (an icon, `activity.pane.icons-say-source-and-kind`), when it started and how long it has run, its result when ended; a STEP
  row names the step, its model, its pages done/failed/left; an ITEM row names the page or file and its result. The STEP TRAIL is
  one cell on the run row: the steps in order, each with its glyph (done ✓, running ▶ with its fraction, left ·, failed ✗), so
  "Import ✓ → Segment ✓ → Read lines ▶ 34/120 → Entities ·" reads at a glance; the engine supplies it: `GET /api/activity/jobs`
  gains per row `ran_on` ({kind: folder|document|pages, name, count}), `steps` (ordered: name, state, done, total, model) and
  `model` (display name), computed from the run record and the tree it already has (`runner.status`, `name_and_pages`), so the
  app adds nothing. Acceptance: a recipe run over 120 pages at its third step lists with `ran_on.count` 120, four `steps` with
  states done, done, running (34/120), waiting, and the row's cell reads exactly the trail above; a thumbnail group lists with
  `ran_on` the import's folder. **Built (2026-11-13 night, engine):** every row of `GET /api/activity/jobs` carries `ran_on`
  (`pages`/`page` with the count; a group row the pages it stands for), a recipe run its `stages` (Set Up's stages in
  order, each with title, state, done, failed, total: the same `StageCount` the live block draws) and `model` (the stage
  running now, from the tree). App (2026-11-14, linted, not compiled): `ActivityJob` decodes `stages`, `ran_on`, `model`
  and the costs; `ActivityTrail.text` builds the one trail line ("Import ✓ → Segment ✓ → Read ▶ 34/120 → Names ·"),
  `ActivityTrail.statusBar` the one status line, `ActivityTrail.cost` the cost cell. Not built: `ran_on.name`, the per-step
  model, the trail drawn in the table (Step 2.6). *Tests:* `fichero-server/tests/unit/jobs/test_row_says_what_ran_on_what_6441.py`,
  `fichero/Tests/Unit/general/Models/ActivityStepTrailTests.swift`; the existing
  `fichero/Tests/Unit/general/Models/ActivityTableTests.swift`.
- `activity.pane.icons-say-source-and-kind` — **[PARTIAL]** (#6441, decision 12) ONE small icon column, two glyphs at most per row:
  the SOURCE (started by a person: `person`; automatic: `gearshape.arrow.triangle.2.circlepath`; a recipe's step: `list.bullet.rectangle`;
  a schedule or trigger: `clock`) and the KIND of step (read: `text.viewfinder`; segment or find lines: `rectangle.split.3x1`;
  entities and names: `person.text.rectangle`; thumbnails: `photo`; search embed: `magnifyingglass`; the RUNTIME — Kraken, a cloud
  model, a local model — is the Model column, not a glyph), the word in the tooltip and the accessibility label, and "Started by" and "Kind" as filter
  tokens; the icons replace the Started by and Kind text columns, which go. Acceptance: the fixture rows map to these symbols
  from the engine's `started_by` and `task_type` in one function; no row text names the source. **Built (2026-11-13 night):**
  the one mapping on the row model (`ActivityMonitorRow.source(startedBy:)`, `kindSymbol(engineKind:)`, each with its word);
  not compiled here. Not built: the icon column and the filter tokens; cloud vs local needs the row's model. *Tests:*
  `fichero/Tests/Unit/general/Models/ActivityRowIconsTests.swift`; the existing
  `fichero/Tests/Unit/general/Models/ActivityRowStartedByTests.swift`.
- `activity.pane.cost-per-row-and-totals` — **[PARTIAL]** (#6441, decision 20; `activity.window.cost-column` built the per-node
  `cost_usd`; `ai/cloud-permission-and-spend.md` keeps the records) the Cost column (default hidden, `activity.pane.default-columns`;
  shown in the Inspector always) shows per row the dollars SPENT so far and, while running, the ESTIMATE to finish ("$0.42 · ~$1.10
  more", from the plan's per-page estimate times the pages left, `spend.caps_now`'s basis); the run row totals its steps; the
  background section's line totals per provider for the day ("OpenRouter $3.20 today"); local work shows no cost and its time
  instead; "Not priced" when a call has no price, never "$0". Acceptance: the fixture run with two cloud steps and one local step
  shows the two costs, the run's total, no cost on the local step, and the estimate falls as pages finish. **Built
  (2026-11-14, engine):** every list row carries `cost_usd` (a recipe run's cloud dollars so far, `live_stages.cost_so_far`;
  null for local work or no priced call, never 0) and `cost_estimate_usd` (the running stage's spent-per-page times its pages
  left, `_cost_estimate`; null when ended or nothing priced yet). Not built: the plan's per-page estimate as the basis before
  the first page is priced; the per-provider daily total line; the app's column. *Tests:*
  `fichero-server/tests/unit/jobs/test_row_says_what_ran_on_what_6441.py`; the existing
  `fichero-server/tests/unit/jobs/test_run_tree_rolls_up.py`;
  not yet written: ActivityCostColumnTests.swift.
- `activity.pane.row-actions-on-the-table` — **[PARTIAL]** (built #6441: the one verb list by the Mail rule, published by the focused table; Stop then Delete after one confirmation, a running run stopped first; Delete, Archive and Put Back of jobs are the audited actions, one step on the window's stack, so Edit › Undo takes them back; a run row's Archive is the engine's `workflow_run.archive` (nothing deleted; Undo and Put Back are `job.unarchive`), test `fichero-server/tests/unit/jobs/test_archive_runs_6441.py`; not built: Undo of a run's delete (the engine's `workflow_run.delete` is not undoable); #6441, #6583, decision 11; `activity.window.delete-any-row`,
  `activity.pause.per-job`, `activity.retry.one-row`) the verbs live on the table: a row's one button (`activity.window.one-button`)
  shows the verb its state allows (the states table above), the context menu lists the one verb list, each enabled by the MAIL RULE (above: enabled when any selected row allows it,
  applied to those, the rest skipped and counted in the status bar), the Delete key and ⌘⌫ delete the selection, ⌘A selects all
  shown, and Edit › Undo undoes a Delete or an Archive (the engine's `job.delete`, `job.archive` and `workflow_run.delete` are
  undoable: the row comes back in the state it had); Delete on a running row is Stop then Delete after one confirmation; a row that
  ended between the click and the request is judged by the engine at receipt and answered skipped, and the app re-reads. Acceptance:
  with a failed, a paused and a running row selected the menu enables Delete, Stop, Continue and Pause (the Mail rule: a verb is on when ANY selected
  row allows it, and each row that does not is skipped and counted); ⌘⌫ asks once for the running one, deletes all three, and the status bar counts them; Undo lists them again in
  their former states. The states table above is this behaviour's fixture. *Tests:*
  `fichero/Tests/Unit/general/Models/ActivityDeleteAnyRowTests.swift`, `fichero-server/tests/unit/jobs/test_delete_any_row_6583.py`,
  `fichero-server/tests/unit/jobs/test_every_state_takes_its_verbs_6583.py` (built 2026-11-13 night: the engine's verbs in every
  state of the table above, through the routes; the table is its fixture), `fichero/Tests/Unit/general/Models/ActivityPane/ActivityRowActionsTests.swift`
  (the states table, the Mail rule, the one button);
  not yet written: test_delete_is_undoable_6583.py.
- `activity.pane.archive-old-runs` — **[PARTIAL]** (#6583; review 2026-11-13 night, item 1; the Trash-is-a-folder ruling: a PLACE with Put
  Back, not a mode) **Archive** hides a finished, failed, stopped or partial row from the table and keeps everything (results,
  cost, history, the record): Archive on one row or many (context menu, Project › Activity, multi-select), **Archive Finished…**
  (every ended row in every open project, one confirmation; replaces Clear Finished…) and **Archive Failed** (replaces Clear
  Failed), and **Archive Finished Older Than…** (a day, a week, a month). **Show Archived** (View › Activity ▸, a filter token)
  lists them greyed with **Put Back** (restores the row as it was, in place) and Delete. Engine: the row's `archived_at` (today's
  `cleared_at` column, renamed in meaning: a mark the list reads, never a state change; a waiting or paused row cannot be archived,
  only ended ones), the audited undoable `job.archive` and `job.unarchive` behind `POST /api/activity/jobs/archive` and
  `…/unarchive` (`ids`, or `states` + `older_than`), `GET /api/activity/jobs?archived=true` for the Show Archived list; a workflow
  run archives the same way (`workflow_run.archive`: the archive mark on the run's own row in `jobs`, whose id is the run's thread id, so the runs list leaves it out; never the runs' soft delete). A retry of an
  archived failed row puts it back first. Auto-archive of finished runs after N days is a setting, default OFF (open question 9).
  **Delete is REDEFINED** (`activity.window.delete-any-row` in `activity-and-automatic-work.md` revised the same night): Delete
  REMOVES the row from every list, including Show Archived and every Retry list; the engine keeps the record for the audit
  (`deleted_at`, a new column applied as `cleared_at` was, `activity.jobs-added-columns`), never the row in any listing; Undo in
  session restores it in its former state; a waiting or paused row deleted is stopped first (its in-flight page's result is
  discarded and said so). Acceptance: a done run archived leaves the table, shows greyed under Show Archived with its cost and
  stages intact, Put Back lists it again unchanged; Archive Finished… after one confirmation archives every done, failed, stopped
  and partial row in two open projects and none still going; a failed row deleted is absent from the table, from Show Archived and
  from `GET /api/activity/jobs?archived=true`, and Undo lists it again as failed with its reason. **Built (2026-11-13 night,
  engine):** `jobs.archive_jobs` (ids, states, older_than_days; a waiting, paused or running row and a kind's row skipped and
  named), `unarchive_jobs`, `undelete_jobs` (a row Delete stopped remembers its state in `detail.deleted_from` and comes back
  as it was), the `deleted_at` column applied like `cleared_at`; `delete_jobs` sets both marks; the audited, undoable
  `job.archive` / `job.unarchive` / `job.delete` / `job.undelete` behind `POST /api/activity/jobs/archive`, `…/unarchive`,
  `…/undelete`; `GET /api/activity/jobs?archived=true` lists the archived top-level rows; a deleted row refuses Retry and
  is in neither list, after a relaunch too. App (linted, not compiled): the window's **Archive Finished…** (confirmation
  "Archive every finished run?") archives every ended job through `job.archive` and every ended run through `workflow_run.archive`,
  and **Archive Failed** keeps `job.clear_failed` (the archive mark) under its new name; `ActivityService.archiveJobs`,
  `ActivityStore.archiveJobs`; **Archive** and **Put Back** in the row's context menu (`ActivityGroupsView.isArchivable`:
  ended rows only; an archived row offers Put Back) and **Show Archived** in the window's menu (the archived rows read once
  per toggle, `ActivityStore.refreshArchivedJobs`, listed greyed under History with `isArchived`). **Built (2026-11-14, #6441):** the
  pane's Delete, Archive and Put Back are the audited actions through `/api/actions/invoke`, one step each on the window's
  stack, so Edit › Undo takes them back; `jobs.archive_runs` and the audited, undoable `workflow_run.archive` (inverse
  `job.unarchive`) behind `POST /api/workflow-execution/runs/archive`; `GET /api/workflow-execution/runs?archived=true` lists
  the archived runs, and Show Archived shows them. Not built: Archive Finished Older Than… in the menu; auto-archive (open question 9); swipe actions. *Tests:*
  `fichero-server/tests/unit/jobs/test_archive_old_runs_6583.py`, `fichero-server/tests/unit/jobs/test_delete_any_row_6583.py`,
  `fichero-server/tests/unit/jobs/test_archive_runs_6441.py`, `fichero/Tests/Unit/general/Models/ActivityPane/ActivityUndoTests.swift`.
- `activity.pane.automatic-runs-easy-to-delete` — **[PARTIAL]** (#6583, decision 11) an automatic run (started by the import, the
  schedule, a trigger, the derivative kinds) deletes like any other row, one at a time with the row's Delete or many at once:
  the filter token "Started by: automatic" plus ⌘A plus Delete, and **Archive Finished…** (which covers every ended row, runs AND
  jobs of their own; `activity.window.clear-finished` widened then renamed; today's `job.delete` with `states` is its engine). Acceptance: forty
  done thumbnail rows and two user runs: the filter plus ⌘A plus Delete removes the forty and leaves the two; Clear Finished… after
  one confirmation removes every ended row in every open project. **Built (2026-11-13 night):** `job.delete` takes `states`
  (every top-level job of its own in those states; workflow runs keep their delete), and the window's Clear Finished… sends
  done, failed and cancelled jobs there beside the runs delete. Not built: the "Started by: automatic" filter token.
  *Tests:* `fichero-server/tests/unit/jobs/test_delete_any_row_6583.py` (the states form); the existing
  `ActivityClearFinishedShapeTests.swift`.
- `activity.pane.failure-with-its-fix-in-the-row` — **[PARTIAL]** (#6354, #6441, decision 19; `run.fail.kinds-table`,
  `activity.pane.error-row-shape`) a failed row shows IN THE TABLE a red X, ONE plain sentence of what happened and the FIX inline
  (a button that does it, or the exact step): "Out of credit on OpenRouter. [Add credit]", "OpenRouter is limiting how fast you
  can send. Fichero will try again in 2 minutes.", "Qwen 2 VL is not downloaded. [Download]", "2 GB of disk needed. [Free up
  space…]", "Something went wrong in Fichero. [Try Again] [Report Bug…]"; never a code, an HTTP status, an exception type or a
  traceback in the row or the alert; the technical detail is a disclosure in the Inspector and **Copy Details**. The engine's
  failure table (`failure.py` `_ROWS`) maps EVERY kind to its words and its fix; a kind with no fix is a spec gap listed under
  Open questions, never shown bare. Acceptance: every kind in the engine's table has non-empty words and at least one action with a
  label; a 429, a 402 and a `KeyError` from a provider stub each list with a sentence that contains no digit code and no
  exception name, and with the fix above. **Built (2026-11-13 night):** the engine half of the test: every kind in the table
  has words, a fix and an action, and names no status code or exception text (`unexpected` names the exception's type on
  purpose, as the bug report's handle; open question 8). App (2026-11-14, not compiled): `ActivityJob.failure` decoded from
  the engine's `failure`, the fix sentence under the failed row (`activity.row.fix`), and the PRIMARY FIX as the row's one button
  (`open-settings`/`choose-model` → Settings…, `resume` → Continue, else Retry). Not built: the ≤ 8-word row words in place of
  the reason, Copy Details, the other actions as buttons. *Tests:*
  `fichero-server/tests/unit/llm/test_every_failure_kind_has_a_fix_6354.py`,
  `fichero/Tests/Unit/general/Models/ActivityErrorRowTests.swift`.
- `activity.pane.less-is-more-table` — **[PARTIAL]** (#6441, decision 13; the review's less-is-more list, accepted by the manager
  2026-11-13 night) the table's acceptance, in cuts: NO section rows (NOW / UP NEXT / DONE TODAY / History / background): a flat
  table sorted by state then start, at most View › Group by State; the five status sentences become ONE bottom status bar, Finder
  style ("3 running · 12 waiting · $3.20 today"; the automatic state lives in Settings and the toolbar, not the table); progress is
  said ONCE, by the trail (no stage bar, no subtitle; one-line rows); TWO disclosure levels (run › files; versions in the Inspector);
  at most ONE button per row (the primary fix on a failed row, else the state verb; the rest in the context menu, as Safari's
  Downloads); the kind glyph is the step kind only (the runtime is the Model column); no footer message (the status bar if
  anything); Undo for Delete and Archive only; a double-click discloses. Create is Set Up / Run Recipe: Activity never starts work,
  so it has no "+" button. iPad and iPhone show the same pane with swipe actions for Delete and Archive and the same launch alert.
  Acceptance: the fixture rows render with no section header, one status bar line, one trail cell per row and at most one button;
  a failed row's button is its fix; the table's view tree has no footer text. **Built (2026-11-14, app, not compiled):** the
  one status bar at the window's foot (`ActivityTrail.statusBar`, `activity.statusbar`) and the trail as a recipe run's one
  progress line in its row (no bar beside it). Not built: the section rows cut, two disclosure levels, one button per row, the
  footer notice folded into the status bar, swipe actions. *Tests:* `fichero/Tests/Unit/general/Models/ActivityStepTrailTests.swift`;
  not yet written: ActivityLessIsMoreTests.swift.
- `activity.one-window` — **[PARTIAL]** (built #6441: the Activity Detail window, the groups list and the sidebar job list deleted; not built: the trace sheet folded into the details; #6441, decision 10; `activity.window.is-the-pane-plus-inspector`) ONE Activity window: the
  pane as its content, the selected row's details in the Inspector beside it, and nothing else of Activity's that opens a second
  window or a popover of its own. Inventory and what replaces each:

  | Today | What it shows | Replaced by |
  |---|---|---|
  | `Window("Activity Detail", id: detailWindowID)` (`FicheroApp.swift:698`), opened from the run strip (`ProjectRunStrip.swift:277`), the toolbar popover (`ActivityStatusToolbarItem.swift:168`) and `ActivityViewHelpers.swift:274` | the one details view alone | the Inspector's Activity section in the one window, the row selected |
  | `ActivityDetailsView`'s `.sheet(item: $trace)` and `RunTraceView`'s compare sheet and popover | the run's trace, two runs compared | the Inspector's Details and Log disclosures; compare stays a Window › command on two selected rows (open question 4) |
  | the toolbar status item's popover (`ActivityStatusToolbarItem.swift:123`) | the summary and Show | KEPT as the summary (`activity.popover.summary`); its Show reveals the one window |
  | `ProjectRunStrip`'s caps popover | change the caps when stopped at a cap | the failed row's fix button opens Settings › AI (`open-settings`) |
  | the sidebar `.activity` mode's job list (`ActivityJobsView`) | a job list plus details | the pane (`activity.pane.is-a-pane-kind`) |
  | the window's own `ActivityModeButton` copies (window toolbar, details view) | Run Now / Run Automatically | the setting (`activity.automatic.one-place`) |

  Acceptance: the app has one `Window` scene for Activity; `detailWindowID` and every `openWindow` of it are gone; a double-click
  on a row selects it and fills the Inspector. *Tests:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityWindowIsAPaneTests.swift`, the existing `ActivityWindowSelectionStateTests`.
- `activity.automatic.one-place` — **[PARTIAL]** (#6441, decision 21; `activity.pane.run-automatically-is-a-setting` made exact) the
  Automatic and Run Now controls exist in ONE place. Inventory today and after:

  | Today | What it does there | After |
  |---|---|---|
  | `ActivityModeButton` in the toolbar status item (`ActivityStatusToolbarItem.swift:68`): a picker "Run Now" / "Run Automatically" | sets the engine's background mode: `started` runs everything queued now, `automatic` lets the throttle decide | GONE; the status item keeps the pill and the summary popover |
  | `ActivityModeButton` in the Activity window's toolbar (`ActivityMonitorWindow.swift:94`) | the same picker | GONE; the pane shows one line: "Running automatically" / "Automatic work is paused", with **Pause Automatic Work** / **Resume Automatic Work** as its one button |
  | `ActivityModeButton` in the details view (`ActivityDetailsView.swift:159`) | the same picker, a third copy | GONE |
  | Item verbs › Automation › "Run Now" (`FocusedCommandButtons+AutomationVerbs.swift:20`) and Schedule detail's "Run Now" (`ScheduleDetailView.swift:101`) | runs a SCHEDULE or trigger now, not the background mode | KEPT, renamed **Run Schedule Now** so it cannot be read as the mode |
  | Scope menu "Automatic" (`WorkflowBarPolicy+ScopeMenu.swift:145`), pane chrome "Automatic" font (`PaneChromeMenu.swift:103`), magnifier "Automatic" (`MagnifierPanel.swift:34`) | unrelated "automatic" choices (a scope, a font size, a magnifier mode) | KEPT; not the background mode |
  | Settings › General **Run automatically** (to build) and each project's **Run automatically: Use the app's setting / On / Off** | the one switch, one sentence under it | THE ONE PLACE |

  The "run now" sense of the old mode (start everything queued regardless of battery and idle rules) becomes **Run Queued Work
  Now** in the Project › Activity menu and the pane's background line while automatic work is held ("Held: on battery · [Run
  Now]"), acting once, not a mode. Acceptance: `ActivityModeButton` has no mount; the setting exists in both places and the pane's
  line follows it; a schedule's button reads Run Schedule Now. **Built (2026-11-14, app, not compiled):** Settings › General
  › Background Work: the one **Run automatically** toggle with its sentence (`RunAutomaticallyToggle`, on = automatic, off
  = paused, bound to the Mac's store); the details view's and the Activity window's copies of `ActivityModeButton` are gone.
  Then (#6441): the toolbar status item's copy is gone too (the indicator alone stays, `ActivityModeIndicator.swift`), the
  schedule's button reads **Run Schedule Now**, and Project › Activity has **Pause Automatic Work** / **Resume Automatic
  Work**. Not built: the per-project setting, "Run Queued Work Now", the pane's background line beyond the status bar's
  "Automatic work paused". *Tests:*
  `fichero/Tests/Unit/general/Models/RunAutomaticallySettingTests.swift`; the existing `ActivityTableTests` mode tests.

## Build order

### Stage 1 — Activity as a pane

#### Step 1.1 — the pane kind, the sidebar mode re-homed (#6441)
- Behaviours: `activity.pane.is-a-pane-kind`
- Tests: fichero/Tests/Unit/general/Views/Shell/PaneHeadKindSwitcherParityTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneKindTests.swift
- Depends on: none
- Size: M

`PaneKind.activity` with its scope; the kind switcher lists it; the sidebar mode's content becomes the pane; `ActivityJobsView` and the "activity-browser" opening selection deleted.

#### Step 1.2 — the one outline table, versions as siblings (#6441)
- Behaviours: `activity.pane.one-outline-table`, `activity.pane.versions-are-siblings`
- Tests: fichero/Tests/Unit/general/Models/ActivityTableTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneOutlineTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneVersionsTests.swift
- Depends on: 1.1
- Size: M

`ActivityMonitorWindow`'s `Table` moves into the pane; the version level is built from the tree's attempts and the run record in the store, one function.

#### Step 1.3 — Group by Run or by File over the same data (#6441)
- Behaviours: `activity.pane.group-by-run-or-by-file`
- Tests: fichero/Tests/Unit/general/Models/ActivityTableTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneGroupByFileTests.swift
- Depends on: 1.2
- Size: M

The join by document id in the store; the `document_id` filter on the jobs route only if measured too slow.

#### Step 1.4 — the Inspector shows the selected row; the window is the pane plus the Inspector (#6441)
- Behaviours: `activity.pane.inspector-shows-the-selected-row`, `activity.window.is-the-pane-plus-inspector`
- Tests: fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift, ActivityInspectorSectionTests.swift (not yet written), fichero/Tests/Unit/general/Models/ActivityPane/ActivityWindowIsAPaneTests.swift
- Depends on: 1.2
- Size: M

The details view mounted once in the Inspector; the Activity Detail window and `ActivityWindowSelectionState` retired; the window scene becomes a one-leaf pane list.

#### Step 1.5 — history kept and filterable (#6441)
- Behaviours: `activity.pane.history-kept-and-filterable`
- Tests: fichero/Tests/Unit/general/Models/ActivityHistoryGroupTests.swift, fichero-server/tests/unit/api/test_activity_order_live_run_first.py, fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneFiltersTests.swift
- Depends on: 1.3
- Size: M

#### Step 1.6 — Run Automatically a setting; every verb through the command table (#6441)
- Behaviours: `activity.pane.run-automatically-is-a-setting`, `activity.pane.commands-through-the-table`
- Tests: fichero/Tests/Unit/general/Views/Shell/MenuShortcutUniquenessTests.swift, fichero/Tests/Unit/general/Models/RunAutomaticallySettingTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityCommandsTests.swift
- Depends on: 1.4
- Size: M

The command table of `menus-and-commands.md` gains the Activity rows in the same commit; the toolbar mode button goes with the setting's arrival, not before.

#### Step 1.7 — less text, more indicator: one glyph per state, six default columns, the error row, the text budget (#6441)
- Behaviours: `activity.pane.one-glyph-per-state`, `activity.pane.default-columns`, `activity.pane.error-row-shape`, `activity.pane.text-budget`
- Tests: fichero/Tests/Unit/general/Models/ActivityTableTests.swift, fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift, fichero/Tests/Unit/general/Models/ActivityRowSubtitleTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityStateGlyphTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityDefaultColumnsTests.swift, fichero/Tests/Unit/general/Models/ActivityErrorRowTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityTextBudgetTests.swift
- Depends on: 1.2
- Size: M

The glyphs and the budget are on the row model, so the window, the pane and the Inspector's heading all obey them from one place; the fix buttons read the typed refusal's offers and add none.

#### Step 1.8 — the page in view first: a rank on the job row, the pick, the bump of existing waiting jobs in step order, the revert, one glyph (#6442)
- Behaviours: `activity.foreground.rank-on-the-row-and-the-pick`, `activity.foreground.one-glyph-not-words`
- Tests: fichero-server/tests/unit/jobs/test_person_started_work_goes_first_5820.py, fichero/Tests/Unit/general/Models/ActivityTableTests.swift, test_page_in_view_first_6442.py (not yet written), ActivityForegroundGlyphTests.swift (not yet written)
- Depends on: 1.7
- Size: S

The engine half of `activity-and-automatic-work.md` Step 1.14 (#6352), done small: one column, one `ORDER BY`, one UPDATE on the existing waiting rows, the revert and the aging 1.14 already fixes; the foreground report route is 1.14's one addition and this step adds none. Code by the lane after approval; not in the dev build.

### Stage 2 — Nothing starts by itself, one cap, the table that says what ran on what (owner 2026-11-13 night)

The order for the night of 2026-11-13: 2.1, 2.2, 2.3 (with Archive), 2.4, 2.5 (engine); 2.6 (the table) after Stage 1's 1.2 and 1.4.

#### Step 2.1 — the launch starts nothing; the one alert (#6584)
- Behaviours: `activity.launch.nothing-starts-one-alert`, `activity.run.failed-is-never-requeued-by-itself`
- Tests: test_launch_starts_nothing_6584.py (not yet written), test_failed_is_never_requeued_6584.py (not yet written), fichero-server/tests/unit/jobs/test_relaunch_resumes_only_running_work_6584.py, fichero-server/tests/unit/workflows/test_quit_paused_runs_resume_5357.py, ActivityLaunchAlertTests.swift (not yet written)
- Depends on: none
- Size: M

`jobs.resume` pauses instead of requeueing; `resume_quit_paused_runs` is retired; the two routes; `pause_recipe` stays paused when
the step run is gone; the app's alert.

#### Step 2.2 — one cap per kind, back off then pause, load a model once (#6584)
- Behaviours: `activity.limits.one-cap-per-kind-across-everything`, `activity.limits.rate-limit-backs-off-then-pauses`, `activity.limits.load-a-model-once`
- Tests: test_one_cap_per_kind_6584.py (not yet written), test_rate_limit_backs_off_then_pauses_6584.py (not yet written), test_load_a_model_once_6584.py (not yet written), fichero-server/tests/unit/jobs/test_kraken_page_gate_two_at_once.py, fichero-server/tests/unit/jobs/test_throttle.py
- Depends on: none
- Size: L

#### Step 2.3 — delete, pause, stop, continue solid in every state; never repeat done work (#6583, #6584)
- Behaviours: `activity.pane.row-actions-on-the-table`, `activity.pane.automatic-runs-easy-to-delete`, `activity.run.never-repeats-done-work`
- Tests: fichero-server/tests/unit/jobs/test_delete_any_row_6583.py, test_delete_is_undoable_6583.py (not yet written), test_every_state_takes_its_verbs_6583.py (not yet written), test_continue_makes_only_the_missing_calls_6584.py (not yet written), fichero/Tests/Unit/general/Models/ActivityDeleteAnyRowTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityRowActionsTests.swift
- Depends on: 2.1
- Size: M

#### Step 2.4 — errors carry their solution, in the row (#6354)
- Behaviours: `activity.pane.failure-with-its-fix-in-the-row`
- Tests: test_every_failure_kind_has_a_fix_6354.py (not yet written), fichero/Tests/Unit/general/Models/ActivityErrorRowTests.swift
- Depends on: none
- Size: S

#### Step 2.5 — the engine half of the table: ran_on, stages and model on every row; the icon and archive mappings (#6441, #6583)
- Behaviours: `activity.pane.row-says-what-ran-on-what`, `activity.pane.icons-say-source-and-kind`, `activity.pane.archive-old-runs`
- Tests: test_row_says_what_ran_on_what_6441.py (not yet written), ActivityStepTrailTests.swift (not yet written), ActivityRowIconsTests.swift (not yet written), ActivityCostColumnTests.swift (not yet written), fichero/Tests/Unit/general/Models/ActivityPane/ActivityWindowIsAPaneTests.swift, fichero/Tests/Unit/general/Models/RunAutomaticallySettingTests.swift, fichero/Tests/Unit/general/Models/ActivityTableTests.swift
- Depends on: none
- Size: M

#### Step 2.6 — the table half: one flat table, the trail cell, cost, one window, one place for Automatic (#6441)
- Behaviours: `activity.pane.less-is-more-table`, `activity.pane.cost-per-row-and-totals`, `activity.one-window`, `activity.automatic.one-place`, `activity.pane.row-actions-on-the-table`
- Tests: ActivityLessIsMoreTests.swift (not yet written), ActivityStepTrailTests.swift (not yet written), ActivityCostColumnTests.swift (not yet written), fichero/Tests/Unit/general/Models/ActivityPane/ActivityWindowIsAPaneTests.swift, fichero/Tests/Unit/general/Models/RunAutomaticallySettingTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityRowActionsTests.swift, fichero/Tests/Unit/general/Models/ActivityTableTests.swift
- Depends on: 1.2, 1.4, 2.5
- Size: L

## Test matrix

Fixture: two recorded job trees from the engine's route (a recipe run with two steps, one step retried on one page and re-run with another model; a second run touching one of the same pages), the run records behind them, and a pane list with one Activity leaf. Every test above reads these; none drives a live engine.

## Open questions — answered (the review's proposals, accepted by the manager 2026-11-13 night)

1. A FILE row is the document with its page count ("Register 3 · 120 pages"); pages under a disclosure.
2. The `document_id` filter: measure first; the bar is a join over 200 ms on the 100k-page fixture.
3. The automatic kinds at launch are paused like everything; the alert rolls them into one line; Continue All includes them.
4. Compare two runs: dropped; the Inspector's versions section shows the figures side by side.
5. No automatic Continue after a rate limit: the back-off is the automatic retrying; the row's fix is "Wait 2 minutes, then
   Continue", its button enabling when the wait is up.
6. Provider cap: a setting; the default is the network lane's width (4), since a smaller cap held a lane slot while a call
   waited for a provider slot (`test_provider_share.py`).
7. Undo of Delete: yes; `workflow_run.delete` becomes undoable too.
8. `unexpected`: "Something went wrong in Fichero, not in your files." + Try Again + Report Bug; the exception type only in Copy
   Details.

## Open questions — for the owner

9. Auto-archive of finished runs after N days: a setting, default OFF; wanted at all, and N?
