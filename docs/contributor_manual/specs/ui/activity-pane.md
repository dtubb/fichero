# UI — Activity as a pane — Design Spec (#6441)

> Milestone: activity
> Manual: TBD — the "Activity" section must say that Activity is a pane like Library or Reader: it can sit in any window beside the Inspector, be grouped by run or by file, and that Run Automatically is a setting.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-11-08, Fable). A COMPANION of `activity-and-automatic-work.md` (APPROVED 2026-10-27, 2997 lines: the one job model, the window, lanes, durability, automatic work) and of `panes-workspaces.md` (the pane and workspace system). This file holds only the DELTA the owner asked for on 2026-11-08: Activity becomes a PANE KIND; the generic Activity window is that pane plus the existing Inspector; one hierarchical table with disclosure triangles, grouped by run or by file over the same data; several versions of one step as siblings; history kept and filterable; Run Automatically a setting. Everything the big spec already pins (the job model, the one-bar row, the groups, the details view's content, lanes, retries) stays as written there and is cited, not restated. Menu items and chords go through the one command table of `menus-and-commands.md` (#6435).
> Tags: **[OK]** built · **[PARTIAL]** exists in part · **[GAP]** designed, not built · **[BROKEN]** built and wrong.
> **Tag note (2026-11-14):** the app tests of this spec first RAN on 2026-11-14 in Xcode (Dev Local, after batch-19): the 13
> ActivityPane suites plus ActivityLaunchAlert, ActivityStepTrail, ActivityRowIcons, ActivityErrorRow and RunAutomaticallySetting,
> 63 tests, all passed. An **[OK]** means built with a test that has run green.
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
2. **One hierarchical table** with disclosure triangles (made exact 2026-11-14: a row's children are WHAT IT WORKS ON, its files or the rows it blocks; steps are the trail cell, versions the Inspector, `activity.pane.children-are-what-it-works-on`); the Inspector on the right shows the selected row.
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

### Ruled 2026-11-14 afternoon (owner, looking at the Dev Local build; paraphrased; the tab set the manager's call at his request)

22. **The window is Apple's Activity Monitor with an Inspector.** The toolbar carries the verbs and the views; the table is the
    middle; the bottom is for figures and graphs; the Inspector stays on the right.
23. **Four tabs, one table:** **Runs | Files | Cost | Where**. Each answers one question a person asks (what is working and
    what needs me; what happened to my pages; what is it spending in money, tokens and time; where is it running: this Mac,
    another Mac, the cloud, a cluster). The tab picks the grouping and the columns; the rows are the same. Recipes is a filter
    token, not a tab (a run row already names its recipe). The tabs replace decision 4's Group by switch: Runs is By Run, Files
    is By File.
24. **Pause, Continue and Stop are toolbar buttons** in the Activity window AND in a main window while its Activity pane has the
    focus, acting on the selection by the Mail rule; beside them the Inspector toggle.
25. **The bottom panel shows figures and graphs, together**, per tab: Runs, pages per minute and the counts; Cost, spend over
    time and today's by provider and tokens; Where, each place's load. The engine supplies the history (pages and spend per
    minute) from what it already records.
26. **Done is green**, failed red: success reads at a glance.
27. **A log is the raw log**, every line as the engine wrote it, rendered whole and always (never "nothing written" for a row
    that ran); its level filter is the only control. **Errors need answers**: a failure in the row or the Inspector says what
    happened and the fix, never a path or an exception; the raw text is the log's and Copy Details'.
28. **A kept export is ONE row per export**, updated in place ("Update kept export · Export folder · 12 pages"), never one
    per page; its folder gone pauses it with Choose Folder… and nothing more is queued; a per-export switch turns the
    automatic part off.
29. **The row and the Inspector say the same numbers**: one time, one count, one cost, from one source.

### Ruled 2026-11-15 morning (owner, looking at the overnight build; paraphrased; supersedes decisions 23 and 24)

30. **Xcode's run controls, global.** At the FAR LEFT of the Activity window's toolbar, and of every main window's (right of
    its sidebar), ONE **Play/Pause** button that turns into the other, and **Stop** on its own. They act on ALL work on this
    engine, every open project, the same in both windows: Pause pauses everything (a person's runs too); Play continues only
    what that Pause paused; Stop stops everything. A row's own Play/Pause and Stop are in the row (decision 31).
31. **A row's own controls are in the row**: the selected (or hovered) row shows Play/Pause and Stop in its trailing cell; the
    selection's verbs stay in the context menu and Project › Activity. The toolbar holds no selection verbs (supersedes 24).
32. **A sidebar, not tabs** (supersedes 23): the window is a source list on the left, the table in the middle, the Inspector
    on the right, the graph panel at the bottom. The sidebar's items: **Runs**, **Files**, **Recipes**, **Cost**, **Models**
    (supersedes Where) and **Archived**.
33. **Models, by where they run**: the sidebar's Models section is a tree **place › provider › model**: This Mac (Kraken, the
    embedding models, MLX, Ollama…), Remote (another Mac, a cluster: ACENET), Cloud (Anthropic, OpenAI, Hugging Face…). Each
    model's icon says whether it is **loaded** and whether it is **active** (working now). Choosing one lists the work it
    ran or runs.
34. **Graphs on every view, taller**: the bottom panel is on every sidebar item, taller than tonight's, its height the
    person's to drag and kept.
35. **Columns from the header**: a column header's menu picks the columns; their widths and order are remembered. The Metadata
    button goes (it offered fields the rows do not show).
36. **The log is Xcode's**: one line per row of a list (time, level, text, monospaced), lines selectable one or many,
    find-in-log highlighting its matches, Copy copying the selected lines. It is a record: not editable.
37. **Granular, like the node editor, "so we can see what recipes worked"**: the Recipes view lists each recipe (its
    version), its runs under it, each run's steps under that, with per page rates that compare (pages done and failed,
    failed %, seconds a page, cost a page, the model and place of each step); the Inspector of a run shows its graph as the
    node editor draws it, each node with its counts.
38. **Sidebar › centre › Inspector, the main app's shape** (the owner, 2026-11-15 late morning): the sidebar SELECTS (an item,
    a recipe, a model, a provider, a place, a cluster), the centre SHOWS the selection in one of several views, the Inspector
    INSPECTS the selected row. This is right; nothing goes back to tabs.
39. **The centre has views of the selection**, chosen in its head like the main app's panes (Canvas / List / Table):
    **Table** (the rows), **Graph** (charts of the same rows over time) and **Visual** (the selection drawn: a run as its
    node graph with each node's counts, work as a timeline of bars per lane or per model, a cluster as its jobs on a
    timeline). Every sidebar item offers the views that mean something for it.
40. **Activity's views are panes**: the sidebar, the centre and the graphs are built from the app's pane code (the pane head,
    the footer `PaneFilterBar`), so each can open in a main window as a pane as well as in the Activity window.
41. **The graphs are their own pane**: at the bottom of the centre by default, and like any pane it can be made full size.
42. **Show everything the engine knows**, by resource: a model's memory held (its process's resident size; Kraken's readers
    as the engine sizes them), when it loaded, its pages, calls and seconds today; a cluster job's time queued and time run,
    its node hours and cost; this Mac's memory, processor and lanes busy. Nothing guessed: what nothing measures reads "—".

## States and what a person may do in each

