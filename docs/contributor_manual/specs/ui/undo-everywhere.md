# Undo everywhere: one way back for every change, from the window that made it. Design Spec (#5658)

> Milestone: undo-trash-rollback
> Manual: TBD. "Undo and Redo" must tell a researcher: Command-Z takes back the last change
> made in this window, and the menu names it ("Undo Move", "Undo Delete 3 Items"); Shift-Command-Z
> puts it back; a change made in another window stays with that window; when someone or
> something has changed the thing since, Fichero says so in a sentence and changes nothing;
> what cannot be undone (exports, sign-in, running a job, emptying the Trash) and why; where
> older changes can still be taken back (the history list).
>
> **Status: DRAFT, 2026-10-10.** The app half of taking things back. The engine half (whose
> step it is, never over later work, redo keeps the id) is `../safety/undo.md` (#5242), which
> this spec builds on and does not repeat. Deleted things and the Trash belong to
> `../safety/trash.md`, and moves and copies between projects to
> `../source/moving-between-projects.md`, which is being written alongside this spec.
> Every claim about the code is marked **VERIFIED** (read in the file, line given) or
> **INFERRED**. Nothing was run except the registry and contract counts below, which were
> taken by loading the engine's action registry and the committed `openapi.json` on
> 2026-10-10 at `2273d3e26`.
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
ask the engine to reverse that exact row and nothing else.

## Prior art

- **The Mac.** Undo belongs to the window or document, and the Edit menu names the step
  ("Undo Typing", "Undo Move of 3 Items"). `UndoManager` keeps the redo stack and clears it
  when a new step is made. A group of changes registered together is undone as one. We adopt
  all of this and do not build a stack of our own.
- **Shared editors** (Google Docs, Figma). Undo is "my own last change", never the document's
  last change, and a change that can no longer apply is refused or skipped. We refuse, as
  `../safety/undo.md` already rules, because a silent skip in research data hides what happened.
- **Optimistic concurrency.** Each change names the version it was made against, and a stale
  change is refused with HTTP 409. The engine already answers 409 for a refused action
  (`ActionRefused`, f9a4e9ba3). This spec makes the app read that answer.
- **What we do differently.** The window's stack holds only **audit row ids** and never an
  app-side copy of the data. The engine stays the one record and the one judge of whether a
  reversal is still safe. This is why the stack can be per window without becoming a second
  source of truth. It answers the objection in `../safety/undo.md` §G (see Open question 1).

## What exists (2026-10-10, `2273d3e26`)

| What | State | Evidence |
| --- | --- | --- |
| One engine route reverses any audited row, and redoes when the row is itself an inverse | built | VERIFIED `fichero-server/src/fichero_server/api/routes/system/actions_registry.py:284-410` |
| 382 registered actions; 240 undoable with an inverse | built | counted from `registry.all()` |
| An action refusing because the world moved on answers 409 with its reason in words | built for one action (`finddocs`), shape ready for all | VERIFIED `actions/registry.py:198`, route `:402-403`; test `fichero-server/tests/unit/finddocs/test_find_documents_to_spec.py::test_finddocs_redo_of_an_accept_a_later_run_replaced_is_refused_in_words` |
| The undo route's other refusals are developer words ("Action is not undoable: x") | wrong for a person | VERIFIED `actions_registry.py:321, 350, 367-398` |
| 409 is not declared on the undo route in the contract (only 200, 422) | so the generated client hands the app `.undocumented` | VERIFIED `fichero-server/tests/contracts/openapi.json`, path `/api/actions/audit/{audit_id}/undo` |
| `ActionUndo`: registers a step by audit id, files the redo correctly despite the async engine call | built and tested | VERIFIED `fichero/fichero/Models/ActionUndo.swift`; `fichero/Tests/Unit/general/Models/ActionUndoTests.swift` (7 tests) |
| `AuditedAction.run`: invoke, then `ActionUndo.register` | built, used by the Hands verbs | VERIFIED `fichero/fichero/Models/AuditedAction.swift:5-24` |
| 22 call sites of `ActionUndo.register`/`AuditedAction.run`, written in five shapes | scattered | `grep` over `fichero/fichero` |
| Sidebar delete calls `document.delete` and then registers a closure that calls `restoreDocument` | a second path that bypasses the engine's undo row | VERIFIED `fichero/fichero/Views/Sidebar/Components/SidebarActions.swift:230-246` |
| Canvas move/resize and the workflow canvas register app-state closures on the window's manager | a second path | VERIFIED `…/Canvas/Engine/CanvasInteractionController+Undo.swift:42-77`; `…/Workflow/Canvas/WorkflowCanvasView.swift:4-24, 230-237` |
| The Edit menu replaces the system Undo/Redo with its own | built | VERIFIED `fichero/fichero/FicheroApp.swift:489-491` |
| Its Undo never calls the window's `UndoManager`: it routes to typing, the image editor, navigation Back, or `AuditStore.undoLast()` | so registrations are unreachable outside a text field | VERIFIED `fichero/fichero/App/Menus/FocusedCommands/FocusedCommandButtons+UndoNavigation.swift:128-174`; `fichero/fichero/App/Menus/UndoRouting.swift:38-55` |
| `AuditStore.undoLast()` reverses the newest undoable row of the **always-there project**, by anyone | wrong project, wrong person | VERIFIED `FocusedCommandButtons+UndoNavigation.swift:58, 64`; `fichero/fichero/Models/LibraryManager.swift:658-660`; `fichero/fichero/Models/AuditStore.swift:119-121, 160-166` |
| `invokeAction` records every audited call into a single-level `LastAction` | a third, global holder | VERIFIED `fichero/fichero/Services/ActionInvokeService.swift:62-69` |
| A refused undo is silent in `ActionUndo` (`try?`) and reads "Undo failed (409)" in `AuditStore` | the engine's sentence is lost | VERIFIED `ActionUndo.swift:76`; `AuditStore.swift:94-95`; `ActionInvokeService.swift:119-121` |
| A test pins that an entity-delete undo overwrites a later claim edit | the engine half of cross-window safety is missing | VERIFIED `fichero-server/tests/unit/api/test_action_undo.py:453` (`test_delete_undo_overwrites_later_claim_mutation_with_snapshot`); #5242 |
| The undo coverage guard counts files that name an operation, not calls that register | measures the wrong thing | VERIFIED `scripts/check_undo_coverage.py` docstring; #5109 |

## The design

### One helper

There is one helper, named here `UndoableChange` (the name is not fixed). Every call a person
starts that changes project data goes through it:

1. It runs the call through the generated client, never a hand-written URL.
2. It reads the audit row id or ids the answer names (see "Every answer names its row" below).
3. It registers one step on **the window's step stack**, named with the action's words. A
   batch registers one step that holds several ids.
4. On undo, it asks the engine to reverse those ids, newest first and one at a time. The redo
   is filed during the undo handler, as `ActionUndo` already does
   (`ActionUndo.swift:12-19`), and it inverts the rows the undo wrote.
5. On a refusal, it shows the engine's sentence in the window and leaves the step where it
   was.
6. It records the project the step belongs to, and looks up that project's live service at
   undo time, never at registration. This matters after an engine restart and after the
   window switches project.

`ActionUndo` becomes the helper's core, because its redo bookkeeping is right and tested.
`AuditedAction`, `ReadingChoice`, `WorkingPassChoice`, `SegmentEdit`, `ReadingOrderStore`,
`ArtifactService+RegionCuration`, `SourceDirection` and the view call sites call the helper
instead. The sidebar, canvas and workflow-canvas closures are deleted and replaced by helper
calls on the actions that already exist (`document.delete`, `canvas.item.update`,
`canvas.layout.save`, `workflow.patch`, all undoable with an inverse).

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
scene-focused value. It is separate from the system manager that text fields use for typing,
so typing steps and project steps never mix in one stack (Open question 2). The Edit menu
decides by focus, in this order:

1. An editable text field has focus: its own typing undo. If it has nothing to undo, the menu
   item does nothing; it never falls through to a project step (unchanged,
   `UndoRouting.swift:45-50`).
2. The image editor is open with uncommitted steps: its last step (unchanged).
3. Otherwise, the key window's step stack. The title is the stack's own
   `undoMenuItemTitle` ("Undo Move"), and Redo's title is `redoMenuItemTitle`.
4. Nothing is left: the item is disabled.

Navigation Back leaves Command-Z (`../safety/undo.md` `safety.undo.command-z-never-navigates`).
`AuditStore.undoLast()` and `LastAction` stop driving Command-Z. The history list
(`AuditHistoryView`) keeps its deliberate, one-row-at-a-time reversal, under the rules of
#5242.

### Across windows, projects and restarts

- **Another window changed the same thing.** The step stays in the window that made it. Its
  undo goes to the engine, and the engine refuses when a later live step touched the same
  thing (`safety.undo.refuses-when-changed`, #5242). The app shows that sentence. Until #5242
  lands, the engine restores its snapshot over the later change; see `undo.cross-window`.
- **The window switched to another project.** The step keeps its project. Command-Z still
  reverses it in the project it was made in, and the menu says which ("Undo Move in
  Marshall Diaries"), but only when that project is not the one the window is showing.
- **A project closes.** Every window drops that project's steps, because the helper registers
  each project's steps against one target per project and calls
  `removeAllActions(withTarget:)` for it.
- **The engine restarts.** Audit rows live in the project's own database, so the ids survive
  the restart. The helper looks up the project's live service when the undo runs, so a
  reconnected engine is used and a stale one never is.
- **The app quits.** The stack is gone. This is the Mac's rule and matches "this sitting"
  (`safety.undo.this-sitting-only`). Older steps stay reversible from the history list.

### Batches

A change a person makes to several things at once is **one step**. The engine's own batch
actions (one call, one audit row: `claim.batch_transition`, `document.batch_exclude`, …) are
used where they exist. Where the app makes N calls, the helper wraps them in one group, holds
the N ids, and on undo reverses them **in reverse order, one after another**. If one is
refused, it stops and says how many were taken back, which one was refused, and why. The step
stays on the stack with only the ids that were not reversed, so pressing Command-Z again tries
the rest. Redo replays the batch forwards under the same rule.

### Moves between projects

A move between projects writes to two projects' records: the copy lands in the destination and
the original leaves the source, as `../source/moving-between-projects.md` defines it. It is
**one step** in the window that made it, holding (project, audit ids) for each side. Undo
reverses the destination side first and then the source side. If the source side refuses, the
destination side is put back, so the thing never ends up in neither project or in both. The
menu reads "Undo Move to “Project B”". Copies and aliases are one step in the same way. The
Trash of each project follows that spec and `../safety/trash.md`.

## Behaviours

### One path

- `undo.one-path` — **[GAP]** (#5658) every person-initiated call that changes project data
  and whose answer names an audit row registers Command-Z through one helper, and nothing
  else registers project steps. Today there are 22 helper-shaped call sites in five shapes,
  three app-state closures, and a global `LastAction`. *Test:* a guardrail (`undo.guard.no-bypass`)
  and a pure Swift test of the helper against a fake engine.
- `undo.one-path.every-answer-names-its-row` — **[PARTIAL]** (#5658) every mutating route that
  wrote audit rows names them in its answer, in the declared `X-Fichero-Audit-Ids` header (or
  the existing `audit_id` field). 20 operations do so today and 160 audited routes do not.
  *Test:* pytest over the contract: every mutating operation whose handler invokes an audited
  action declares the header; one test per domain reads it back.
- `undo.one-path.no-local-closures` — **[BROKEN]** (#5658) no view registers an undo that
  changes data through anything other than the engine's undo route. Sidebar delete restores
  through `restoreDocument` instead of reversing its own `document.delete` row
  (`SidebarActions.swift:235-245`), so the restore writes no inverse row and has no redo. The
  canvas and workflow canvas register app-state closures. All three move onto the helper.
  *Test:* the guardrail refuses `registerUndo(withTarget:)` outside the helper, text editing
  and the image editor.
- `undo.one-path.reachable` — **[GAP]** (#5658) every undoable change a person can make in the
  app can also be taken back from the app: from the Edit menu in the window that made it, and
  from the history list afterwards. A change with no way back says so before it runs
  (`safety.undo.every-action-says-how-it-comes-back`). *Test:* click-around for each domain in
  the build order.

### Naming

- `undo.naming` — **[PARTIAL]** (#5658) the step is named with the action's words, the way a
  person would say it: "Undo Move", "Undo Rename", "Undo Delete Note". `ActionUndo` already
  takes a name from each call site. The Edit menu today derives "Undo Merge" from the dotted
  action name of the newest audit row (`FocusedCommandButtons+UndoNavigation.swift:111-124`).
  The helper takes a typed name (verb + object noun) and never a dotted action id. *Test:*
  pure Swift, a name for every action in the build order.
- `undo.naming.counts` — **[GAP]** (#5658) a step over several things counts them: "Undo
  Delete 3 Items", "Undo Move 12 Pages". One thing is named by its kind ("Undo Delete Note").
  *Test:* pure Swift, 1, 2 and many.

### The window

- `undo.window` — **[BROKEN]** (#5658) Command-Z in a window reverses that window's last
  step. Today the Edit menu never calls a window's undo manager. When no text field has focus
  it reverses the newest row in the always-there project's history, whoever made it and
  whichever project the window shows (`FocusedCommandButtons+UndoNavigation.swift:58-64, 149`;
  `LibraryManager.swift:658-660`). *Test:* click-around: make a step in window A, focus window
  B, press Command-Z, and A's step is untouched.
- `undo.window.own-stack` — **[GAP]** (#5658) the helper's stack is separate from the typing
  stack, so Command-Z in a text field never reaches a project step and a project step never
  swallows typing. *Test:* mounted test: register a step, focus a field, type, then Command-Z
  undoes only the typing and the record has no new row.
- `undo.edit-menu` — **[PARTIAL]** (#5658) the Edit menu reads, in order: typing, then image
  editor, then the window's stack, then disabled, with titles from the stack. The text-field
  and image-editor routes are built and tested (`fichero/Tests/Unit/general/App/UndoRoutingPolicyTests.swift`).
  The window-stack route and its titles are not built. *Test:* extend the pure routing test.

### Across windows

- `undo.cross-window` — **[GAP]** (#5242) if another window, device, agent or run changed the
  thing after this window's step, the undo is refused and changes nothing. The engine half is
  #5242. Today the engine restores its snapshot over the later change, and a test pins that
  (`test_action_undo.py:453`). *Test:* backend: two clients, A edits, B edits, A's undo
  answers 409 and B's edit is unchanged. Click-around: the same with two windows.
- `undo.cross-window.others-see-the-result` — **[PARTIAL]** (#5658) after an undo or redo,
  every other window showing the thing updates through the change stream, with no manual
  refresh. The stream exists (`harness/observable-data-layer.md`). Some call sites still
  re-read by hand (`afterChange` in `AuditedAction.swift:10-21`). *Test:* click-around: undo in
  A, and B's row changes.
- `undo.cross-project` — **[GAP]** (#5658) a step stays tied to its project. If the window has
  switched to another project, Command-Z still reverses the step in the project it was made
  in, and the title names that project. When the project closes, its steps leave every window.
  *Test:* pure Swift with two fake projects; close one, and its steps are gone while the
  other's remain.

### Refusal

- `undo.refusal` — **[BROKEN]** (#5658) when the engine refuses an undo or redo, the window
  shows the engine's sentence and the step stays where it was. Today 409 is not declared on
  the route, so the generated client returns `.undocumented`. `ActionUndo` swallows the error
  (`try?`, `ActionUndo.swift:76`) and `AuditStore` shows "Undo failed (409)"
  (`AuditStore.swift:95`). *Test:* declare 409 with its `detail` in the contract; a Swift test
  with a fake engine that refuses checks that the sentence reaches the window and the step is
  still offered.
- `undo.refusal.in-words` — **[PARTIAL]** (#5658) every refusal from the undo route is a
  sentence a researcher can act on, naming what changed and, once #5242 lands, who changed it
  and when. `ActionRefused` does this (f9a4e9ba3), but the route's other refusals are developer
  words ("Action is not undoable: x", "Inverse/replay action unknown: y",
  `actions_registry.py:321-398`). *Test:* pytest, one per refusal kind, checks the message
  contains no action id and no status code.

### Batches

- `undo.batches` — **[PARTIAL]** (#5658) a change made to several things at once is one step.
  `ReadingOrderPicker` groups N registrations into one "Continue Flow" step
  (`fichero/fichero/Views/Components/ReadingOrderPicker.swift:166-185`). Deleting several notes
  makes N calls and registers nothing (`fichero/fichero/Views/Library/Notes/NoteListView.swift:136-150`).
  *Test:* pure Swift: delete 3, then one Command-Z brings back all 3.
- `undo.batches.in-order` — **[GAP]** (#5658) a batch is reversed newest first, one row after
  another, and stops at the first refusal, saying how many came back. Today each grouped
  registration starts its own engine call, so the order is not fixed (`ActionUndo.swift:75-77`).
  *Test:* a fake engine that refuses the second of three: one is reversed, the refusal is
  shown, and the step still holds two.

### Redo

- `undo.redo` — **[OK]** Shift-Command-Z reverses the row the undo wrote, and undo, redo,
  undo walks the chain one row at a time. *Tests:* `ActionUndoTests.redoIsRegisteredDuringTheUndo`,
  `.redoInvertsTheUndosOwnRow`, `.theChainKeepsGoing` (in
  `fichero/Tests/Unit/general/Models/ActionUndoTests.swift:59-102`).
- `undo.redo.laps` — **[PARTIAL]** (#4957) four laps of do, undo, redo, undo leave the rows as
  after the first undo, with the same ids. Built for segment actions (`redo_via_own_invert`).
  The rest replay recorded requests (`safety.undo.reversed-through-its-own-inverse`, #5242).
  *Test:* the four-lap backend test for each action in the build order.
- `undo.redo.new-step-clears` — **[PARTIAL]** (#5658) a new step clears Redo. `UndoManager`
  does this itself, but no test pins it for the helper, whose redo is registered from inside
  an undo handler. *Test:* pure Swift: undo, register a new step, and Redo is disabled.
- `undo.redo.before-the-answer` — **[PARTIAL]** (#5658) a redo pressed before the engine has
  answered the undo does nothing and is logged. It never guesses a row. Built
  (`ActionUndo.swift:66-74`) but not tested; the menu should also show Redo as disabled until
  the answer arrives. *Test:* pure Swift with a slow fake engine.

### Engine restart

- `undo.engine-restart` — **[GAP]** (#5658) after the engine restarts, Command-Z still
  reverses the window's steps, because the audit rows are in the project's database and the
  helper looks up the live service at undo time. If a row no longer exists (the project was
  returned to a snapshot), the window says "This change is no longer in the project's history"
  and drops the step. Today each call site captures its service when it registers, so this is
  INFERRED to break after a reconnect. *Test:* integration: register, restart the dev engine,
  then undo succeeds; and with the row deleted, the sentence is shown and the step is gone.

### Moves between projects

- `undo.move-between-projects` — **[GAP]** (#5658) a move, copy or alias between projects is
  one step that holds both projects' rows. Undo reverses the destination side, then the
  source side. If either side refuses, the other is put back and the window says which side
  refused. *Test:* see the Test matrix; depends on `../source/moving-between-projects.md`.

### iPhone and iPad

- `undo.ios` — **[GAP]** (#5658) on iPhone and iPad, the system's undo gestures and the
  keyboard's undo key reach the same helper stack under the same rules
  (`safety.undo.iphone-and-ipad`). *Test:* iOS leg.

### The guard's measure

- `undo.guard.measure` — **[GAP]** (#5109) `scripts/check_undo_coverage.py` counts an operation
  as covered when an app call to its generated method sits inside a helper call. Naming the
  operation anywhere in a file that registers undo no longer counts. *Test:* the guard's
  self-test with a fixture: a call inside the helper is covered, and the same call beside it
  but outside is not.
- `undo.guard.three-lists` — **[GAP]** (#5658) the single known-gaps baseline is replaced by
  three lists, each entry with a reason: **one-way by design** (kept, with the reason the
  person is told); **needs an engine inverse** (each with an issue); **waiting for the app**
  (only shrinks). A route on no list and not covered fails. *Test:* the guard's self-test.
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
| Pure rule (Swift) | y | helper: naming, counts, batch order, stop-at-refusal, project targets, redo cleared, redo before answer | `fichero/Tests/Unit/general/Models/UndoableChangeTests.swift` (new), extends `ActionUndoTests.swift` |
| Availability (Swift) | y | Edit-menu routing: typing, image editor, window stack, disabled; titles from the stack | extends `fichero/Tests/Unit/general/App/UndoRoutingPolicyTests.swift` |
| Backend (pytest) | y | every audited route answers `X-Fichero-Audit-Ids`; 409 declared on the undo route; refusals in words; four laps per domain | `fichero-server/tests/unit/api/test_action_undo.py`, `tests/contracts/` |
| MCP | n | (agents' undo is `safety.undo.command-line-and-agents`) | |
| CLI | n | (same) | |
| Click-around (XCUITest, Mac) | y | each domain: do, Command-Z, Shift-Command-Z, title text | `fichero/Tests/UI/…` (subclass `FicheroUISessionTests`) |
| iPhone (iOS) | y | system undo gesture reaches the helper | `fichero/Tests/UI/ios` |
| iPad | y | same, with a keyboard | `fichero/Tests/UI/ipad` |
| Load (#4634) | n | | |
| Guardrail | y | `undo.guard.*` | `scripts/check_undo_coverage.py` self-test |

**Adversarial cases (each is its own test):**

1. **Undo after another window edited.** Window A renames a note. Window B renames it again.
   Command-Z in A is refused with a sentence, B's name stands, and A's step is still offered.
   B undoes; now A's undo succeeds. (Engine half: #5242.)
2. **Undo after an engine restart.** Register three steps, restart the engine, then undo all
   three. With one row removed behind the app's back, that step says it is gone and the others
   still work.
3. **Redo laps.** Do, undo, redo, undo, redo for create, update, delete and move of a document,
   note, claim and workflow. After every undo the rows equal the first undo's rows, ids are
   kept, and no stray row is left.
4. **Redo pressed twice, fast.** The second press does nothing until the first answer arrives,
   and never reverses the redo it just made.
5. **Typing, then Command-Z.** With a project step on the stack and a text field focused,
   Command-Z undoes the typing only. Click out, and Command-Z undoes the project step.
6. **Batch with a refusal in the middle.** Delete three notes; another window edits the second.
   Command-Z restores the third, is refused on the second and says so, and does not touch the
   first. Command-Z again is refused again with the same sentence.
7. **Undo of a move between projects.** Move a document from P to Q, then press Command-Z: it is
   back in P, not in Q, and not in either Trash. Then with Q's copy edited in another window,
   Command-Z is refused, and the document is in Q only, unchanged.
8. **Project closed.** Make a step in P, close P, and Command-Z does not offer it. Reopen P,
   and the step is in the history list, not the stack.
9. **Window switched project.** Make a step in P, switch the window to Q, and the menu reads
   "Undo … in P". Command-Z reverses it in P and Q is untouched.
10. **Two windows, one project, independent stacks.** A step in A is never offered in B.

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | the maintainer's "Undo and Redo" section (Manual: TBD above) |
| Contributor | developer docs | y | this spec; `docs/contributor_manual/guide/05-actions-audit-and-undo.md` gains "register through the helper" |
| AI / agent | MCP tool description | n | |
| Scripter | CLI `--help` | n | |
| Reference | capability/endpoint reference | y | the `X-Fichero-Audit-Ids` header, generated |

## Accessibility identifiers

- The Edit menu items: `edit.undo` and `edit.redo` (their titles are the stack's).
- The sentence shown when the engine refuses: `undo.refusal.notice`.

## Open questions

1. **One stack per window, or one per person per project?** `../safety/undo.md` proposes one
   stack per person per project and no project steps in any window's undo manager
   (`safety.undo.one-stack-per-person-per-library`,
   `safety.undo.no-library-step-lives-in-the-window-undo-manager`). This spec follows the
   maintainer's direction to register on the window that made the change.
   **Recommendation: per window.** It is the Mac's convention, and SwiftUI gives it for free.
   Safety's objection was a second stack that holds data and makes its own refusal rules. This
   stack holds only audit ids and asks the engine every time, so it is not a second source of
   truth. "Mine only" also becomes true by construction, because a window holds only the steps
   it made. The two specs should be reconciled in `../safety/undo.md` once this is ruled.
2. **The helper's own stack, or the system window manager?** The system manager is shared with
   text fields' typing (INFERRED: the field editor asks the window for its undo manager), so
   project steps and typing would interleave. **Recommendation: the helper owns one
   `UndoManager` per window**, published as a scene-focused value, and the Edit menu picks
   between it and typing by focus as it does today. Verify the INFERRED sharing first with
   the mounted test in `undo.window.own-stack`.
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
   handful of items are involved, so that undo is one engine call and not 500.

## Build order

1. **The helper**, with its stack per window, project targets, and refusal in words. This
   includes declaring 409 on the undo route. Route the Edit menu to it, and take `AuditStore.undoLast()`
   and `LastAction` off Command-Z. Move the existing 22 call sites onto it. Pins: `undo.one-path`,
   `undo.window*`, `undo.edit-menu`, `undo.refusal`, `undo.redo*`.
2. **Every answer names its row:** the `X-Fichero-Audit-Ids` header, and the 24 bypassing
   routes moved onto their actions. After this, the guard's new measure goes in (`undo.guard.*`).
3. **Documents and folders:** create, rename, move, reorder, duplicate, delete (sidebar
   closure deleted), Put Back. Entity folders get their inverse (needs-inverse list).
4. **Annotations.**
5. **Claims and entities**, including the batch curation inverses.
6. **Notes**, including multi-delete as one step and note links.
7. **Workflows:** the canvas closures are deleted; create, patch, delete, duplicate, reorder.
8. **Saved searches and bookmarks.**
9. **Kinds and registries:** classifications, epistemic statuses, claim kinds, entity types.
10. Then the rest of the needs-inverse list, by daily use. Moves between projects follow
    `../source/moving-between-projects.md` once its engine action exists.

Each domain lands with its click-around test and leaves the "waiting for the app" list in the
same commit.
