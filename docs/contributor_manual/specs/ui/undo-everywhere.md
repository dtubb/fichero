# Undo everywhere: one way back for every change, from the window that made it. Design Spec (#5658)

> Milestone: undo-trash-rollback
> Manual: TBD. "Undo and Redo" must tell a researcher: Command-Z takes back the last change
> made in this window, and the menu names it ("Undo Move", "Undo Delete 3 Items"); Shift-Command-Z
> puts it back; a change made in another window stays with that window; when someone or
> something has changed the thing since, Fichero says so in a sentence and changes nothing;
> what cannot be undone (exports, sign-in, running a job, emptying the Trash) and why; where
> older changes can still be taken back (the history list).
>
> **Status: DRAFT, 2026-10-10; reconciled with `../safety/undo.md` the same day.** Its one
> open decision was ruled by the maintainer on 2026-10-11: one stack per window (see
> "Decision"). Slice 1's app half is built (2026-10-11).
>
> **Who owns what.** This file owns the APP path of taking things back: the one helper, the
> window's step stack, the Edit menu, typing and the image editor, naming, showing a refusal in
> words, batches as the app sees them, iPhone and iPad, and the coverage guard's measure.
> `../safety/undo.md` (#5242) owns the undo DESIGN: what is undoable, whose step it is, the
> engine's audit chain and its locks (never over later work, from any window), one step undone
> once and a set undone whole, redo keeping the id, the command line and agents. A behaviour
> lives in one of the two files; the other links to it. Deleted things and the Trash belong to
> `../safety/trash.md`; moves and copies between projects, and how they are undone, to
> `../source/moving-between-projects.md`.
>
> Every claim about the code is marked **VERIFIED** (read in the file, line given) or
> **INFERRED**. Nothing was run except the registry and contract counts below, which were
> taken by loading the engine's action registry and the committed `openapi.json` on
> 2026-10-10 at `2273d3e26`; line numbers were re-read at `ef5ae2273`.
> Tags: **[OK]** built and tested · **[PARTIAL]** built in part or unproven · **[GAP]** not
> built · **[BROKEN]** the code contradicts the rule.

## Intent

The maintainer's direction (2026-10-10): every change a person makes should be undoable
unless there is a real reason it cannot be, the way back should be reachable from the app,
and it should be bulletproof.

What a person sees: they move a letter, delete three notes, or rename a folder. The Edit menu
then reads "Undo Move", "Undo Delete 3 Items" or "Undo Rename". Command-Z takes the change back
and Shift-Command-Z puts it back. Each window keeps its own list of the changes made in it. If
another window, another device, an agent or a workflow has changed the same thing since, the
undo is refused in a sentence ("This note was changed in another window at 14:02. Your
delete was not undone.") and nothing changes. A change that cannot be undone says so before it
runs.

The engine already does most of the work. It records almost every edit as an audited action
with an inverse, and one route reverses any of them (`POST /api/actions/audit/{id}/undo`).
The gap is in the app. Command-Z is registered in five different ways, and most calls register
nothing at all. The Edit menu ignores what has been registered. It undoes the newest step in
one project's history instead, whoever made that step. This spec gives the app **one path**:
any call a person starts whose answer names its audit row goes through one helper. The helper
registers the step on that window's undo stack, under the action's own name. Undo and redo then
ask the engine to reverse those exact rows and nothing else.

## Prior art

- **The Mac.** Undo belongs to the window or document, and the Edit menu names the step
  ("Undo Typing", "Undo Move of 3 Items"). `UndoManager` keeps the redo stack and clears it
  when a new step is made. We adopt this and do not build a stack of our own.
- **Shared editors** (Google Docs, Figma). Undo is "my own last change", and a change that can
  no longer apply is refused or skipped. We refuse (`safety.undo.refuses-when-changed`).
- **Optimistic concurrency.** A stale change is refused with HTTP 409. The engine already
  answers 409 for a refused action (`ActionRefused`, f9a4e9ba3). This spec makes the app read
  that answer.
- **What we do differently.** The window's stack holds only **audit row ids** and never an
  app-side copy of the data or a closure that changes it. The engine stays the one record and
  the one judge of whether a reversal is still safe. This is why the stack can be per window
  without becoming a second source of truth.

## Decision: one stack per window (RULED by the maintainer, 2026-10-11)

**The question.** `../safety/undo.md` once proposed one undo stack per person per project,
shared by every window and pane, and no project steps in any window's undo manager. This spec
proposed one stack per window. The two contradicted each other.

**Ruled 2026-10-11 (the maintainer), as proposed while he was away: per WINDOW.** Each window's Command-Z takes back what was done in that
window, newest first, and Shift-Command-Z puts it back. The engine still decides every undo
against the audit chain and refuses in words if the world moved on, whichever window asked
(`safety.undo.refuses-when-changed`). The project's history list (Action History) lists every
step from every window, device, agent and run, and is where an older step, or another
window's step, is taken back deliberately.

**Why.**
- It is the Mac's convention: two document windows have two undo stacks. A person who works
  in two windows expects Command-Z in the front one to touch only what they did there.
- It cannot become a second source of truth: the stack holds row ids, and every reversal is
  judged by the engine against the one record.
- "Mine only" holds by construction in the app: a window holds only steps its person started.
- It costs nothing to build: SwiftUI and AppKit give each window an `UndoManager`, with redo,
  grouping and titles.

**What the per-person stack would have given, and where that went.** Taking back a step made
in a pane of the same window still works (panes share their window's stack). Taking back a step
made in a window since closed works from the history list. The command line and agents have no
window; their quick undo is the engine's "what is next" call (`safety.undo.the-engine-says-what-is-next`).

**If the maintainer rules per person instead:** the helper and every call site stay; only the
stack's owner changes, from the window to one stack per project shared by the project's
windows. The engine needs no change either way.

## What exists (2026-10-10)

| What | State | Evidence |
| --- | --- | --- |
| One engine route reverses any audited row, and redoes when the row is itself an inverse | built | VERIFIED `fichero-server/src/fichero_server/api/routes/system/actions_registry.py:284-422` |
| 382 registered actions; 240 undoable with an inverse | built | counted from `registry.all()` |
| An action refusing because the world moved on answers 409 with its reason in words | built for one action (`finddocs`), shape ready for all | VERIFIED `actions/registry.py:198`, route `actions_registry.py:402-403`; test `fichero-server/tests/unit/finddocs/test_find_documents_to_spec.py::test_finddocs_redo_of_an_accept_a_later_run_replaced_is_refused_in_words` |
| The undo route's other refusals are developer words ("Action is not undoable: x") | wrong for a person | VERIFIED `actions_registry.py:318, 321, 350, 367, 378, 383, 388, 398` |
| 409 and 404 are not declared on the undo route in the contract (only 200, 422) | so the generated client hands the app `.undocumented` | VERIFIED `fichero-server/tests/contracts/openapi.json`, path `/api/actions/audit/{audit_id}/undo`; the app's switch at `fichero/fichero/Services/ActionInvokeService.swift:115-121` |
| `ActionUndo`: registers a step by audit id, files the redo correctly despite the async engine call | built and tested | VERIFIED `fichero/fichero/Models/ActionUndo.swift`; `fichero/Tests/Unit/general/Models/ActionUndoTests.swift` (7 tests) |
| `AuditedAction.run`: invoke, then `ActionUndo.register` | built, used by the Hands verbs | VERIFIED `fichero/fichero/Models/AuditedAction.swift:5-24` |
| 22 call sites of `ActionUndo.register`/`AuditedAction.run`, written in five shapes | scattered | `git grep` over `fichero/fichero` (listed in "Slice 1") |
| 11 more person-initiated `invokeAction` calls that register nothing (duplicate, delete selected, merge, split, claim, language, translate, sidebar drop and duplicate) | reach Command-Z today only through the global history, and only in the always-there project | VERIFIED `git grep "\.invokeAction("` (listed in "Slice 1") |
| Sidebar delete calls `document.delete` and then registers a closure that calls `restoreDocument` | a second path that bypasses the engine's undo row, so no inverse row and no redo | VERIFIED `fichero/fichero/Views/Sidebar/Components/SidebarActions.swift:229-246` |
| Canvas move/resize and the workflow canvas register app-state closures on the window's manager | a second path | VERIFIED `…/Canvas/Engine/CanvasInteractionController+Undo.swift:42-77`; `…/Workflow/Canvas/WorkflowCanvasView.swift:4-24` |
| "Continue Flow" opens an undo group and keeps it open across N awaited engine calls | INFERRED: any registration another view makes in the same window meanwhile joins the group | VERIFIED `fichero/fichero/Views/Components/ReadingOrderPicker.swift:166-185` |
| The Edit menu replaces the system Undo/Redo with its own | built | VERIFIED `fichero/fichero/FicheroApp.swift:489-491` |
| Its Undo never calls the window's `UndoManager`: it routes to typing, the image editor, navigation Back, or `AuditStore.undoLast()` | so registrations are unreachable outside a text field, and Back outranks undo | VERIFIED `fichero/fichero/App/Menus/FocusedCommands/FocusedCommandButtons+UndoNavigation.swift:89-174`; `fichero/fichero/App/Menus/UndoRouting.swift:38-55` |
| `AuditStore.undoLast()` reverses the newest undoable row of the **always-there project**, by anyone | wrong project, wrong person | VERIFIED `FocusedCommandButtons+UndoNavigation.swift:58, 64`; `fichero/fichero/Models/LibraryManager.swift:658-660`; `fichero/fichero/Models/AuditStore.swift:119-121, 160-166` |
| `invokeAction` records every audited call into a single-level `LastAction` | a third, global holder | VERIFIED `fichero/fichero/Services/ActionInvokeService.swift:62-69, 265` |
| A text field's typing undo and `ActionUndo`'s project steps share one manager | INFERRED: the field editor asks its window for its undo manager, and `ActionUndo` registers on the window's (`@Environment(\.undoManager)`); so Command-Z in a field can pop a project step that sits on top | `UndoRouting.swift` `FocusedTextResponder.undo()`; to be confirmed by the mounted test in `undo.window.own-stack` |
| A refused undo is silent in `ActionUndo` (`try?`) and reads "Undo failed (409)" in `AuditStore` | the engine's sentence is lost | VERIFIED `ActionUndo.swift:76`; `AuditStore.swift:92-100`; `ActionInvokeService.swift:115-121` |
| The engine overwrites a later change when it undoes an earlier one, and a test pins it | the engine half of cross-window safety is missing | VERIFIED `fichero-server/tests/unit/api/test_action_undo.py:453`; owned by `safety.undo.refuses-when-changed` (#5242) |
| The undo coverage guard counts files that name an operation, not calls that register | measures the wrong thing | VERIFIED `scripts/check_undo_coverage.py` docstring; #5109 |

## The design

### One helper

There is one helper, named here `UndoableChange` (the name is not fixed). Every call a person
starts that changes project data goes through it:

1. It runs the call through the generated client, never a hand-written URL.
2. It reads the audit row id or ids the answer names (see "Every answer names its row").
3. It registers one step on **the window's step stack**, named in words. A batch registers one
   step that holds several ids.
4. On undo, it asks the engine to reverse that step's ids **as one set**
   (`safety.undo.a-set-is-undone-whole`): all or none, in one call. The redo is filed during
   the undo handler, as `ActionUndo` already does (`ActionUndo.swift:12-19`), and it reverses
   the set of rows the undo wrote.
5. On a refusal, it shows the engine's sentence in the window. A `changed` refusal leaves the
   step where it was; `already-undone` and `gone` drop it (`safety.undo.refusal-loses-nothing`).
6. It records the project the step belongs to, and looks up that project's live service at
   undo time, never at registration. This matters after an engine restart and after the
   window switches project.
7. While one of its calls from this window is still waiting for the engine, Undo and Redo in
   that window are disabled (`undo.window.in-flight`).

`ActionUndo` becomes the helper's core, because its redo bookkeeping is right and tested.
Only calls the person starts are registered: a workflow run, an agent in the chat, an App
Intent from Shortcuts and a background job never register a step
(`safety.undo.agents-and-runs-are-not-in-my-stack`).

### Every answer names its row

Only 20 operations name their audit row in the answer today (`ActionResultResponse`,
`ArtifactRegionsEditResponse`, …). Another 160 run an undoable audited action and then return
a domain object with no id. **One engine change covers all 160:** the action layer remembers the
ids of the audit rows it wrote while serving a request, and every mutating route answers them
in one declared response header, `X-Fichero-Audit-Ids`, as a list. The generated client exposes
the header as a typed field, so the helper reads it without parsing anything by hand. The
existing `audit_id` body fields stay. The 24 routes that write directly while an undoable
action for the same change already exists (`POST /api/workflows`, `DELETE
/api/search/saved/{id}`, …) are moved onto that action first (Open question 3).

### The window's step stack

Each window has one `UndoManager` that **the helper owns**. The helper publishes it as a
scene-focused value. It is separate from the manager that text fields use for typing, so
typing steps and project steps never mix in one stack (`undo.window.own-stack`). Panes in one
window share their window's stack. The Edit menu's order is `undo.edit-menu`.

`AuditStore.undoLast()` and `LastAction` stop driving Command-Z and are deleted. The history
list (`AuditHistoryView`) keeps its deliberate, one-row-at-a-time reversal, shows the same
sentences on a refusal, and lists the window each step came from where the record has it (the
engine already receives `X-Fichero-Origin-Window`, VERIFIED `fichero-server/src/fichero_server/api/auth.py:583-607`).

### When steps end

A window's steps are in memory and end with: the window (closed), the app (quit), the project
(closed, or returned to a snapshot by `../safety/safety-net.md`, because its rows no longer
describe what the project holds), and the person (signed out, or another account signed in).
In every case the steps stay in the history list, from where they can still be taken back
under the same locks. The helper registers each project's steps against one target object per
project, so ending one project's steps is `removeAllActions(withTarget:)` on each window.

### Batches

A change a person makes to several things at once is **one step**. The engine's own batch
actions (one call, one audit row: `claim.batch_transition`, `document.batch_exclude`, …) are
used where they exist. Where the app makes N calls, the helper collects the N ids the answers
name and registers **one** step after the last call returns; it never holds an undo group open
across awaits. If some of the N calls failed, the step holds only the ids that were written,
and its name counts them ("Undo Delete 2 Items"). Undo reverses the set in one engine call,
all or none; a refusal names the one thing that refused, nothing changes, and the step stays.

### Moves between projects

How a move or copy between projects is recorded and undone is
`../source/moving-between-projects.md` (`transfer.action.undo-move`, `transfer.action.undo-copy`):
one transfer, one record in each project under the same id, undone by the engine both sides or
neither. The app holds the transfer's one id as one step, with the source project as its
project, and never orchestrates the two sides itself. The menu reads "Undo Move to “Istmina”".
When the drag crossed two windows (source in one, target in the other), the step is registered
in both, and whichever window undoes it first removes it from the other
(`undo.window.drag-between-windows`), which is how `transfer.app.undo-both-windows` is met.

## Behaviours

### One path

- `undo.one-path` — **[PARTIAL]** (#5658) every person-initiated call that changes project data
  and whose answer names an audit row registers Command-Z through one helper, and nothing
  else registers project steps. Today there are 22 helper-shaped call sites in five shapes,
  11 `invokeAction` sites that register nothing, three app-state closures, and a global
  `LastAction`. *Test:* a guardrail (`undo.guard.no-bypass`) and a pure Swift test of the
  helper against a fake engine. Built (slice 1, app, 2026-10-11): `UndoableChange` (`fichero/fichero/Models/UndoableChange.swift`) over `ActionUndo`'s core, on the window's `WindowSteps`; the 22 helper-shaped sites and the 11 unregistered `invokeAction` sites moved onto it; `LastAction` and `AuditStore.undoLast` deleted; `UndoableChangeTests`. *Not built: the guardrail `undo.guard.no-bypass`.*
- `undo.one-path.every-answer-names-its-row` — **[PARTIAL]** (#5658) every mutating route that
  wrote audit rows names them in its answer, in the declared `X-Fichero-Audit-Ids` header (or
  the existing `audit_id` field). 20 operations do so today and 160 audited routes do not.
  *Test:* pytest over the contract: every mutating operation whose handler invokes an audited
  action declares the header; one test per domain reads it back.
- `undo.one-path.no-local-closures` — **[PARTIAL]** (#5658) no view registers an undo that
  changes data through anything other than the engine's undo route; a window's stack holds
  record ids, never data and never a closure that writes. Sidebar delete restores through
  `restoreDocument` instead of reversing its own `document.delete` row
  (`SidebarActions.swift:235-245`), so the restore writes no inverse row and has no redo. The
  canvas and workflow canvas register app-state closures. All three move onto the helper.
  *Test:* the guardrail refuses `registerUndo(withTarget:)` outside the helper, text editing
  and the image editor. Built (slice 1, app, 2026-10-11): sidebar delete registers its own `document.delete` row through the helper (the `restoreDocument` closure is gone, so Redo works). *Not built: the canvas and workflow-canvas closures (build step 7).*
- `undo.one-path.reachable` — **[GAP]** (#5658) every undoable change a person can make in the
  app can also be taken back from the app: from the Edit menu in the window that made it, and
  from the history list afterwards. A change with no way back says so before it runs
  (`safety.undo.every-action-says-how-it-comes-back`). *Test:* click-around for each domain in
  the build order.

### Naming

- `undo.settings-are-not-undone` — **[OK]** (manager ruling 2026-10-20) a settings switch does not go on the undo
  stack: System Settings and the app's Settings do not do it either. Switching it back is its undo, the change is
  still audited, and undo per window covers edits to project content. So a mutating route that only sets an app or
  Settings switch (where models may run, `PUT /api/recipes/places`) is listed in the undo guard's known gaps as "not
  undoable by design", with this reason. `fichero-server/tests/unit/scripts/test_every_guard_passes_on_the_real_tree.py`
  (`check_undo_coverage.py`).
- `undo.naming` — **[PARTIAL]** (#5658) the step is named with the action's words, the way a
  person would say it: "Undo Move", "Undo Rename", "Undo Delete Note", and never a dotted
  action id. The words come from ONE place, so the Edit menu, the history list, the command
  line and the refusal sentence agree: a short verb and noun on each action's registration,
  answered by the engine. Until the registration carries them, the helper takes a typed name
  (verb + noun) from the call site, as `ActionUndo` already does. The Edit menu today derives
  "Undo Merge" from the dotted action name of the newest audit row
  (`FocusedCommandButtons+UndoNavigation.swift:111-124`). *Test:* pure Swift, a name for every
  action in the build order; pytest, every undoable registration has a verb and noun.
- `undo.naming.counts` — **[PARTIAL]** (#5658) a step over several things counts them: "Undo
  Delete 3 Items", "Undo Move 12 Pages". One thing is named by its kind ("Undo Delete Note").
  *Test:* pure Swift, 1, 2 and many. Built (slice 1, app, 2026-10-11): `UndoableChange.named` and the batch's name ("Move 3 Items to Trash", "Delete 3 Notes"); `UndoableChangeTests`::namesCount. *Not built: a name for every action in the build order.*
- `undo.naming.other-project` — **[GAP]** (#5658) when the window now shows another project
  than the step's, the title names the step's project ("Undo Move in Marshall Diaries").
  *Test:* pure Swift with two fake projects.

### The window

- `undo.window` — **[PARTIAL]** (#5658) Command-Z in a window reverses that window's last
  step, and only that window's (the provisional decision above). Today the Edit menu never
  calls a window's undo manager. When no text field has focus it reverses the newest row in
  the always-there project's history, whoever made it and whichever project the window shows
  (`FocusedCommandButtons+UndoNavigation.swift:58-64, 149`; `LibraryManager.swift:658-660`).
  *Test:* click-around: make a step in window A, focus window B, press Command-Z, and A's step
  is untouched; with nothing made in B, Undo in B is disabled even though the history has rows. Built (slice 1, app, 2026-10-11): the Edit menu's ⌘Z and ⇧⌘Z read the key window's `WindowSteps` (focused scene value) and nothing else outside typing and the image editor; `UndoRoutingPolicyTests`. *Not run: the two-window click-around.*
- `undo.window.own-stack` — **[PARTIAL]** (#5658) the helper's stack is separate from the typing
  stack. While an editable text field has focus, Command-Z and Shift-Command-Z are the
  system's own typing undo for that field, with the grouping Mac users expect, and never reach
  a project step, even when the typing stack is empty; a project step never swallows typing.
  The INFERRED sharing of one manager today (see "What exists") is confirmed or ruled out by
  this behaviour's test before slice 1 is merged. *Test:* mounted test: register a step, focus
  a field, type, then Command-Z undoes only the typing, the step is still offered, and the
  record has no new row. Built (slice 1, app, 2026-10-11): `WindowSteps` owns its own `UndoManager`, apart from the text view's; `WindowStepsTypingTests` (a real window and text view). *Not built: the iOS scene's responder answer (`undo.ios`).*
- `undo.edit-menu` — **[PARTIAL]** (#5658) Command-Z goes to exactly one of these, in this
  order, and the menu item's title says which: (1) a focused, editable text field: its own
  typing undo; if its typing stack is empty, the item is disabled, never the project; (2) the
  image editor, when open with uncommitted steps: its last step; (3) the key window's step
  stack, titled by the stack (`undoMenuItemTitle`, `redoMenuItemTitle`); (4) nothing,
  disabled. Shift-Command-Z follows the same order. The text-field and image-editor routes are
  built and tested (`fichero/Tests/Unit/general/App/UndoRoutingPolicyTests.swift`); the
  window-stack route and its titles are not built. *Test:* extend the pure routing test, every
  combination. Built (slice 1, app, 2026-10-11): the window-stack route and its titles (`windowSteps.undoName`, `redoName`), `edit.undo` and `edit.redo`; `UndoRoutingPolicyTests`. *Not built: the image editor's Redo.*
- `undo.edit-menu.never-navigates` — **[OK]** (#5658) going Back is not an undo. Command-Z
  never changes what is shown except to reveal the thing a reversal changed. Back keeps its own
  key. Today navigation outranks the project in the routing (`UndoRouting.swift:52-53`).
  *Test:* pure routing: navigation is not an input; click-around: open a folder, press
  Command-Z, the view does not move. Built (slice 1, app, 2026-10-11): `UndoRoute` has no navigation or project-log case; `UndoRoutingPolicyTests`::testNothingMadeInThisWindowIsNoRoute.
- `undo.window.in-flight` — **[OK]** (#5658) while a call this window started is waiting for
  the engine, Undo and Redo in this window are disabled, so a quick Command-Z after a change
  never takes back the step BEFORE it. *Test:* pure Swift with a slow fake engine: start a
  change, Undo is disabled; the answer arrives, Undo names the change. Built (slice 1, app, 2026-10-11): `WindowSteps.inFlight` counts the window's calls (a change through the helper, an undo, a redo) and `canUndo`/`canRedo` are false while any is out; `UndoableChangeTests`::inFlightDisables, ::aRunningChangeHoldsUndo.
- `undo.window.drag-between-windows` — **[GAP]** (#5658) a step made by a drag from one window
  into another is offered in both; undoing it in one removes it from the other. *Test:* pure
  Swift with two window stacks.
- `undo.typing.commit-is-one-step` — **[PARTIAL]** (#5658) when a field commits an edit (focus
  leaves, or the app saves), the whole edit becomes ONE step on the window's stack, named "Edit
  Transcription" or the like. With focus still in the field, Command-Z keeps undoing typing.
  A later commit that the engine folds into the same row
  (`safety.undo.commits-are-not-per-keystroke`) answers the same row id, and the helper
  coalesces it into the step already on top rather than adding one. *Test:* type, click away,
  Command-Z: the text returns to what it was before the edit; three autosaves leave one step. Built (slice 1, app, 2026-10-11): the same rows answered again are the step on top, not a second step; `UndoableChangeTests`::sameRowsCoalesce. *Not built: a field's commit as one step.*
- `undo.image-editor` — **[PARTIAL]** (#5658) inside the image editor, Command-Z drops the last
  uncommitted step (built) and Shift-Command-Z puts it back (not built: there is no Redo).
  On Done, the whole session is one step on the window's stack. *Test:* crop, rotate,
  Command-Z, Shift-Command-Z, Done, Command-Z outside the editor: the image is as it was before
  the session.

### Across windows and projects

What happens when another window, device, agent or run changed the thing since is the
engine's rule, `safety.undo.refuses-when-changed` (#5242): refused, nothing changed. The app's
part is to show that sentence (`undo.refusal`).

- `undo.cross-window.others-see-the-result` — **[PARTIAL]** (#5658) after an undo or redo,
  every other window showing the thing updates through the change stream, with no manual
  refresh. The stream exists (`harness/observable-data-layer.md`). Some call sites still
  re-read by hand (`afterChange` in `AuditedAction.swift:10-21`). *Test:* click-around: undo in
  A, and B's row changes.
- `undo.cross-project` — **[PARTIAL]** (#5658) a step stays tied to its project. If the window has
  switched to another project, Command-Z still reverses the step in the project it was made
  in (`undo.naming.other-project`). *Test:* pure Swift with two fake projects. Built (slice 1, app, 2026-10-11): a step keeps its project's path and finds that project's live service when taken back, whatever the window shows now. *Not built: `undo.naming.other-project`.*
- `undo.steps-end` — **[PARTIAL]** (#5658) a window's steps end with the window, the app, their
  project (closed or returned to a snapshot) and the signed-in person, as "When steps end"
  says; they stay in the history list. *Test:* pure Swift: close project P, and its steps are
  gone from every window while Q's remain; a sign-out empties every stack. Built (slice 1, app, 2026-10-11): `WindowSteps.endSteps(forProject:)` on project close (`LibraryManager.closeLibrary`) and `endAllSteps()` on sign-out (`SessionStore.logout`), in every window; `UndoableChangeTests`::endingOneProjectsSteps. *Not built: the snapshot restore.*

### Refusal

- `undo.refusal` — **[PARTIAL]** (#5658) when the engine refuses an undo or redo, the window
  shows the engine's sentence. A `changed` refusal leaves the step where it was;
  `already-undone` and `gone` drop it, saying so ("This change was already taken back in
  another window."). Today 409 and 404 are not declared on the route, so the generated client
  returns `.undocumented`. `ActionUndo` swallows the error (`try?`, `ActionUndo.swift:76`) and
  `AuditStore` shows "Undo failed (409)" (`AuditStore.swift:95`). *Test:* declare 404 and 409
  with `detail` and `reason` in the contract; a Swift test with a fake engine that refuses
  checks that the sentence reaches the window and which steps stay. Built (slice 1, app, 2026-10-11): the set route's declared 404/409 arrive as `UndoRefusal` (sentence + reason); `changed` keeps the step, `already-undone` and `gone` drop it; the sentence shows in `UndoRefusalNotice` (`undo.refusal.notice`) in the window that asked; `UndoableChangeTests`::changedKeepsTheStep, ::alreadyUndoneAndGoneDrop. *Not built: a refused REDO keeping its place (it is dropped, and the history list still has it).*
- `undo.refusal.in-words` — **[PARTIAL]** (#5658) every refusal from the undo route is a
  sentence a researcher can act on: "This page was changed by Ana at 14:02, after your edit.
  Your edit was not undone. See history." No status codes and no ids. `ActionRefused` does
  this (f9a4e9ba3), but the route's other refusals are developer words ("Action is not
  undoable: x", "Inverse/replay action unknown: y", `actions_registry.py:318-398`). Who changed
  it and when arrive with #5242. *Test:* pytest, one per refusal kind, checks the message
  contains no action id and no status code.
- `undo.shows-what-it-took-back` — **[GAP]** (#5658) after an undo or redo, the app reveals the
  thing (selects it, scrolls to it) when it is in an open pane of this window, and shows a
  short notice naming the step either way. Nothing is taken back off-screen in silence.
  *Test:* click-around.
- `undo.offered-after-a-removal` — **[GAP]** (#5658) after a delete or a merge, a short notice
  offers Undo for a few seconds. It is the same step as Command-Z, on the same stack, not a
  second path. *Test:* click-around.

### Batches

- `undo.batches` — **[PARTIAL]** (#5658) a change made to several things at once is one step.
  `ReadingOrderPicker` groups N registrations into one "Continue Flow" step, but holds the
  group open across awaits (`ReadingOrderPicker.swift:166-185`). Deleting several documents
  in the library makes N calls and registers nothing
  (`fichero/fichero/Views/Library/LibraryView+DeleteActions.swift:90-97`), and so does deleting
  several notes (`fichero/fichero/Views/Library/Notes/NoteListView.swift:136-150`). *Test:*
  pure Swift: delete 3, then one Command-Z brings back all 3.
- `undo.batches.whole` — **[PARTIAL]** (#5658) a batch is reversed as one set by one engine call
  (`safety.undo.a-set-is-undone-whole`): all or none. A refusal names the one thing that
  refused, changes nothing, and the step still holds all its ids. *Test:* a fake engine that
  refuses the set: nothing reversed, the sentence names the second item, the step still holds
  three; a backend test for the set itself is in `../safety/undo.md`. Built (slice 1, app, 2026-10-11): a batch is one step holding every row written, taken back by one set call; `UndoableChange.batch`; library delete-selected and Continue Flow use it; `UndoableChangeTests`::aBatchIsOneSet, ::aFailedBatchHoldsWhatWasWritten. *Not built: the refusal naming the one thing that refused (the engine's sentence is shown as it comes).*

### Redo

How the engine redoes, keeps ids and passes four laps is `../safety/undo.md` §D. The app's part:

- `undo.redo` — **[OK]** Shift-Command-Z reverses the rows the undo wrote, and undo, redo,
  undo walks the chain one row at a time. *Tests:* `ActionUndoTests.redoIsRegisteredDuringTheUndo`,
  `.redoInvertsTheUndosOwnRow`, `.theChainKeepsGoing` (in
  `fichero/Tests/Unit/general/Models/ActionUndoTests.swift:59-102`).
- `undo.redo.new-step-clears` — **[OK]** (#5658) once I make a new step in a window, my
  earlier undone steps there are no longer offered by Shift-Command-Z; they remain in the
  history list. `UndoManager` does this itself, but no test pins it for the helper, whose redo
  is registered from inside an undo handler. *Test:* pure Swift: undo, register a new step, and
  Redo is disabled. Built (slice 1, app, 2026-10-11): `UndoableChangeTests`::newStepClearsRedo.
- `undo.redo.before-the-answer` — **[OK]** (#5658) a redo pressed before the engine has
  answered the undo does nothing and is logged. It never guesses a row. Built
  (`ActionUndo.swift:66-74`) but not tested; with `undo.window.in-flight` the menu shows Redo
  disabled until the answer arrives. *Test:* pure Swift with a slow fake engine. Built (slice 1, app, 2026-10-11): `UndoableChangeTests`::redoBeforeTheAnswer; the menu's Redo is also disabled while the undo is out.

### Engine restart

- `undo.engine-restart` — **[PARTIAL]** (#5658) after the engine restarts, Command-Z still
  reverses the window's steps, because the audit rows are in the project's database, their ids
  are never reused (UUID, `fichero-server/src/fichero_server/models/__init__.py:158-160`), and
  the helper looks up the live service at undo time. If a row no longer exists, the engine
  answers `gone` and the window says "This change is no longer in the project's history" and
  drops the step. Today each call site captures its service when it registers, so this is
  INFERRED to break after a reconnect. *Test:* pure Swift: a step registered against service 1
  is undone through service 2 after a swap; integration: register, restart the dev engine,
  then undo succeeds. Built (slice 1, app, 2026-10-11): the step looks up its project's live service when taken back; `UndoableChangeTests`::liveServiceAtUndoTime. *Not run: the integration leg (restart the dev engine, then undo).*

### Moves between projects

- `undo.move-between-projects` — **[GAP]** (#5658) a move, copy or alias between projects is
  one step holding the transfer's one id; Command-Z asks the engine to undo the transfer, which
  does both sides or neither (`transfer.action.undo-move`). The app never reverses one side on
  its own. *Test:* adversarial case 7; depends on `../source/moving-between-projects.md`.

### iPhone and iPad

- `undo.ios` — **[GAP]** (#5658) on iPhone and iPad, the system's undo gestures (shake,
  three-finger swipe), the keyboard's undo key and the iPad Edit menu reach the window
  scene's helper stack under the same rules: one stack per scene, typing in a field first.
  INFERRED: the gestures ask the responder chain for its `undoManager`, so the scene's root
  must answer the helper's manager while a focused field keeps its own. *Test:* iOS leg: make
  a change, shake, confirm, the change is back; with a field focused, only typing is undone.

### The guard's measure

- `undo.guard.measure` — **[GAP]** (#5109) `scripts/check_undo_coverage.py` counts an operation
  as covered when an app call to its generated method sits inside a helper call. Naming the
  operation anywhere in a file that registers undo no longer counts. *Test:* the guard's
  self-test with a fixture: a call inside the helper is covered, and the same call beside it
  but outside is not.
- `undo.guard.three-lists` — **[GAP]** (#5109) the single known-gaps baseline is replaced by
  three lists, each entry with a reason: **one-way by design** (its reason taken from the
  action's registration, `safety.undo.every-action-says-how-it-comes-back`, where the route
  invokes an action); **needs an engine inverse** (each with an issue); **waiting for the
  app** (the engine inverse exists and the app has not adopted it; only shrinks). A route on
  no list and not covered fails. *Test:* the guard's self-test.
- `undo.guard.no-bypass` — **[GAP]** (#5658) an app call to an operation that answers audit
  rows, made outside the helper from a view or store, fails the guard unless the call is on
  the one-way list. *Test:* fixture.

## Classification of the known gaps

`scripts/check_undo_coverage_known_gaps.json` lists 460 operations. 279 of them carry only the
reason "no undo registration in current tree". They were classified by loading the action
registry (which action each route's handler invokes, and whether that action is undoable) and
reading the contract (whether the answer names an audit row). That machine pass was then
checked by hand for each area, and 31 rows were moved where the machine reading was wrong.
Some single rows may still be misread. Each row is confirmed when its domain is wired, which is
also the moment it leaves the baseline.

| Class | Count | What it takes |
| --- | --- | --- |
| **Undoable by the one path: ready** (answer already names its row) | 18 | Call the helper. Includes find-documents accept/split/join/move-page, hands, signs, rights, proposed kind, mention repoint/respan, reading-order place. |
| **Undoable by the one path: audited, answer is silent** | 160 | One engine change (the `X-Fichero-Audit-Ids` header) covers all of them, then call the helper. Largest areas: segments 17, knowledge graph 17, documents 16, research 14, image edits 13, recipes 6, claims 5, canvas 5. |
| **Undoable by the one path: route bypasses its own action** | 24 | Move the route onto the existing undoable action, then as above. Workflows 7 (create, import, update, patch, delete, duplicate, reorder), providers 6, saved searches 4 (update, delete, duplicate, reorder), conversations 3, batches 2, action library 2. |
| **Needs an engine inverse** | 77 | See the list below. |
| **One-way by design** | 181 | Keep. Reasons below. |
| **Total** | 460 | |

So 202 of 460 need no inverse work, only the helper (and for 184 of them, the header or a
route move first).

**Needs an engine inverse (77), by area:**

- *Folders* (4): create, rename, delete and move an entity folder (`/api/folders/{entity_type}/…`). No `folder.*` action exists.
- *Knowledge graph* (8): claim and entity batch curation (`*.batch_curation` exist, undoable=False), prune trivial claims, PyKEEN review create and verify, apply a prediction run, queue a review pair, link an external authority (#3740).
- *Claims* (3): assign time period (two routes), batch transition.
- *Hermeneutics* (7): framework, interpretation, pattern and circle-state create, add a claim to a pattern, circle navigate and backtrack.
- *Registries and kinds* (8): epistemic statuses and claim kinds create/patch/delete; entity types add/remove on a project.
- *Projects and the project list* (8): create a project (`POST /api/library`), patch, include/remove an item, add/remove a known project, update access, merge Unicode collisions.
- *Chains, schedules, triggers, orchestration policies, the action library* (18): their create/update/delete routes; use, from-node and composite actions.
- *Workflow tools* (3): set a tool prompt, create a node from a tool, reinstall defaults.
- *Notes, annotations, representations* (4): note links add/remove, promote an annotation to a claim, revise a representation (#3740).
- *Runs and tasks the person deletes* (3): delete a workflow run (`workflow_run.delete`, undoable=False "for now"), delete a run thread, delete a task. These should go to the Trash (`../safety/trash.md`).
- *Other* (11): conversation reorder, provider ref and model add, library view columns, activity delete, Tinderbox note create and attribute edit, agent write and approve, browser save, node-comparison apply.

**One-way by design (181): kept, with the reason a person is told:**

| Reason | Count | Examples |
| --- | --- | --- |
| Starts or controls work: a run or job is stopped, not undone. Its results are taken back as a run (`../safety/run-take-back.md`). | 75 | training, checking, reading at scale, workflow execute/resume/cancel, batches execute, reindex, embed, KG rebuild, sync-folder tie/untie/mode |
| Reads only: a POST that computes and writes nothing | 36 | search, SPARQL, compare readings, estimate cost, recipe check/assemble, transliterate |
| App preference or machine state, not project data: setting it again is the way back | 26 | AI defaults, model profiles, provider keys, MCP servers, HPC clusters, local models and runtimes |
| Sign-in, accounts and devices: the inverse is its own deliberate act (revoke, sign out) | 15 | login, invites, users, pairing, device renew/revoke |
| Imports: taken back by moving what arrived to the Trash, not row by row | 14 | ingest folder, bulk create, bibliography import, integrations import |
| Exports: the files written stay; un-keeping stops future writes | 12 | Word, Excel, Parquet, site, kept exports |
| Permanent by definition | 3 | purge from Trash, clean up orphans, clean up activity |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | helper: naming, counts, sets, refusal kinds, project targets, steps end, in-flight, drag between windows, coalescing, live service at undo time, redo cleared, redo before answer | `fichero/Tests/Unit/general/Models/UndoableChangeTests.swift` (new), extends `ActionUndoTests.swift` |
| Availability (Swift) | y | Edit-menu routing: typing, image editor, window stack, disabled; navigation never; titles from the stack | extends `fichero/Tests/Unit/general/App/UndoRoutingPolicyTests.swift` |
| Mounted (Swift, XCTest) | y | typing and project steps never share a stack | `fichero/Tests/Unit/general/App/WindowStepsTypingTests.swift` (new) |
| Backend (pytest) | y | 404 and 409 declared on the undo route with `reason`; the set route; refusals in words; every audited route answers `X-Fichero-Audit-Ids` | `fichero-server/tests/unit/api/test_action_undo.py`, `tests/contracts/` |
| MCP | n | (agents' undo is `safety.undo.command-line-and-agents`) | |
| CLI | n | (same) | |
| Click-around (XCUITest, Mac) | y | each domain: do, Command-Z, Shift-Command-Z, title text; two windows | `fichero/Tests/UI/mac/…` (subclass `FicheroUISessionTests`) |
| iPhone (iOS) | y | system undo gesture reaches the helper | `fichero/Tests/UI/ios` |
| iPad | y | same, with a keyboard | `fichero/Tests/UI/ipad` |
| Load (#4634) | n | | |
| Guardrail | y | `undo.guard.*`, and slice 1's one-path check | `scripts/check_undo_coverage.py` self-test |

**Adversarial cases (each is its own test):**

1. **Undo after another window edited.** Window A renames a note. Window B renames it again.
   Command-Z in A is refused with a sentence, B's name stands, and A's step is still offered.
   B undoes; now A's undo succeeds. (Engine half: `safety.undo.refuses-when-changed`, #5242;
   until it lands, the engine overwrites B's name, as it does today.)
2. **Undo after another window deleted the thing.** A renames a note; B deletes it. A's
   Command-Z is refused, saying the note was deleted and is in the Trash; A's step stays.
3. **Undo after the history list took it back.** A moves a document; the history list reverses
   that move. A's Command-Z is answered `already-undone`, the window says so, and the step is
   dropped (it is not offered again).
4. **Undo after an engine restart.** Register three steps, restart the engine, then undo all
   three. With the project returned to a snapshot instead, every step of that project is gone
   from every window and stays in the history list.
5. **Command-Z pressed before the change answered.** Rename, and press Command-Z at once: Undo
   is disabled until the rename answers, and the step before the rename is never taken back.
6. **Redo pressed twice, fast.** The second press does nothing until the first answer arrives,
   and never reverses the redo it just made.
7. **Undo of a move between projects.** Move a document from P to Q by dragging from P's window
   to Q's. Both windows offer "Undo Move to “Q”". Command-Z in Q: it is back in P, not in Q, and
   not in either Trash; P's window no longer offers it. Then, after a fresh move, with Q's copy
   edited in Q's window, Command-Z in P is refused, and the document is in Q only, unchanged.
8. **Typing, then Command-Z.** With a project step on the stack and a text field focused,
   Command-Z undoes the typing only, and with the typing stack empty it is disabled. Click
   out, and Command-Z undoes the project step.
9. **Batch with a refusal in the middle.** Delete three notes; another window edits the second.
   Command-Z is refused, names the second note, and none of the three comes back. Command-Z
   again is refused again with the same sentence. The other window undoes its edit; now
   Command-Z brings back all three.
10. **Project closed, account switched.** Make a step in P, close P, and Command-Z does not
    offer it; reopen P, and the step is in the history list, not the stack. Sign in as another
    person: every window's stack is empty.
11. **Window switched project.** Make a step in P, switch the window to Q, and the menu reads
    "Undo … in P". Command-Z reverses it in P and Q is untouched.
12. **Two windows, one project, independent stacks.** A step in A is never offered in B.
13. **iPhone.** Make a change, shake, confirm Undo: the change is back. Focus a field, type,
    shake: only the typing is undone.

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | the maintainer's "Undo and Redo" section (Manual: TBD above) |
| Contributor | developer docs | y | this spec; `docs/contributor_manual/guide/05-actions-audit-and-undo.md` gains "register through the helper" |
| AI / agent | MCP tool description | n | |
| Scripter | CLI `--help` | n | |
| Reference | capability/endpoint reference | y | the `X-Fichero-Audit-Ids` header and the undo route's refusals, generated |

## Accessibility identifiers

- The Edit menu items: `edit.undo` and `edit.redo` (their titles are the stack's).
- The sentence shown when the engine refuses: `undo.refusal.notice`.

## Open questions

1. **One stack per window, or one per person per project?** Answered provisionally: per
   window (see "Decision"). Waiting for the maintainer on #5658.
2. **The helper's own stack, or the system window manager?** The system manager is shared with
   text fields' typing (INFERRED), so project steps and typing would interleave.
   **Recommendation: the helper owns one `UndoManager` per window**, published as a
   scene-focused value, and the Edit menu picks between it and typing by focus as it does
   today. The mounted test in `undo.window.own-stack` settles the INFERRED sharing.
3. **Header, or a body field?** **Recommendation: the `X-Fichero-Audit-Ids` header** for the
   160 silent routes. It is one change in the action layer, the response bodies stay the same,
   and it handles routes that write more than one row. Keep `audit_id` in the bodies that
   already have it. Move the 24 bypassing routes onto their actions in the same slice.
4. **Should app settings have undo?** AI defaults, MCP servers, HPC clusters and model profiles
   are app preferences, not project data. **Recommendation:** not through the engine record.
   Settings forms use the system's field undo, and deleting a configured cluster or server
   asks first. They stay on the one-way list.
5. **The always-there project's history list.** Once Command-Z leaves `AuditStore.undoLast()`,
   should the history list show every open project, or the window's project?
   **Recommendation:** the window's project, with a project picker. That is where a person
   looks for "what did I change here".
6. **How far a batch goes.** Should a select-all delete of 500 items be one step?
   **Recommendation: yes**, but through an engine batch action (one row) once more than a
   handful of items are involved, so that the forward change is one call and not 500.

## Build order

### Slice 1 (next): the helper, the window's stack, the Edit menu, refusals in words

**What a person gains.** Command-Z in a window takes back that window's last step and names
it; a refusal reads as a sentence; Back is no longer an undo; sidebar delete comes back with a
Redo. Pins: `undo.one-path` (for the sites below), `undo.one-path.no-local-closures` (sidebar
delete), `undo.window`, `undo.window.own-stack`, `undo.window.in-flight`, `undo.edit-menu`,
`undo.edit-menu.never-navigates`, `undo.naming` (typed names), `undo.naming.counts`,
`undo.cross-project`, `undo.steps-end`, `undo.refusal`, `undo.refusal.in-words` (the route's own
messages), `undo.batches.whole`, `undo.redo.*`, `undo.engine-restart`; engine:
`safety.undo.a-set-is-undone-whole`, and with it `safety.undo.marked-inside-the-transaction`.

**Engine.**
- `fichero-server/src/fichero_server/api/routes/system/actions_registry.py`: declare 404 and
  409 on `POST /api/actions/audit/{audit_id}/undo` with one refusal body (`detail`, a
  sentence; `reason`: `changed`, `already-undone`, `gone`, `not-undoable`); rewrite the route's
  developer-word messages as sentences; add the set route (`POST /api/actions/audit/undo`, body
  `{audit_ids}`), newest first in one `db.transaction()`, with the "undone" marks inside it,
  answering the new rows' ids; the single route becomes a set of one.
- Regenerate the contract and the client (`fichero-server/tests/contracts/openapi.json`,
  `fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json`, the docs copy).
- Tests in `fichero-server/tests/unit/api/test_action_undo.py`: a set of three succeeds and its
  redo restores all three with their ids; a set with one stale row is refused whole, nothing
  changed, the refusal names the row's thing; two concurrent undos of one row: one succeeds,
  one is `already-undone`; a forced failure after the inverse leaves neither inverse nor mark;
  a missing row answers `gone`; no refusal message contains an action id or a status code. A
  contract test asserts 404 and 409 are declared on both routes.

**App.**
- New `fichero/fichero/Models/UndoableChange.swift`: the helper (run the call, collect ids,
  register one step, undo and redo as a set, refusal kinds, in-flight count, project target,
  live service looked up at undo time). `ActionUndo.swift` stays as its core.
- New `fichero/fichero/Models/WindowSteps.swift`: the window's own `UndoManager`, one target
  per project, `endSteps(for:)`, published with `focusedSceneValue`; ended on project close,
  snapshot restore and sign-out.
- `fichero/fichero/App/Menus/UndoRouting.swift`: `UndoRoute` and `RedoRoute` lose `.navigation`
  and `.auditedAction` and gain `.windowSteps`.
- `fichero/fichero/App/Menus/FocusedCommands/FocusedCommandButtons+UndoNavigation.swift`: Undo
  and Redo read the focused `WindowSteps`, take titles from it, show refusals; no `AuditStore`
  and no `LastAction`.
- `fichero/fichero/Services/ActionInvokeService.swift`: handle the declared 404 and 409 as a
  typed `UndoRefusal` (sentence + reason); add the set call; delete `LastAction` and its
  recording (`ActionLibraryService.swift:41`).
- `fichero/fichero/Models/AuditStore.swift`: delete `undoLast()` and `nextUndoableEntry`; the
  history list's one-row reversal shows the same `UndoRefusal` sentence.
- New `fichero/fichero/Views/Components/UndoRefusalNotice.swift` (`undo.refusal.notice`), shown
  in the window that asked.
- The 22 existing call sites, moved onto the helper: `AuditedAction.swift:14`,
  `ReadingChoice.swift:26`, `ReadingOrderStore.swift:194`, `SegmentEdit.swift:276`,
  `SourceDirection.swift:25`, `WorkingPassChoice.swift:19, 53`,
  `ArtifactService+RegionCuration.swift:28`, `ReadingOrderList.swift:191`,
  `ReadingOrderPicker.swift:90, 176` (the open group across awaits becomes one set step),
  `InspectorEditorialSection.swift:80`, `InspectorHandsSection.swift:88, 100`,
  `InspectorLinksSection.swift:96`, `InspectorNoReadingSection.swift:45`,
  `InspectorRightsSection.swift:103`, `InspectorSegmentMakingSection.swift:87`,
  `ZoomableImagePreviewMac+SegmentEdits.swift:48`, `ReaderTextEditRunner.swift:40, 54`,
  `SegmentsGatheredList.swift:64`.
- The 11 person-initiated `invokeAction` sites that register nothing, onto the helper, because
  removing the global history from Command-Z would otherwise take their only (wrong) way back:
  `EntityStore+Mutations.swift:102` (merge), `EntityMergeSheet.swift:168`,
  `EntitySplitSheet.swift:130`, `ClaimSummaryCard+Details.swift:616`,
  `DocumentInspectorInfoTab+Language.swift:198`, `ArtifactsInspectorPane+Translate.swift:30`,
  `LibraryView+ContextMenu.swift:192` (duplicate), `LibraryView+DeleteActions.swift:94` (delete
  selected: one set step), `SidebarDropOperation.swift:170, 253`,
  `SidebarItemRow+Presentation.swift:194`. `FicheroActionIntents.swift:107` is not a window and
  stays off the stack.
- Sidebar delete (`SidebarActions.swift:229-246`): the `restoreDocument` closure is deleted; the
  `document.delete` row is registered through the helper, so undo writes the inverse row and
  Redo works. `document.delete` already reverses through its own inverse
  (`documents.py:3858-3866`).
- Not in slice 1, and left as they are: the canvas and workflow-canvas closures (build step 7;
  unreachable from the Edit menu today and after); routes whose answers are silent (slice 2).

**Tests.**
- New `fichero/Tests/Unit/general/Models/UndoableChangeTests.swift` (Swift Testing, MainActor
  default isolation): a fake engine; step named and counted; set undo and set redo; `changed`
  keeps the step, `already-undone` and `gone` drop it with a sentence; in-flight disables Undo;
  a new step clears Redo; redo before the answer does nothing; ending a project's steps leaves
  the other's; a step registered against one service undoes through its replacement; the same
  row answered twice coalesces.
- Extend `fichero/Tests/Unit/general/Models/ActionUndoTests.swift` for the set shape.
- Replace `AuditStoreRedoTests` and `LastActionScopingTests` (deleted with the global path, 2026-10-11), which pinned the global path this slice deletes (`menus.undo-reaches-every-mutating-action`), by
  the tests above; the history list's one-row reversal keeps its own test.
- Extend `fichero/Tests/Unit/general/App/UndoRoutingPolicyTests.swift`: every combination of
  text focus, typing stack, image editor and window stack; navigation is never a route.
- New `fichero/Tests/Unit/general/App/WindowStepsTypingTests.swift` (XCTest, a real window and
  text view): typing undo never pops a project step, and the reverse.
- A guardrail, `scripts/check_undo_one_path.py` with a self-test: `registerUndo(withTarget:` only
  in the helper, the image editor and the two named canvas files (each line citing build step
  7); `ActionUndo.register` only in the helper; no `undoLast` and no `LastAction`; every
  `.invokeAction(` outside `Intents/` inside a helper call.
- Click-around (`fichero/Tests/UI/mac/`, run by the manager in a GUI session): delete a
  document from the sidebar, the menu reads "Undo Move to Trash", Command-Z brings it back,
  Shift-Command-Z deletes it again; two windows, a step in one is never offered in the other.

**Acceptance.**
1. All of the above tests pass, and the four spec guardrails, `scripts/check_undo_coverage.py`
   and the new one-path check pass.
2. `git grep` finds `ActionUndo.register` only in the helper, no `undoLast`, no `LastAction`.
3. The contract declares 404 and 409 on both undo routes, and the regenerated client has no
   `.undocumented` branch in the undo path.
4. By hand, in the running app: adversarial cases 3, 5, 8, 11 and 12, and the sidebar
   delete with Redo.
5. **Known and accepted for slice 1:** changes made through the 160 routes whose answers are
   silent lose the accidental Command-Z they had in the always-there project (reversing the
   newest row, anyone's) until slice 2 names their rows; they stay reversible from the history
   list. And until `safety.undo.refuses-when-changed` (#5242) lands, an undo after another
   window's later change overwrites it, exactly as today. #5242's B should be built straight
   after slice 1.

### Then

2. **Every answer names its row:** the `X-Fichero-Audit-Ids` header, and the 24 bypassing
   routes moved onto their actions. After this, the guard's new measure goes in (`undo.guard.*`).
3. **Documents and folders:** create, rename, move, reorder, duplicate, delete, Put Back. Entity
   folders get their inverse (needs-inverse list).
4. **Annotations.**
5. **Claims and entities**, including the batch curation inverses.
6. **Notes**, including multi-delete as one step and note links.
7. **Workflows and canvases:** the canvas and workflow-canvas closures are deleted
   (`safety.undo.canvas-moves-are-recorded-steps`); create, patch, delete, duplicate, reorder.
8. **Saved searches and bookmarks.**
9. **Kinds and registries:** classifications, epistemic statuses, claim kinds, entity types.
10. Then the rest of the needs-inverse list, by daily use. Moves between projects follow
    `../source/moving-between-projects.md` once its engine action exists.

Each domain lands with its click-around test, only after its actions pass the four-lap test
(`safety.undo.every-action-on-the-rule-has-a-four-lap-test`), and leaves the "waiting for the
app" list in the same commit.