One vocabulary for the engine's rows (`jobs.state` plus the reason words it decides), the table's glyph, and the verbs. The
engine owns the transitions; the app shows the state and offers only the verbs the row allows. The set-aside state ("Stopped 3
times by the engine stopping; set aside") is RETIRED: interruptions pause, they never count.

| State | Glyph | Means | Pause | Stop | Continue | Retry | Archive | Delete |
|---|---|---|---|---|---|---|---|---|
| queued | hollow circle | waiting its turn in its lane; nothing holds it | yes | yes | — | — | — | yes |
| waiting for a slot | hollow circle, tooltip says for what | held by a cap (provider, model, memory, battery, thumbnails first) | yes | yes | — | — | — | yes |
| blocked | `lock.circle`, tooltip names the blocker | waiting on something another row or a person must supply first (a model not downloaded or not loadable, a key, a folder); listed UNDER its blocker's row (`activity.pane.blocked-under-its-blocker`); never picked, never retried by itself | yes | yes | — | — | — | yes |
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
- `activity.pane.group-by-run-or-by-file` — **[OK]** (built #6441: the two groupings over the same rows, a selected file kept selected across the switch; #6441, decision 4) (superseded in its control by decision 23: the **Runs** and **Files** tabs of the window's toolbar, a main window's pane its head's lens menu, `activity.window.toolbar-tabs`; the grouping below is unchanged) ONE switch, **Group by: Run | File**, over the SAME data, a new pane opening BY RUN (decision 4, decided) with By File one click away: by Run is the outline above (a row and what it works on, `activity.pane.children-are-what-it-works-on`); by File lists each FILE (page or document) the scope's runs touched, a file row showing what runs on it NOW and expanding to its PATH THROUGH THE STEPS in run order (step › version, each with model, version, result, time, cost, the counting version marked), so a person reads a page's whole history in one place; the switch is per pane, remembered, and the selection survives it (the selected page stays selected in the other grouping); the data is the run trees and per-page states the store already holds (`loadRunTree`, `GET /api/activity/jobs/{id}/pages`) joined by document id in the app; for history older than the loaded trees the pane reads the runs that touched a file through `GET /api/activity/jobs` with a `document_id` filter — the ONE provisional contract point of this spec, one query parameter on an existing route, added only if the app-side join is too slow on a 100k-page library. Acceptance: Group by File on a project with two runs shows a page with two steps and, under the read step, the two versions with their models; switching back to Run keeps that page selected. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneGroupByFileTests.swift`, the existing `ActivityTableTests.swift`.
- `activity.pane.inspector-shows-the-selected-row` — **[PARTIAL]** (built #6441: `ActivityInspectorSection` in both Inspectors; not built: ActivityInspectorSectionTests.swift; #6441, decision 2; `activity.details.one-view`, #5561) the EXISTING Inspector column shows the selected row in an **Activity** section that IS the one details view (`ActivityDetailsView`: heading, state and why, stage bar and page grid for a run, pages done and failed with Read Again, what it made, details and log disclosures, resources, actions), mounted there and nowhere else: the Activity Detail window (`FicheroApp.swift:694`) and the details' mounts inside the window and the sidebar mode go; selecting a run, a step, a version or a file shows its details; with nothing selected the section shows nothing (`activity.window.no-empty-prose`); in a main window the Inspector shows the Activity section while the Activity pane holds the focus (the last pane clicked) and a row is selected, and the document's sections again once another pane takes the focus; the Inspector's other sections stay for a selected page (so a file row's Inspector shows the page's own sections too). Acceptance: selecting a version row shows its heading, model and pages in the Inspector; selecting nothing shows an empty section; no Activity Detail window exists. *Test:* `ActivityInspectorSectionTests.swift` (not yet written; the section per row kind, the empty state), the existing `ActivityDetailsTests.swift`.
- `activity.window.is-the-pane-plus-inspector` — **[OK]** (built #6441: one window, the pane plus `.inspector`; the popover's Show and Open Activity focus an Activity pane already in the window, else open the window; #6441, decision 1) the generic Activity window (Window › Activity, ⌥⌘0 kept in the command table) is ONE Activity pane plus the Inspector column, built from the pane kind with a `PaneList` of one leaf, not a view tree of its own: `ActivityMonitorWindow`'s body becomes the pane; its selection is the window's ONE selection: the Activity window is a single `Window` scene, so its selection is the one `ActivityWindowSelectionState` (Show in Activity writes it, then opens the window), while an Activity pane in a main window writes that window's `WindowState.activityPick`, which the main window's Inspector reads; the toolbar status item's popover stays the summary (`activity.popover.summary`) and its Show opens this window or reveals an Activity pane already in the front window. Acceptance: the window's view tree is a pane list with one Activity leaf and the Inspector; Show in the popover brings the pane forward. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityWindowIsAPaneTests.swift`.
- `activity.pane.history-kept-and-filterable` — **[OK]** (built #6441: one filter field, the tokens kept per pane; #6441, decision 5; `activity.window.history-group`, `activity.run.record-keeps-all-history`) history is KEPT (every ended run, of any kind, in the same flat table after the live rows, as the engine's `group: "earlier"` already marks it; no History section row; Archive Finished… and Archive Failed hide it, `activity.pane.archive-old-runs`) and FILTERABLE through one filter field in the pane header that takes tokens as Finder's search does — recipe, step, model, state, date (a day or a range), file, started by — combined with AND (typed as `key: value`, the value matched case-insensitively as a substring of the row's name, step trail, model, state words, file names or starter; `date:` takes `today`, `YYYY-MM-DD` or `YYYY-MM-DD..YYYY-MM-DD` against the row's start; text with no key matches the name; an unknown key is plain text), applied to both groupings, per pane and remembered; the engine's existing filters serve what they can (`GET /api/activity`'s `types`, `since`, `until`, `search`; the job list's kinds) and the rest is filtered in the app over the loaded trees; a filter that hides everything says "No activity matches" in one line. Acceptance: the token "model: Kraken" with "state: failed" shows the one failed Kraken version and its page; clearing the tokens shows everything; the tokens survive a relaunch. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneFiltersTests.swift`, the existing `ActivityHistoryGroupTests.swift` and `test_activity_order_live_run_first.py`.
- `activity.pane.run-automatically-is-a-setting` — **[GAP]** **[SUPERSEDED]** by `activity.pane.automatic-work-setting-and-row-verbs` (owner rulings 2026-11-14 afternoon) (#6441, owner ruling; `activity.window.background-group`, `activity.recipe.declares-automatic`) **Run Automatically** is a SETTING, not a toolbar mode: in Settings › General a plain label **Run automatically** with one sentence under it ("Fichero processes new and changed pages in the background: thumbnails, text, names and search."), and the same in each project's settings with "Use the app's setting" as its default (the project's answer wins when set); the toolbar's `ActivityModeButton` goes. The pane only SHOWS the state as one line at the top of its background section ("Running automatically" or "Automatic work is paused") and offers the two verbs there and in the command table, worded so that neither can be read as the other: **Pause Automatic Work** / **Resume Automatic Work** for the background lane, **Pause Run** / **Resume Run** / **Stop Run** on a run row (the one button's titles, `activity.window.one-button`), never a bare "Pause" or "Run" anywhere in Activity. Acceptance: turning the setting off in Settings shows "Automatic work is paused" in every Activity pane and no background row starts; the run row's button reads "Pause Run"; the background line's reads "Pause Automatic Work". *Test:* `RunAutomaticallySettingTests.swift` (not yet written; the setting read by the pane, the project override, the two wordings), the existing `ActivityWindowGroupsTests.swift`.
- `activity.pane.automatic-work-setting-and-row-verbs` — **[PARTIAL]** (built #6441: Settings › General's switch, "Automatic work paused" in the status bar, Project › Activity's Pause / Resume Automatic Work, the toolbar's `ActivityModeButton` gone; not built: the project's own setting; #6441, owner ruling; `activity.window.background-group`, `activity.recipe.declares-automatic`) **Run Automatically** is a SETTING, not a toolbar mode: in Settings › General a plain label **Run automatically** with one sentence under it ("Fichero processes new and changed pages in the background: thumbnails, text, names and search."), and the same in each project's settings with "Use the app's setting" as its default (the project's answer wins when set); the toolbar's `ActivityModeButton` goes. The pane has no section rows (`activity.pane.less-is-more-table`), so it SHOWS the state only as the last item of its one status bar while automatic work is paused ("Automatic work paused"; nothing while it runs) and offers the two verbs in the command table, worded so that neither can be read as the other: **Pause Automatic Work** / **Resume Automatic Work** for the background lane; a row's verbs are the one verb list's (**Pause**, **Continue**, **Stop**, **Retry**), whose help and accessibility label name the row ("Pause Letters"). Acceptance: turning the setting off in Settings shows "Automatic work is paused" in every Activity pane and no background row starts; a running row's button reads Pause and a paused one's Continue (never Resume); the command reads "Pause Automatic Work". *Test:* `fichero/Tests/Unit/general/Models/RunAutomaticallySettingTests.swift`. Supersedes `activity.pane.run-automatically-is-a-setting`.
- `activity.pane.commands-through-the-table` — **[PARTIAL]** (built #6441: the verbs in Project › Activity through the focused pane, Pause / Resume Automatic Work, Show in Activity in a page's context menu and File menu, View › Activity ▸; not built: Copy Link, which waits on `profile.links.one-link-two-forms` (#6439); #6441; `menus.one-command-table`, `menus.chords-are-standard-mac`, #6435) every Activity verb lives in the one command table and acts on the pane's selection wherever the pane is: Window › Activity (⌥⌘0, kept); Project › Activity › Stop, Read Again (as built, `menus.project.activity-stop-read-again`, now on the pane's focused selection); Pause / Continue, Retry, Archive, Put Back, Delete, Pause Automatic Work / Resume Automatic Work, **Show in Activity** (from a page or folder's context menu: reveals the file's row in Group by File), **Group by Run** / **Group by File** and **Show Archived** (View › Activity ▸, no chord), Archive Finished…, Archive Failed, Copy Link (the row's deep link, `profile.links.one-link-two-forms`); each appears in the menu bar, the pane's context menu and the Inspector's actions from the one definition; no new chord (the uniqueness test is the judge). Acceptance: the command table lists each verb once with its surfaces; Show in Activity on a page reveals its file row; the uniqueness test passes unchanged. *Test:* the existing `MenuShortcutUniquenessTests.swift`; `fichero/Tests/Unit/general/Models/ActivityPane/ActivityCommandsTests.swift`.
- `activity.pane.one-glyph-per-state` — **[OK]** (built #6441: `ActivityPane.glyph`; #6441, decision 8) every row's STATE is ONE glyph, the system's where one exists, never a word beside it: waiting a hollow circle, running the indeterminate spinner (`ProgressView` circular, the Mac's), done a GREEN check in a filled circle (decision 26), failed a RED X in a filled circle, paused the pause glyph, stopped the stop glyph, skipped a dash; the glyph carries the state's name as its accessibility label and tooltip, so the word exists for VoiceOver and hover only; no timestamp is written as text where a glyph or a bar says it (a running row shows its spinner and its trail, or "12 of 40" when it has no stages, not "started 14:02"; a done row shows its check and ONE time, the duration or the finish time by the column's choice, never both; "about 12 min left" stays, as the one time of a running row). Acceptance: a row in each of the seven states shows the glyph and no state word; a running row has no timestamp text; VoiceOver reads "running" on the spinner. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityStateGlyphTests.swift`, the existing `ActivityTableTests.swift`.
- `activity.pane.default-columns` — **[OK]** (built #6441: six on, four in the header menu, kept per pane; #6441, decision 8; REVISED by the review: Cost ON, the owner asked twice) the table's columns and their defaults are the one column table above (source glyph, name, state, trail, time, cost on; model, started by, started, kind glyph off, and the Cost and Where tabs' tokens, to finish, runs on, lane), each a plain toggle in the header's menu (right-click, as every Mac table), remembered per pane; the Inspector shows every fact for the selected row, so nothing is lost by hiding a column. Acceptance: a fresh pane has the six default columns; turning Model on in the header menu adds it and survives a relaunch; the Inspector shows the model whether the column is on or off; the Steps cell counts only work of more than one item, never "0 of 1" or "1 of 1" (the state glyph says it; #6588, 2026-11-14 night). *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityDefaultColumnsTests.swift`, the existing `ActivityTableTests.swift`.
- `activity.pane.error-row-shape` — **[PARTIAL]** (built #6441: the red X, the one line, the one fix button, pages failing for one reason said once with their count; not built: Download (the fix button opens Settings); #6441, decision 8; `runtime.errors-are-typed`, `designer.budget.refusal-offers-the-fix`, `source.recipe.check-names-every-fault`) a failed row is a RED X, ONE SHORT LINE (the typed refusal's sentence, cut to the text budget: "Qwen 2 VL is not downloaded", "No key for OpenRouter", "Page image unreadable"), and the FIX the refusal itself offers as the row's ONE button (its primary action; the other offers — Download, Add Key…, Read Again, Use Next Candidate, Skip Page, the offers the engine's typed errors and the recipe check already carry, never invented in the view — in the context menu and the Inspector), with the full reason, the log and the stack a disclosure in the Inspector on demand; several failed pages under one step collapse to one line with the count and one set of fix buttons when their refusal is the same. Acceptance: a step whose model is missing shows the red X, the one line and Download; a run with twelve pages failing for the same reason shows one error line with "12 pages" and Read Again; the Inspector has the full text. *Test:* `fichero/Tests/Unit/general/Models/ActivityErrorRowTests.swift`, the existing `ActivityDetailsTests.swift`.
- `activity.pane.text-budget` — **[OK]** (built #6441: every cell held to eight words, no sentence; #6441, decision 8; the app-wide rule `menus.less-text-more-indicator`) a row is a LINE, never a paragraph: a word is a whitespace token; the NAME cell is exempt (a file's or recipe's name is cut with a middle ellipsis, as Finder does); a state line at most EIGHT words ("7 of 20 pages · about 12 min left"), an error line at most EIGHT words, no cell holds a sentence (no full stop inside a row), counts as figures with units ("3 pages", "2.1 MB", "$0.04"), no "Currently", "Successfully", "Please"; anything longer belongs in the Inspector. The budget is a test over the row model's strings, not a guideline. Acceptance: every row the fixture trees produce passes the word counts and holds no full stop; a failure's row words are the kind's own ≤ 8-word column (`run.fail.kinds-table`), never a sentence cut at a word boundary; the full sentence is in the Inspector. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityTextBudgetTests.swift`, the existing `ActivityRowSubtitleTests.swift`.
- `activity.foreground.rank-on-the-row-and-the-pick` — **[GAP]** (#6442; the engine half of `activity-and-automatic-work.md` Step 1.14, #6352, made concrete: `activity.foreground.open-jumps-the-queue`, `.order-is-the-views`, `.drops-back-when-moved-on`, `.background-never-starved`) the page IN VIEW is processed first. Facts read in the engine (not run): the one job model has no queue rank; the waiting reads order by `created_at` (`execution/jobs.py` 1149, 1348, 2523, 2769), FIFO apart from the `watched` flag (`activity.throttle.watched-first`: first in its lane, utility QoS, `jobs.watched`); `priority` in `execution/throttle.py` is the COMPUTE priority of a job once it runs, not its place in the queue; `enqueue` (jobs.py 1298) has `run_after` and `watched` but no rank, and REUSES a job of the same kind and subject already waiting. The ONE engine addition, the same one Step 1.14 names: `foreground_rank INTEGER DEFAULT 0` on the jobs row (an `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, as `watched` was added), the lane's pick `ORDER BY foreground_rank DESC, watched DESC, created_at`, and the bump an UPDATE of the EXISTING waiting jobs of the page in view — never a new row, never a re-run of done work (a done job is reused as today) — ranked in STEP ORDER so the page's pipeline completes in sequence: the thumbnail and working rendition, then Find Regions, Find Lines, the Reader (the pipeline order `KINDS` declares; the page in view highest, then its neighbours as 1.14's view order says). The rank is REVERTED to 0 when the person moves on (the client's next set replaces it) or when the set EXPIRES (1.14's 90 s without a heartbeat), and it never starves the rest (1.14's one pick in four and the five-minute age). The app tells the engine the page in view through the one report Step 1.14 defines (`PUT /api/activity/foreground`, the Preview, the browser and the Activity selection feeding one reporter, 300 ms settle, 30 s heartbeat): no such event exists today (checked: no view, focus or foreground route in `api/routes`), so that one route is the only API, and it is 1.14's, not a second one. Acceptance: page 23 opened in the Preview with its Find Lines and reading waiting: both rows get a rank above 0 with Find Lines ahead of the reading, the lane's next pick is Find Lines for page 23, and the row already done for the page is not touched; the person opens page 60: page 23's waiting rows return to 0 on the same call; a bulk run behind it still advances one pick in four. *Test:* `test_page_in_view_first_6442.py` (not yet written; the column, the pick order, the UPDATE of existing rows in step order, no new row, the revert, the aging), the existing `test_person_started_work_goes_first_5820.py`.
- `activity.foreground.one-glyph-not-words` — **[GAP]** (#6442, decision 8; supersedes, for the pane, the wording of `activity.foreground.shown-in-activity`) the Activity pane shows the jump with ONE INDICATOR and no sentence: a bumped waiting row carries the "in view" glyph (an eye, `eye.fill`) beside its state glyph and moves up to its pick place in the lane's order; the tooltip and the accessibility label carry the words ("Next: the page in view"); the status bar counts it in figures ("3 for the page in view · 212 more"), within the text budget; a row that dropped back loses the glyph and nothing else changes. Acceptance: with page 23 in view its two waiting rows show the eye and sit first in their lanes; moving to page 60 moves the eye; no row text changes. *Test:* `ActivityForegroundGlyphTests.swift` (not yet written; the glyph on bumped rows, the order, the summary figures), the existing `ActivityTableTests.swift`.

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
  synced folder" (the review's answers, 2026-11-14). Choose… opens Activity with the stopped rows selected
  (`ActivityWindowSelectionState.revealAll`, 2026-11-14 night). Not built: the folder's name on the new-material line.
  **Ruled 2026-11-14 evening (owner, looking at the alert):** a FOURTH button, **Delete All** (destructive, last): every
  listed row deleted through the one `job.delete`, one step on the window's stack, so Edit › Undo puts them back paused. With
  no run among the rows the title says what was stopped ("Background work was stopped when Fichero quit"), never "0 runs",
  and the line drops its "and". **Built the same evening** (`StoppedAtQuitAlert.deleteAll`, the title by kind); *test:*
  `ActivityLaunchAlertTests` (the title and the line; Delete All's step since 2026-11-14 night). Seen in the Dev Local
  build at a relaunch: the alert showed, nothing was picked (2 embeds, 2 thumbnails held). **Fixed 2026-11-14 night:** the
  SwiftUI alert showed only three buttons on the Mac and dropped Delete All (its sheet held Leave Paused, Choose…, Continue
  All); on the Mac the alert is now an `NSAlert` sheet with the four answers of `StoppedAtQuitAlert.Choice` in order, Delete
  All destructive (`ActivityLaunchAlertTests.fourAnswers`, `chooseOpensActivity`). Picture at a real relaunch after a Kraken
  run was stopped by the quit: `docs/assets/activity-pane/launch-alert.png`. Delete All went to NO undo stack: the alert
  is mounted above the window's environment, where no `WindowSteps` is injected; it now takes the front window's steps
  (`ActivityLaunchAlertTests.deleteAllIsUndoable`). Real round trip the same night: Kraken run on 60 pages → quit → engine
  restart → the run `paused`, nothing picked → Delete All → the run gone → Undo ("Delete Row", the Debug verb `undo step`
  because the screen was locked) → the run back `paused`, "Paused: the app quit" with Continue
  (`docs/assets/activity-pane/pane-paused-at-quit.png`).
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
  "waiting for a slot: 3 of 3 OpenRouter calls in flight"; the status bar counts "N running · M waiting". Acceptance:
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
- `activity.pane.icons-say-source-and-kind` — **[PARTIAL]** (#6441, decision 12) ONE narrow icon column, the SOURCE glyph (the KIND glyph is the optional Kind column, off by default; made exact 2026-11-14):
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
- `activity.pane.cost-per-row-and-totals` — **[PARTIAL]** (#6598, #6441, decision 20; `activity.window.cost-column` built the per-node
  `cost_usd`; `ai/cloud-permission-and-spend.md` keeps the records) the Cost column (on by default, `activity.pane.default-columns`;
  shown in the Inspector always) shows per row the dollars SPENT so far and, while running, the ESTIMATE to finish ("$0.42 · ~$1.10
  more", from the plan's per-page estimate times the pages left, `spend.caps_now`'s basis); the run row totals its steps; the
  status bar totals the day's spend ("$3.20 today"; per provider in its tooltip); local work shows no cost and its time
  instead; "Not priced" when a call has no price, never "$0". Acceptance: the fixture run with two cloud steps and one local step
  shows the two costs, the run's total, no cost on the local step, and the estimate falls as pages finish. **Built
  (2026-11-14, engine):** every list row carries `cost_usd` (a recipe run's cloud dollars so far, `live_stages.cost_so_far`;
  null for local work or no priced call, never 0) and `cost_estimate_usd` (the running stage's spent-per-page times its pages
  left, `_cost_estimate`; null when ended or nothing priced yet); then (917678a6f, #6598) every job row of its own carries
  its priced cloud calls (`_job_cost`) and a call priced at $0 reads 0.0, not null. Not built: the day total (a contract field),
  "Not priced" apart from local (a contract field); the plan's per-page estimate as the basis before
  the first page is priced; the per-provider daily total line; the app's column. *Tests:*
  `fichero-server/tests/unit/jobs/test_row_says_what_ran_on_what_6441.py`; the existing
  `fichero-server/tests/unit/jobs/test_run_tree_rolls_up.py`;
  not yet written: ActivityCostColumnTests.swift.
- `activity.pane.row-actions-on-the-table` — **[GAP]** **[SUPERSEDED]** by `activity.pane.row-actions-mail-rule` (owner rulings 2026-11-14 afternoon) (#6441, #6583, decision 11; `activity.window.delete-any-row`,
  `activity.pause.per-job`, `activity.retry.one-row`) the verbs live on the table: a row's one button (`activity.window.one-button`)
  shows the verb its state allows (the states table above), the context menu lists the one verb list, each enabled by the MAIL RULE (above: enabled when any selected row allows it,
  applied to those, the rest skipped and counted in the status bar), the Delete key and ⌘⌫ delete the selection, ⌘A selects all
  shown, and Edit › Undo undoes a Delete or an Archive (the engine's `job.delete`, `job.archive` and `workflow_run.delete` are
  undoable: the row comes back in the state it had); Delete on a running row is Stop then Delete after one confirmation; a row that
  ended between the click and the request is judged by the engine at receipt and answered skipped, and the app re-reads. Acceptance:
  with a failed, a paused and a running row selected the menu enables Delete, Stop and Continue (the paused one allows it) and
  disables Pause; ⌘⌫ asks once for the running one, deletes all three, and the status bar counts them; Undo lists them again in
  their former states. The states table above is this behaviour's fixture. *Tests:*
  `fichero/Tests/Unit/general/Models/ActivityDeleteAnyRowTests.swift`, `fichero-server/tests/unit/jobs/test_delete_any_row_6583.py`,
  `fichero-server/tests/unit/jobs/test_every_state_takes_its_verbs_6583.py` (built 2026-11-13 night: the engine's verbs in every
  state of the table above, through the routes; the table is its fixture);
  not yet written: ActivityRowActionsTests.swift, test_delete_is_undoable_6583.py.
- `activity.pane.row-actions-mail-rule` — **[PARTIAL]** (built #6441: the one verb list by the Mail rule, published by the focused table; Stop then Delete after one confirmation, a running run stopped first; Delete, Archive and Put Back of jobs are the audited actions, one step on the window's stack, so Edit › Undo takes them back; a run row's Archive is the engine's `workflow_run.archive` (nothing deleted; Undo and Put Back are `job.unarchive`), test `fichero-server/tests/unit/jobs/test_archive_runs_6441.py`; not built: Undo of a run's delete (the engine's `workflow_run.delete` is not undoable); #6441, #6583, decision 11; `activity.window.delete-any-row`,
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
  not yet written: test_delete_is_undoable_6583.py. Supersedes `activity.pane.row-actions-on-the-table`.
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
  `activity.pane.error-row-shape`) a failed row shows IN THE TABLE a red X, its kind's ROW WORDS (at most eight, `activity.pane.text-budget`) and the FIX as a
  button with its word (never an icon alone); the ONE plain sentence of what happened is the Inspector's (the examples below are those sentences): "Out of credit on OpenRouter. [Add credit]", "OpenRouter is limiting how fast you
  can send. [Continue] (enabled when the wait is up)", "Qwen 2 VL is not downloaded. [Download]", "2 GB of disk needed. [Free up
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
  style ("3 running · 12 waiting · $3.20 today"; the automatic state lives in Settings and Project › Activity; the status bar's last item says "Automatic work paused" only while it is); progress is
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
  | `ActivityDetailsView`'s `.sheet(item: $trace)` and `RunTraceView`'s compare sheet and popover | the run's trace, two runs compared | the Inspector's Details and Log disclosures; compare is dropped, the Inspector's versions side by side (open question 4, the owner 2026-11-14) |
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
  | `ActivityModeButton` in the Activity window's toolbar (`ActivityMonitorWindow.swift:94`) | the same picker | GONE; the status bar says "Automatic work paused" while it is (nothing while it runs); **Pause Automatic Work** / **Resume Automatic Work** are in Project › Activity, not a button in the pane |
  | `ActivityModeButton` in the details view (`ActivityDetailsView.swift:159`) | the same picker, a third copy | GONE |
  | Item verbs › Automation › "Run Now" (`FocusedCommandButtons+AutomationVerbs.swift:20`) and Schedule detail's "Run Now" (`ScheduleDetailView.swift:101`) | runs a SCHEDULE or trigger now, not the background mode | KEPT, renamed **Run Schedule Now** so it cannot be read as the mode |
  | Scope menu "Automatic" (`WorkflowBarPolicy+ScopeMenu.swift:145`), pane chrome "Automatic" font (`PaneChromeMenu.swift:103`), magnifier "Automatic" (`MagnifierPanel.swift:34`) | unrelated "automatic" choices (a scope, a font size, a magnifier mode) | KEPT; not the background mode |
  | Settings › General **Run automatically** (to build) and each project's **Run automatically: Use the app's setting / On / Off** | the one switch, one sentence under it | THE ONE PLACE |

  The "run now" sense of the old mode (start everything queued regardless of battery and idle rules) becomes **Run Queued Work
  Now** in the Project › Activity menu and the status bar's last item while automatic work is held ("Held: on battery"), acting once, not a mode. Acceptance: `ActivityModeButton` has no mount; the setting exists in both places and the pane's
  line follows it; a schedule's button reads Run Schedule Now. **Built (2026-11-14, app, not compiled):** Settings › General
  › Background Work: the one **Run automatically** toggle with its sentence (`RunAutomaticallyToggle`, on = automatic, off
  = paused, bound to the Mac's store); the details view's and the Activity window's copies of `ActivityModeButton` are gone.
  Then (#6441): the toolbar status item's copy is gone too (the indicator alone stays, `ActivityModeIndicator.swift`), the
  schedule's button reads **Run Schedule Now**, and Project › Activity has **Pause Automatic Work** / **Resume Automatic
  Work**. Not built: the per-project setting, "Run Queued Work Now", the pane's background line beyond the status bar's
  "Automatic work paused". *Tests:*
  `fichero/Tests/Unit/general/Models/RunAutomaticallySettingTests.swift`; the existing `ActivityTableTests` mode tests.

### Ruled 2026-11-14 (owner, testing the 2026.11.14 release): a simple table that shows blockers, downloads that work

What the release showed: a download of bge-m3 read "Running · 0 of 1" for minutes with no movement; it then FAILED to load
(onnxruntime 1.29 refused `model.onnx_data` because huggingface_hub 1.33's sharded blob store put it in another folder than
`model.onnx`) while Settings › AI › Downloads showed bge-m3 with a green check and 4.58 GB (the file is 2.27 GB); "Processing
imported pages · 11 of 2618" and "Embed for search" kept being listed as waiting for "the search model … being fetched", a long
sentence on four rows, after the fetch had failed; two rows showed raw text (the ONNX error; "Connection already closed: the
library …/fichero.duckdb was closed"). The owner restated the goal: a much simpler table, hierarchical, that shows what is
working, on which files, and what blocks it; the engine smarter about work that cannot run; models that download.

- `activity.pane.blocked-under-its-blocker` — **[GAP]** (#6593, #6588; the `blocked` state in the states table) work that cannot run
  until something else exists is BLOCKED, not waiting: the engine records on the row WHAT blocks it (`blocked_by`: another job's
  id, or a typed need — a model `runtime:model`, a key for a provider, a folder) and the lane never picks a blocked row, so it
  does not spin, re-check or re-queue. The table shows ONE row for the blocker (the download, or a need row "Search model bge-m3
  · not loadable" when no job supplies it) and the blocked work as its CHILDREN under a disclosure, each with the `lock.circle`
  glyph and no sentence ("Embed for search · 2,618 pages", "Prepare pages · Letters · 2,618"); the blocker's words are said once,
  on the blocker. When the blocker ENDS done, its children become queued by themselves (that is the engine finishing what it
  was asked, not a restart); when it ends FAILED, the children stay blocked and the blocker's row carries the fix (Download Again,
  Choose Another Model…, Add Key…), and the person's fix unblocks them. Acceptance: with the search model missing, an import
  queues its embeds blocked on the download; the lane picks none of them; the table has one download row with the embed rows
  under it; the download fails: the embeds stay blocked, zero model calls, the row offers Download Again; it succeeds: the
  embeds run. *Test:* not yet written: `test_blocked_work_waits_on_its_blocker_6588.py`, `ActivityBlockedRowsTests.swift`.
- `activity.download.says-bytes-and-time-left` — **[PARTIAL]** (built a6ab0bc7c: every runtime's bytes in the row's words and its detail, a folder watcher where the library has no callback; not built: the typed fields on the listed row (a contract change), the time left; #6592, #6588; supersedes "0 of 1" for a download) every model download, of
  every runtime (Kraken, MLX, embeddings, Whisper, spaCy, YOLO, the MLX runtime), reports its bytes at least every
  `PROGRESS_EVERY_SECONDS` (2) as typed fields on the row (`bytes_done`, `bytes_total`, never only words): through the library's
  callback where it has one, else by measuring the model's download folder as it grows against the catalogue's size. The row's
  bar is determinate on bytes and its one line reads "340 MB of 2.3 GB · 3 min left" (the text budget); before the first byte,
  the spinner and "Connecting"; a stall of `READ_TIMEOUT_SECONDS` says "No data for 20 s, trying again". Acceptance: a stub
  fetch for each runtime that writes 10 chunks reports at least 5 rising `bytes_done` values and the total; the row never reads
  "0 of 1". *Test:* `fichero-server/tests/unit/llm/test_every_download_reports_bytes_6592.py`.
- `activity.download.installed-means-it-loads` — **[PARTIAL]** (built a7ca0859c, 5a3a66b63: one real folder, a load check before installed, `broken` with a marker, the size counted once; not built: Settings' red X and Download Again, an old-layout model that does not load reads installed until deleted; #6591, #6588; `runtime.spacy.pipelines-download-as-data`) a model is
  INSTALLED only once it LOADS: the download job ends by loading the model once (or the runtime's own check) and only then
  says `model.installed`; a model whose files are present but which does not load is `broken`, shown in Settings with the red X,
  one line ("bge-m3 could not be loaded") and **Download Again** (delete, fetch, check), never the green check; Settings' size
  is the bytes on disk counted once (a link and its blob are one file). The engine fetches every model into ONE real folder
  (`snapshot_download(local_dir=…)`, plain files) and loads it from there (fastembed's `specific_model_path`), so no loader's
  path check depends on the cache's layout. Acceptance: a fixture snapshot whose `model.onnx` and `model.onnx_data` resolve to
  different folders loads after the fix; a model whose load raises reads `broken` in `GET /api/models` and in Settings, never
  installed; bge-m3's size reads 2.3 GB. *Test:* `fichero-server/tests/unit/llm/test_model_installed_means_it_loads_6591.py`.
- `activity.pane.names-what-it-works-on` — **[GAP]** (#6588; `activity.pane.row-says-what-ran-on-what` made exact for jobs of
  their own) a row names what it works on, never only its kind: "Prepare pages · Letters · 2,618" (the folder or project and the
  count), not "Processing imported pages · 11 of 2618"; its children are the steps it holds (thumbnails, text, embed), each
  with its own count, and under a step the files it is on NOW (at most the in-flight ones, named), so "which files" is one
  disclosure away; an import's derivative work for one folder is ONE row, never one per step at the top level. Acceptance: an
  import of a folder of 2,618 images lists one top-level row naming the folder and the count, three step children, and under
  the running step the files in flight by name. *Test:* not yet written: `ActivityNamesWhatItWorksOnTests.swift`, the engine's
  `test_row_says_what_ran_on_what_6441.py` extended.
- `activity.failure.no-raw-text-ever` — **[GAP]** (#6597, #6588, #6354; `activity.pane.failure-with-its-fix-in-the-row`) the failure
  table gains the kinds the release showed bare: a model that will not load (`model-broken`: "bge-m3 could not be loaded" ·
  Download Again), a library closed under a running job (`library-closed`: the job is not failed but PAUSED, "Paused: the
  project closed", Continue on reopen), a kept export whose folder is gone ("The export folder is gone" · Choose Folder…). A row,
  alert or Settings line never shows an exception name, an absolute path or an engine message; those live in Copy Details.
  Acceptance: the three stub failures list with those words and fixes, none containing `Error`, `/Users/` or `[`. *Test:*
  `fichero-server/tests/unit/llm/test_every_failure_kind_has_a_fix_6354.py` extended.

### Made exact 2026-11-14 (the spec review; the owner's open calls taken at the manager's recommendation, his to overturn)

The wireframe (revised 2026-11-14 afternoon, decisions 22-29: Activity Monitor's toolbar and bottom panel, the Inspector on
the right; the same pane in a main window keeps the table and drops Time, Cost and the trail first as it narrows):

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ●●●  Activity      ⏸ ▶ ⏹   ⋯▾     [ Runs │ Files │ Cost │ Where ]                                        [◫]  │
├────────────────────────────────────────────────────────────────────────────────┬───────────────────────────────┤
│    Name                            State                      Steps        Time │ ✗ Download bge-m3             │
│ ▾⚙ Download bge-m3                 ✗ Can't load [Download Again]          3 min │   Search model · automatic    │
│     🔒 Embed for search · 2,618     🔒                                          │ bge-m3 downloaded but could   │
│     🔒 Find text · Letters · 2,618  🔒                                          │ not be loaded.                │
│ ▸⚙ Update kept export · Export     ⏸ Folder is gone [Choose Folder…]           │ [Download Again] [Use e5]     │
│ ▸⚙ Thumbnails · Diary 1912 · 14    ⏸ Stopped at quit [Continue]                │ Holds 2 rows · 2,618 pages    │
│ ▾⚙ Prepare pages · Letters · 2,618 ◌     Thumbs ✓ → Text ▶ 11/2,618        ~2 h │ ▸ Details                     │
│     ◌ IMG_0412.jpg                  ◌                                           │ ▾ Log  (raw, every line)      │
│ ▸👤 Read diaries · Register 3 · 120 ◌     Import ✓ → Read ▶ 34/120          12 m │ 14:00:14 info  Started bge-m3 │
│ ▸👤 Find names · Diary 1912 · 40    ✓(green)  Done                         14 m │ 14:00:15 info  Fetching …     │
├────────────────────────────────────────────────────────────────────────────────┴───────────────────────────────┤
│ RUNS  ▁▂▅▇▆▃ pages/min (last hour)   │ 2 running · 3 waiting · 2 blocked · 2 need you │ $0.50 today            │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ☰ Metadata ▾   (≡▾ Filter: state: failed               ⊗)                                                     │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
  Cost tab's panel:  ▁▃▅ spend/hour │ today $0.50 · OpenRouter $0.42 · Gemini $0.08 │ 12,400 tokens
  Where tab's panel: This Mac ▇▇▇░ 3 of 4 lanes │ Other Mac — │ Cloud 2 calls in flight │ Cluster —
```

- `activity.pane.children-are-what-it-works-on` — **[PARTIAL]** (#6599, #6588; supersedes the "recipe › step › version ›
  items" readings of decision 2 and `activity.pane.group-by-run-or-by-file`; built: a run's FILES, `ActivityPane.files(of:)`;
  a job of its own's files in flight, by name, 2026-11-14 night: `ActivityPane.withQueuedFiles` over the queued items the engine
  names (`QueuedItem.name`, `test_queued_items_named_6599.py`; `ActivityPaneOutlineTests.queueOpensToItsFilesInFlight`);
  not built: a finished job's failed files, a blocker's rows) a row's disclosure holds WHAT IT WORKS ON and nothing else: a run's or
  a job's FILES (a job of its own — thumbnails, text, embed — lists the files in flight now, at most the lane's width, by name;
  a finished one its failed files), or the rows a BLOCKER holds (`activity.pane.blocked-under-its-blocker`). Steps are the
  trail cell, versions the Inspector; there is no third level. By File, a file's children are the runs that touched it.
  Acceptance: a thumbnails job over 14 pages with two in flight opens to those two file rows; a run opens to its documents;
  no row has a step child. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneOutlineTests.swift` extended.
- `activity.pane.needs-you-first` — **[OK]** (#6599, #6588; supersedes the plain "sorted by state then start" of
  `activity.pane.one-outline-table`) the default order puts first what NEEDS THE PERSON: failed and partial rows, a row paused
  for a cause or stopped at quit, a blocker whose fix is a person's (newest first); then what runs; then what waits or is
  blocked (in the lane's order); then what ended done (newest first). A column header's sort replaces it until cleared. The
  status bar counts "N need you". Acceptance: the fixture with a failed, a running, a waiting and a done row lists them in
  that order; a blocker with Download Again sorts with the failed. *Built 2026-11-14 night:* `ActivityPane.needsYouRank`
  (a row the person paused waits with the waiting; a blocker sorts by its state until `blocked` is its own); the status
  counts "N need you" in the window's bottom panel. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneOutlineTests.swift` (`flatOrder`; the order superseded).
- `activity.pane.fix-button-has-words` — **[OK]** (#6599, #6588; `activity.pane.error-row-shape`) the row's one button carries its
  WORD ("Download Again", "Choose Folder…", "Add Key…", "Continue", "Retry"), never an icon alone; the fix comes from the
  failure's primary action as the engine names it, the app maps an action id to its word and its act, and an action id it does
  not know shows "Show Details" (the Inspector), never a gear. Acceptance: each action id in the engine's table maps to a word;
  an unknown id reads Show Details. *Built 2026-11-14 night:* `ActivityPaneButton.forAction` (Settings…, Choose Folder…,
  Continue, Retry; Show Details selects the row so the Inspector shows its fix); the row draws the word in a small bordered
  button (`docs/assets/activity-pane/pane-fix-buttons.png`). *Test:* `fichero/Tests/Unit/general/Models/ActivityErrorRowTests.swift`
  extended (`everyActionHasAWord`).
- `activity.pane.one-undo-per-action` — **[PARTIAL]** (#6599, #6588, #6583; open question 7) ONE person's action is ONE step on the
  window's Undo stack, whatever it spans: rows of several projects, runs and jobs together, Archive Finished… and Archive
  Failed included; a run's Delete is undoable like a job's (`workflow_run.delete` gains `workflow_run.undelete`). Until a
  delete is undoable the confirmation says so. Acceptance: deleting a run and a job from two projects at once, then Undo once,
  lists all of them again in their states; Archive Finished… then Undo restores every row. *Built 2026-11-14 night:* a run's
  Delete is undoable (`workflow_run.delete` keeps `deleted_from`, its inverse `workflow_run.undelete`); a project's runs and
  jobs deleted together are ONE step (`ActivityStore.deleteAsOneStep`, `UndoableChange.batch`). *Not yet:* one step across
  several projects (a step is one project's today). Archive Finished… and Archive Failed are one undoable step per project
  too (`ActivityStore.archiveAsOneStep`: `job.archive` by states and `workflow_run.archive`). *Test:*
  `fichero-server/tests/unit/api/test_run_delete_is_undoable_6599.py`, `ActivityUndoTests.runAndJobAreOneStep`, `ActivityUndoTests.archiveFinishedIsOneStep`,
  `test_delete_is_undoable_6583.py`.
- `activity.pane.empty-says-one-line` — **[OK]** (#6599, #6588; supersedes `activity.window.no-empty-prose`'s blank) a pane with nothing to list says
  "Nothing running" in one line and keeps its status bar; a filter that hides everything says "No activity matches".
  *Built 2026-11-14 night:* `ActivityPane.emptyLine`. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityPaneFiltersTests.swift` extended (`emptyLine`).
- `activity.pane.verbs-one-word-each` — **[OK]** (#6599, #6588; `activity.pane.commands-through-the-table`) Retry is the one verb
  for running a failed row again; Read Again is the Inspector's verb on a failed PAGE only, not a Project › Activity item
  beside Retry. *Built 2026-11-15:* Project › Activity carries Stop and the verb list (Retry among it), the row's context menu
  the verb list alone; a failed run's Retry already reads the pages it did not do as a new run (`POST /jobs/{id}/retry`
  answers `replaces`). `ActivityToolbarVerbsTests.retryIsTheOneVerb`, `MenuTerminologyBoundaryTests.
  testActivityStopIsInTheMenuBarAndRetryIsTheOneRerun`. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityCommandsTests.swift` extended.

**Known broken (the engine review, 2026-11-14, verified in code; each its own issue: #6594, #6595, #6596):**

- `activity.engine.undelete-running-is-a-phantom` — **[OK]** (fixed 9847efc9e, #6594, #6588) Undo of a Stop-then-Delete restores a row as
  `running` with no thread (`undelete_jobs` writes `deleted_from.state` back as is): a row Delete stopped comes back
  `paused` "Stopped by you", never `running`. *Test:* `fichero-server/tests/unit/jobs/test_delete_is_undoable_6583.py`.
- `activity.engine.deleted-stays-deleted` — **[OK]** (fixed 9847efc9e, #6594, #6588) a deleted row is never picked and never revived: the lane's
  end write for a deferred or out-of-reach job skips a row with `deleted_at` set; a second Delete of a deleted row is a no-op
  (it does not re-stamp `deleted_at`, so Undo still restores it). *Test:* `fichero-server/tests/unit/jobs/test_deleted_stays_deleted_6588.py`.
- `activity.engine.open-queues-nothing-twice` — **[OK]** (fixed 6c5dcd44b, 612773c7b: a paused row is reused, and a person's own request on it lets it run; #6595, #6588, #6584) the open's pending-derivative resume
  (`db/manager.py`) and every enqueue dedupe against a row of the same kind and subject that is waiting OR PAUSED (and not
  deleted), so a relaunch never adds a twin and a deleted row's page is not queued again by the open. *Test:*
  `fichero-server/tests/unit/jobs/test_open_queues_nothing_twice_6588.py`.
- `activity.engine.close-pauses-running-work` — **[BROKEN]** (#6596, #6588) closing a project PAUSES the work running in it
  ("Paused: the project closed") and waits for it to let go of the connection before closing it; never a failure with the
  library's path in its words. *Test:* not yet written: `test_close_pauses_running_work_6588.py`.

### Ruled 2026-11-14 afternoon: the window, the bottom panel, the log, kept exports (decisions 22-29)

- `activity.window.toolbar-tabs` — **[SUPERSEDED 2026-11-15]** (decision 32, the sidebar: `activity.window.sidebar`) **[PARTIAL]** (#6588; decision 23; supersedes the Group by control of
  `activity.pane.group-by-run-or-by-file`) the Activity window's toolbar has ONE segmented control **Runs | Files | Cost |
  Where** and no search field (the filter is the bottom bar's, `activity.pane.bottom-bar-like-every-pane`); each tab is a grouping plus a
  column set over the same rows: **Runs** by run (Name, State, Steps, Time, Cost); **Files** by file (File, State, Steps it
  went through as its trail, Last run); **Cost** by run (Name, Model, Tokens, Time, Spent, To finish); **Where** by run (Name,
  Runs on: This Mac / Other Mac / Cloud / Cluster, Lane, State). The tab is per pane and remembered; a main window's Activity
  pane offers the same four in its head's lens menu. Acceptance: each tab shows its columns; switching keeps a selected row
  selected when it is listed in both. *Built 2026-11-14 night:* `ActivityPane.Tab` (a grouping and a column set each; a
  person's column toggles kept per tab, `ActivityPanePrefs.columns(for:)`; prefs stored before the tabs load, their grouping
  becoming the tab), the segmented control in the window's toolbar, the four in a main window pane's lens menu; Group by
  (View › Activity ▸) lands on Runs or Files. The engine says where each row runs (`runs_on`, `lane`,
  `test_activity_where_6588.py`; a workflow run by its page jobs). Picture: `docs/assets/activity-pane/window-toolbar-tabs.png`.
  The titles follow the tab ("File" and "Last Run" on Files, "Spent" on Cost, `Column.title(in:)`). *Test:*
  `fichero/Tests/Unit/general/Views/Activity/Pane/ActivityToolbarTabsTests.swift`.
- `activity.pane.bottom-bar-like-every-pane` — **[OK; its Metadata button SUPERSEDED 2026-11-15 by decision 35, `activity.pane.columns-from-the-header`]** (#6588; the owner 2026-11-14: "filter bar and metadata button at the
  bottom like in the rest of the app"; `panes.chrome.one-filter-pattern`, `PaneFilterBar`, `PaneFilterField`; supersedes the
  filter field at the top of `activity.pane.history-kept-and-filterable` and the window's Group by row) the pane's one bottom
  bar is the app's: **Metadata** (the column toggles of the one column table, `activity.pane.default-columns`, the same as the
  header's menu) and the **Filter** field (`PaneFilterField`: the tokens as typed, its menu what the list shows: Show
  Archived, Failed, Needs You, Started by automatic, Today); the status line's figures move to the bottom panel in the window
  and stay as the bar's trailing text in a main window's pane. Nothing of Activity's is a custom control at the top but the
  toolbar's verbs and tabs. Acceptance: the pane's view tree has one `PaneFilterBar` at the bottom holding a
  `PaneFilterField` and the Metadata menu, and no filter field above the table. *Built 2026-11-14 night:* the bar holds
  `PaneMetadataButton` (each column of the tab, on or off), `PaneFilterField` (its menu: Show Archived, Failed, Today,
  Started Automatically) and the status figures; the More menu (⋯) is the window's toolbar's, the bar's in a main window's
  pane (`docs/assets/activity-pane/window-bottom-bar.png`). Needs You waits for `activity.pane.needs-you-first`. *Test:*
  `fichero/Tests/Unit/general/Views/Activity/Pane/ActivityBottomBarTests.swift`.
- `activity.window.toolbar-verbs` — **[SUPERSEDED 2026-11-15]** (decisions 30-31: `activity.window.run-controls`, `activity.pane.row-controls`) **[PARTIAL]** (#6588; decision 24) **Pause**, **Continue** and **Stop** are toolbar buttons of
  the Activity window and of a main window while its Activity pane holds the focus, enabled by the Mail rule over the
  selection (the one verb list's definitions, `ActivityPaneVerb`), with the Inspector toggle; the More menu (⋯) keeps Show
  Archived, Archive Finished… and Archive Failed. Acceptance: with a running and a paused row selected all three enable; with a
  done row alone none does; the main window shows them only while the Activity pane has the focus. *Built 2026-11-14 night:*
  `ActivityToolbarVerbsBar` (one control group over the pane's `activityVerbs`, the target Project › Activity reads) in
  the Activity window beside the Inspector toggle and in the main window's leading zone, right of the sidebar, drawn only
  while an Activity pane holds the focus (`docs/assets/activity-pane/window-toolbar-verbs.png`); the More menu (⋯) is in
  the toolbar too. *Removed 2026-11-15:* `ActivityToolbarVerbsBar` and its tests went when the run controls (`activity.window.run-controls`) took its place in both toolbars.
- `activity.window.bottom-panel` — **[PARTIAL]** (#6588; decision 25; supersedes the one-line status bar of
  `activity.pane.less-is-more-table` for the window: a main window's pane keeps the one line) the window's foot is a panel per
  tab, figures AND a graph together: **Runs** pages done per minute over the last hour (a sparkline) and "N running · N
  waiting · N blocked · N need you"; **Files** pages done, failed and untouched today; **Cost** spend per hour over the day,
  today's total by provider, tokens; **Where** each place's load (this Mac's lanes busy of their width, calls in flight to
  the cloud, the other Mac and the cluster when connected, "—" when not). Engine: `GET /api/activity/history?minutes=60`
  answers per minute `pages_done`, `pages_failed`, `spend_usd`, `tokens` (and per runtime), derived from what is already kept
  (the jobs' `finished_at`, the spend ledger `llm/spend.py`, the calls' usage), no new recording; the panel reads it once a
  minute and on the change stream. Acceptance: a fixture of 30 pages done over 10 minutes answers 10 buckets summing to 30; the
  Cost panel's today total equals the ledger's; nothing is drawn when there is no history ("No work in the last hour").
  *Built 2026-11-14 night (app):* `ActivityBottomPanel` above the bottom bar in the window: a Swift Charts graph and the
  tab's figures (Runs: pages per minute, green done and red failed, and "N running · N waiting · N need you"; Files: done
  and failed; Cost: dollars per minute, today's by provider, tokens; Where: pages by place, "—" for none), the open projects'
  histories summed (`ActivityService.history`, read once a minute); "No work in the last hour" with no graph when empty; the
  bar's figures leave the window (they are the panel's). Picture: `docs/assets/activity-pane/window-bottom-panel.png`. *Not
  yet:* blocked counts, this Mac's lanes busy of their width. *Test:* the engine half:
  `fichero-server/tests/unit/api/test_activity_history_6588.py`; the app half:
  `fichero/Tests/Unit/general/Views/Activity/Pane/ActivityBottomPanelTests.swift`.
  (Engine note: today's total and its by-provider split are summed from the priced calls of pages finished today (UTC), the one
  source that names providers; the ledger keeps only a day's total.)
- `activity.log.raw-always-rendered` — **[PARTIAL]** (#6588; decision 27; `activity.window.log-levels`) the Inspector's Log is the
  RAW log of the row (every line the engine wrote, its time, level and text, monospaced, wrapped, selectable), rendered whole
  for every row that ran, a page row's log its own lines in its run's log; "Nothing written for this row yet" only for a row
  that has not started; Problems / All / Everything filter it and change nothing else; Copy Log copies exactly what is shown.
  Acceptance: a page that ran six steps shows its lines for each; a waiting row says nothing written. *Built 2026-11-14
  night:* a paused row's line ("Paused: <row>: <why>") is the person's, a warning, so Problems shows it (engine,
  `test_the_paused_rows_log_says_why_it_is_paused`); an empty log says "Nothing written" only for a row not started, "No
  problems in this row's log." under Problems, and "The engine wrote no lines for this row." for one that ran
  (`ActivityLogFilter.emptyWords`). *Not yet:* the raw text of the pause's cause in the log. *Test:* the existing
  `ActivityLogFilter` tests extended (`emptyWords`).
- `activity.pane.done-is-green` — **[OK]** (#6588; decision 26; `activity.pane.one-glyph-per-state`) the done glyph is
  `checkmark.circle.fill` in green; partial the check in green with its dot; failed the red X; everything else secondary. The
  table's state cell and the Inspector's versions draw the one `Glyph.tint`.
  *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityStateGlyphTests.swift` extended.
- `activity.pane.row-and-inspector-agree` — **[OK]** (#6588; decision 29) a row's Time, count and Cost and its Inspector's
  Elapsed, counts and cost are the same numbers from the same fields (a file row's time is its pages' summed work time and its
  Inspector says so, "work time 48 s"; never a step's 9 s beside the row's 48 s); a time is written "48 s", "3 min", "2 h"
  (no "secs.", no full stop, `activity.pane.text-budget`); local work's cost is blank and a priced call at $0 reads "Free",
  never "$0.00" (`activity.pane.cost-per-row-and-totals`). *Built 2026-11-14:* Free and blank cost (`ActivityPane.costLine`: the engine's 0.0 reads Free,
  its null blank); one short time unit, "48 s", "3 min", "2 h" (`ActivityMonitorRow.duration`). *Built 2026-11-14 night:* one
  `ActivityMonitorRow.elapsedSeconds` (the engine's seconds, else start to end) read by the Time cell, its sort and the
  Inspector, which names a file row's "Work time". *Built 2026-11-15:* a run the engine finds interrupted at the next open ends when it stopped (its close, else the last work heard from it), not when the open noticed, so a 3-minute Kraken run no longer reads "1 h" (`run_account.mark_interrupted_runs` passes `ended_at` to `mark_run_failed`; `test_interrupted_run_ends_when_it_stopped_6588.py`); a paused row's clock stops at the last work heard under it, not now (`jobs.tree`; `test_a_paused_row_stops_its_clock_6588.py`). Acceptance: the fixture's file row and its Inspector read the same
  time; a local Kraken row has no cost; a $0 cloud call reads Free. *Test:* `fichero/Tests/Unit/general/Models/ActivityPane/ActivityDefaultColumnsTests.swift` extended.
- `activity.pane.started-by-is-honest` — **[OK]** (#6588; `activity.pane.icons-say-source-and-kind`) the source glyph is a
  person only for a person's own act; the engine's own starters (`kept export`, `synced folder`, `automatic`, a schedule, a
  trigger) are automatic. Acceptance: `started_by: "kept export"` maps to automatic. *Built 2026-11-14 night:*
  `ActivityMonitorRow.automaticStarters` holds the engine's `jobs.BACKGROUND_STARTERS` (less schedule and trigger, their
  own glyph). *Test:*
  `fichero/Tests/Unit/general/Models/ActivityRowIconsTests.swift` extended.
- `activity.kept-export.one-row-per-export` — **[PARTIAL]** (#6588; decision 28; `kept_export.py`) the work changing queues ONE job
  per kept export (subject the export's id, the pages to rewrite gathered in its detail), never one per page; while it waits,
  more changes join it and push its quiet period; its row reads "Update kept export · <folder name> · N pages". When the
  folder is gone the job ends PAUSED "The export folder is gone" with Choose Folder… and nothing more is queued for that export
  until the folder is chosen again or Write Now is pressed; a per-export switch **Keep up to date** (on by default) turns the
  automatic rewrite off, Write Now still writing. Acceptance: ten page edits queue one row naming ten pages; with the folder
  removed, ten more edits add no row and the one row is paused with the fix; switching Keep up to date off queues nothing on
  an edit. *Built 2026-11-14:* one row per export (subject the export's id, `pages` and `keys` in its detail, the
  kind's `names` hook naming the row), a gone folder PAUSES it (`jobs._PAUSED_NOT_FAILED`; the path kept for Copy Details),
  Continue writes what waited, Write Now joins the row and drops its quiet period; removing the export ends its waiting or
  paused row ("The export was removed"). *Built 2026-11-14 night (engine):* `PATCH /api/export/kept/{id}`
  (`export.update`, audited) chooses the folder again (checked as at keep, 422 in words, nothing changed) and lets the row
  its gone folder paused write there, or switches `keep_up_to_date` (a column, on by default; off, `queue_rewrites`
  queues nothing, Write Now still writes); the gone folder's failure offers `choose-folder` then `resume`; the contract
  regenerated; the listed paused row carries its failure, the `choose-folder` action naming the export
  (`jobs.paused_failure`). *Built the same night (app):* the row's one button is Choose Folder… (a folder icon; the system
  folder panel, then `KeptExportStore.chooseFolder`), the alert's button "Choose Folder…", and the project Inspector's
  Kept Exported row has a **Keep up to date** switch and Choose Folder… beside Write Now
  (`docs/assets/activity-pane/pane-export-folder-gone.png`). *Test (app):* `KeptExportStoreTests.chooseFolderAndKeepUpToDatePatch`,
  `ActivityErrorRowTests.primaryFix`. *Test:*
  `fichero-server/tests/unit/jobs/test_kept_export_one_row_6588.py` (4, green),
  `fichero-server/tests/unit/jobs/test_kept_export_choose_folder_6588.py` (4, green).

### Ruled 2026-11-15 morning: run controls, the sidebar, models, graphs, columns, the log, recipes (decisions 30-37)

- `activity.window.run-controls` — **[PARTIAL]** (#6588; decision 30) the toolbar's leading item, in the Activity window and every
  main window, is Play/Pause (one button: Pause while anything runs or waits, Play while a Pause All is outstanding,
  disabled when neither) and Stop. **Pause All** pauses every running and waiting job and run of every open project (a
  person's too: a running page finishes, then the run holds), marks each with the one pause's id, and sets the global
  background pause so nothing new starts; ONE undo step. **Play** (Continue All) resumes exactly the jobs that mark names and
  clears the background pause; a row paused by hand before stays paused. **Stop All** asks once ("Stop 3 runs and 41 waiting
  jobs? Their work so far is kept; Retry runs them again.") and stops every running and waiting job; not undoable (Retry is
  its way back). The engine owns all three: `activity.pause_all`, `activity.continue_all`, `activity.stop_all`, audited
  actions over every open project's queue, and the summary says which the button shows (`controls: "pause" | "play" |
  "none"`, `stoppable: n`). Acceptance: two projects, a person's run and 20 waiting thumbnails: Pause All leaves none
  running; a row paused by hand before stays paused after Play; Undo of Pause All is Play's effect; Stop All ends them
  cancelled with their done pages kept. *Built 2026-11-15:* the engine's `jobs.pause_all` / `continue_all` / `stop_all` (the `held_by` mark), the three routes and actions, the summary's `controls` and `stoppable`; the app's `ActivityRunControlsBar` at the far left of the Activity window and of every main window, over every open project, Stop asking once. *Not yet:* one undo step across projects (each project's Pause All is its own step); a real-run check. *Test:* `fichero-server/tests/unit/jobs/test_pause_all_continue_all_6588.py`,
  `fichero/Tests/Unit/general/Views/Activity/Pane/ActivityRunControlsTests.swift`.
- `activity.pane.row-controls` — **[GAP]** (#6588; decision 31) the selected or hovered row's trailing cell shows its own
  Play/Pause (by its state, `ActivityPaneVerb.pause` / `.resume`) and Stop, small, borderless, through the one verb list;
  nothing for a row neither allows. The toolbar holds no selection verbs; the context menu and Project › Activity keep them.
  *Test:* `ActivityRowControlsTests.swift`.
- `activity.window.sidebar` — **[PARTIAL]** (#6588; decision 32; supersedes `activity.window.toolbar-tabs`) the Activity window
  is a `NavigationSplitView`: a source list (Runs, Files, Recipes, Cost; Models, a section of its own,
  `activity.window.models-tree`; Archived), the table, the Inspector. Each item is a grouping plus a column set over the
  same rows (Runs, Files, Cost as the tabs had them; Archived the archived rows by run); the item is remembered per window;
  each item's count of rows needing you is its badge. A main window's Activity pane offers the same items in its head's
  lens menu. Acceptance: choosing Files lists by file; Archived lists only archived rows and Show Archived leaves the More
  menu. *Built 2026-11-15:* the window is a `NavigationSplitView` laid out by the pane (sidebar, centre, the window's Inspector beside the centre); the source list Activity (Runs, Files), Resources (Cost, Where), Archived (`ActivityPane.Tab.archived`: the archived rows only); Runs badged with the rows needing you (`ActivityPane.needsYouCount`); the tabs left the toolbar, which leads with the run controls (`docs/assets/activity-pane/window-sidebar.png`). *Not yet:* Recipes and Models (Steps 5.3, 5.5), Show Archived leaving the More menu. *Test:* `ActivityWindowSidebarTests.swift`.
- `activity.window.models-tree` — **[PARTIAL]** (#6588; decision 33) the sidebar's Models section is place › provider › model:
  **This Mac** (Kraken, each embedding model, MLX and Ollama models), **Remote** (another Mac by name, a cluster: ACENET),
  **Cloud** (Anthropic, OpenAI, Hugging Face, …), from the engine's one list `GET /api/activity/models`: each model's id,
  name, place, provider, `loaded` (held in memory, this Mac's from the model registry; a remote one's as its host says),
  `active` (a call or page in flight now), the rows it runs now, and today's pages and calls. Its icon: filled when loaded,
  hollow when not; a green dot (animated while working) when active. Choosing a model lists the rows it ran or runs (by
  `model` and `runs_on`); choosing a provider or place lists all of theirs. A model used today and not loaded stays listed,
  hollow. Acceptance: with Kraken reading and an embedder loaded idle, Kraken is filled with the dot, the embedder filled
  without, a cloud model used this morning hollow. *Built 2026-11-15:* the engine's `GET /api/activity/models` (`workflows/activity_models.py`: the job rows' model and each call's provider, model and place; `models_held`; Kraken's memory the size its load is given, marked estimated) and the sidebar's Models section, place › provider › model, read every ten seconds, the icon filled while loaded, a green dot while working, the memory beside it; a model or provider picked filters the centre by `model:`. *Not yet:* a model's Inspector; listing by `runs_on` as well as the model's name. *Test:* `fichero-server/tests/unit/api/test_activity_models_6588.py`,
  `ActivityModelsTreeTests.swift`.
- `activity.window.graph-on-every-view` — **[PARTIAL]** (#6588; decision 34; extends `activity.window.bottom-panel`) the bottom
  panel is on every sidebar item, 180 pt tall by default, its divider dragged and its height kept per window: Runs and
  Files as built; Recipes pages per minute by recipe; Cost as built; a model or place its pages and calls per minute
  (`/api/activity/history` grouped by model). Acceptance: every item draws a graph; the height survives a relaunch.
  *Built 2026-11-15:* every sidebar item draws its graph, with time and count axes, under the rows in a `VSplitView` whose divider the person drags (`docs/assets/activity-pane/window-graphs.png`). *Not yet:* the height kept across relaunch; Recipes' and a model's own graphs. *Test:* `ActivityBottomPanelTests.swift` extended.
- `activity.pane.columns-from-the-header` — **[OK]** (#6588; decision 35; supersedes the Metadata button of
  `activity.pane.bottom-bar-like-every-pane`) the columns are chosen from a column header's context menu, and their
  visibility, widths and order are kept per sidebar item (`TableColumnCustomization`, stored with the pane's prefs); the
  bottom bar holds the filter only. Acceptance: a column widened stays widened after a relaunch; the bar has no Metadata
  button. *Built 2026-11-15:* the Metadata button is gone; the table's `TableColumnCustomization` (kept per item in the pane's prefs) gives the header's column menu and keeps widths and order. *Test:* `fichero/Tests/Unit/general/Views/Activity/Pane/ActivityToolbarTabsTests.swift` (`rememberedPerTab`).
- `activity.log.like-xcode` — **[OK]** (#6588; decision 36; extends `activity.log.raw-always-rendered`) the Inspector's log is
  a list, one engine line per row (time, level glyph, text, monospaced, long lines wrapped); a click selects a line, shift
  and command select many; ⌘C and Copy copy the selected lines (all when none); the log's find field highlights each match
  and steps through them; the level filter stays. Not editable. *Built 2026-11-15:* `ActivityLogLinesView` (number, level glyph, time, text; click, shift, command; ⌘C; the find bar with "2 of 5" and up/down) over `ActivityLogList`'s rules; Copy Log becomes Copy Lines while lines are selected (`docs/assets/activity-pane/inspector-log.png`). *Test:* `ActivityLogListTests.swift`.
- `activity.window.recipes` — **[PARTIAL]** (#6588; decision 37; an exception to `activity.pane.children-are-what-it-works-on`'s
  two levels) the Recipes item lists each recipe (name and version) with its runs under it and each run's steps under
  that. A recipe row: runs, pages done and failed, failed %, seconds a page (median), cost a page, last run. A run row: its
  scope (folder), started, outcome, the same rates. A step row: its node's name, model and place, pages done and failed,
  seconds a page, tokens, cost. The Inspector of a run draws its graph as the node editor does (the run's stored
  `workflow_snapshot` / `diagram_mermaid`), each node with its done, failed and seconds; of a recipe, its runs' rates side by
  side. Engine: `GET /api/activity/recipes?days=30` answers it from what is kept (the runs' timelines and usage,
  `run_view.step_timing`), no new recording. Acceptance: two runs of one recipe, one with Kraken (3 of 20 failed) and one
  with Qwen (0 failed), read 15% and 0% failed with each step's model; the run's Inspector draws its nodes with counts.
  *Built 2026-11-15:* the engine's `GET /api/activity/recipes` (`workflows/activity_recipes.py`, from the run records and each run's job tree) and the sidebar's Recipes item: an outline table recipe › run › step (Runs, Model, Pages, Failed, Failed %, A Page, Cost a Page, When) over the graphs (`ActivityRecipesView`). *Not yet:* the recipe's version; the run's node graph in the Inspector; a recipe-run's stages (run-a-recipe) as their own level. *Test:* `fichero-server/tests/unit/api/test_activity_recipes_6588.py`, `ActivityRecipesViewTests.swift`.

- `activity.window.centre-views` — **[GAP]** (#6588; decisions 38-39) the centre's head carries a view picker, **Table |
  Graph | Visual**, per sidebar item and remembered: Table is the rows (every item); Graph the item's rows over time (the
  history, `GET /api/activity/history`, by the item's grouping: Runs and Recipes pages per minute, Cost spend, a model or place
  its pages, calls and memory); Visual draws the selection: a run as its node graph (`activity.window.recipes`'s Inspector
  drawing, full size), work as a timeline of bars per lane or per model (each row a bar from start to end, coloured by state),
  a cluster its jobs on a timeline (queued, then running). An item with no Visual meaning offers Table and Graph. Acceptance:
  Runs offers all three; choosing Visual on a run draws its nodes; the choice survives a relaunch. *Test:*
  `ActivityCentreViewsTests.swift`.
- `activity.window.views-are-panes` — **[GAP]** (#6588; decision 40; `panes.chrome.one-filter-pattern`) the Activity
  sidebar, the centre (with its views) and the graphs are pane kinds of the app's pane system, with its head and its footer
  (`PaneFilterBar`), so a main window can show any of them as a pane, and the Activity window is those panes in its own
  layout; no Activity-only chrome. Acceptance: a main window offers "Activity Graphs" and "Activity" panes; the Activity
  window's centre is the same view type. *Test:* `ActivityPaneKindsTests.swift`.
- `activity.graphs.own-pane` — **[PARTIAL]** (#6588; decision 41; supersedes the fixed panel of `activity.window.bottom-panel` and
  the fixed height of `activity.window.graph-on-every-view`) the graphs are a pane: under the centre by default, its divider
  dragged, and maximised full size like any pane (and back); it follows the sidebar's selection. Acceptance: maximising it
  fills the window's centre; restoring it gives the height it had. *Built 2026-11-15:* the graphs' Full Size button fills the centre with them (kept per window, `@SceneStorage`) and Show the Table brings the rows back. A main window opening it as a pane is `activity.window.views-are-panes`, below. *Test:* `ActivityBottomPanelTests.swift` extended.
- `activity.resources.everything-measured` — **[GAP]** (#6588; decision 42; `activity.window.models-tree`) the engine answers,
  per model, `memory_bytes` (a process of its own: its resident size, `execution/models_held.py`; Kraken's readers: the size
  the throttle gives them, marked `estimated`), `loaded_at`, and today's `pages`, `calls`, `seconds`; per cluster job (the
  remote jobs, `workflows/remote_jobs.py`), `queued_seconds`, `run_seconds` (from its phase history), node hours and cost when
  the cluster reports them; per Mac, memory used of its total, processor, lanes busy of their width. The Inspector of a model,
  a cluster job or a place shows them; the Models tree's rows show memory; the Graph view draws them over time. What nothing
  measures is "—", never 0. Acceptance: an embedder loaded shows its resident megabytes; Kraken shows "~2.5 GB (estimated)";
  a cluster job of 40 min queued and 12 min run reads both. *Test:* `fichero-server/tests/unit/api/test_activity_models_6588.py`
  extended, `test_cluster_job_times_6588.py`.

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

### Stage 3 — blockers, downloads that work, names (owner 2026-11-14)

#### Step 3.1 — models that download and load (#6588)
- Behaviours: `activity.download.installed-means-it-loads`, `activity.download.says-bytes-and-time-left`
- Tests: test_model_installed_means_it_loads_6588.py (not yet written), test_embeddings_load_from_one_folder_6588.py (not yet written), test_every_download_reports_bytes_6588.py (not yet written)
- Depends on: none
- Size: M

First, because every new install hits it: one real folder per model, load-checked before installed, bytes on the row.

#### Step 3.2 — blocked work under its blocker; no raw text (#6588)
- Behaviours: `activity.pane.blocked-under-its-blocker`, `activity.failure.no-raw-text-ever`
- Tests: test_blocked_work_waits_on_its_blocker_6588.py (not yet written), ActivityBlockedRowsTests.swift (not yet written), fichero-server/tests/unit/llm/test_every_failure_kind_has_a_fix_6354.py
- Depends on: 3.1
- Size: M

#### Step 3.3 — the row names what it works on (#6588)
- Behaviours: `activity.pane.names-what-it-works-on`
- Tests: ActivityNamesWhatItWorksOnTests.swift (not yet written), fichero-server/tests/unit/jobs/test_row_says_what_ran_on_what_6441.py
- Depends on: 2.5
- Size: M

### Stage 4 — the Activity Monitor window (owner 2026-11-14 afternoon)

#### Step 4.1 — honest rows: green done, short times, Free and blank cost, honest source, row and Inspector agree (#6588)
- Behaviours: `activity.pane.done-is-green`, `activity.pane.row-and-inspector-agree`, `activity.pane.started-by-is-honest`
- Tests: fichero/Tests/Unit/general/Models/ActivityPane/ActivityStateGlyphTests.swift, fichero/Tests/Unit/general/Models/ActivityPane/ActivityDefaultColumnsTests.swift, fichero/Tests/Unit/general/Models/ActivityRowIconsTests.swift
- Depends on: none
- Size: S

#### Step 4.2 — the toolbar: verbs and the four tabs (#6588)
- Behaviours: `activity.window.toolbar-verbs`, `activity.window.toolbar-tabs`
- Tests: fichero/Tests/Unit/general/Views/Activity/Pane/ActivityToolbarVerbsTests.swift, fichero/Tests/Unit/general/Views/Activity/Pane/ActivityToolbarTabsTests.swift
- Depends on: 4.1
- Size: M

#### Step 4.3 — the history and the bottom panel (#6588)
- Behaviours: `activity.window.bottom-panel`
- Tests: fichero-server/tests/unit/api/test_activity_history_6588.py, fichero/Tests/Unit/general/Views/Activity/Pane/ActivityBottomPanelTests.swift
- Depends on: 4.2
- Size: M

#### Step 4.4 — the raw log; kept exports one row each (#6588)
- Behaviours: `activity.log.raw-always-rendered`, `activity.kept-export.one-row-per-export`
- Tests: test_kept_export_one_row_6588.py (not yet written)
- Depends on: none
- Size: M

### Stage 5 — the owner's window (2026-11-15 morning)

#### Step 5.1 — global run controls and the row's own (#6588)
- Behaviours: `activity.window.run-controls`, `activity.pane.row-controls`
- Tests: fichero-server/tests/unit/jobs/test_pause_all_continue_all_6588.py, ActivityRunControlsTests.swift, ActivityRowControlsTests.swift
- Depends on: none
- Size: M

#### Step 5.2 — the sidebar (#6588)
- Behaviours: `activity.window.sidebar`
- Tests: ActivityWindowSidebarTests.swift
- Depends on: none
- Size: M

#### Step 5.3 — the Models tree (#6588)
- Behaviours: `activity.window.models-tree`
- Tests: fichero-server/tests/unit/api/test_activity_models_6588.py, ActivityModelsTreeTests.swift
- Depends on: 5.2
- Size: M

#### Step 5.4 — graphs on every view; columns from the header (#6588)
- Behaviours: `activity.window.graph-on-every-view`, `activity.pane.columns-from-the-header`
- Tests: ActivityBottomPanelTests.swift, ActivityPanePrefsTests.swift
- Depends on: 5.2
- Size: M

#### Step 5.5 — the Recipes view (#6588): the engine's route, then the view and the run's graph
- Behaviours: `activity.window.recipes`
- Tests: fichero-server/tests/unit/api/test_activity_recipes_6588.py, ActivityRecipesViewTests.swift
- Depends on: 5.2
- Size: M

#### Step 5.6 — the log like Xcode's (#6588)
- Behaviours: `activity.log.like-xcode`
- Tests: ActivityLogListTests.swift
- Depends on: none
- Size: M

#### Step 5.7 — the centre's views: Table, Graph, Visual (#6588)
- Behaviours: `activity.window.centre-views`
- Tests: ActivityCentreViewsTests.swift
- Depends on: 5.2
- Size: M

#### Step 5.8 — Activity's views are panes; the graphs a pane of their own (#6588)
- Behaviours: `activity.window.views-are-panes`, `activity.graphs.own-pane`
- Tests: ActivityPaneKindsTests.swift, ActivityBottomPanelTests.swift
- Depends on: 5.2, 5.4
- Size: M

#### Step 5.9 — every resource measured: model memory, cluster times, this Mac (#6588)
- Behaviours: `activity.resources.everything-measured`
- Tests: test_activity_models_6588.py, test_cluster_job_times_6588.py
- Depends on: 5.3
- Size: M

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
