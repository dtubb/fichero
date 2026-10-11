# Undo: take back my last step. Design Spec (#5242)

> Milestone: undo-trash-rollback
> Manual: TBD. "Undo and Redo": what Command-Z takes back; that it is always your own step;
> what happens while you are typing; what "this has changed since" means and what to do then;
> how to take back an older step from the history list.
>
> Slice 1 of the safety set. Read `undo-trash-rollback.md` first. **Status: DRAFT,
> 2026-09-20; reconciled with `../ui/undo-everywhere.md` on 2026-10-10.** Behaviours carry
> their tag and issue. Claims about the code are VERIFIED (line given), TRACED or INFERRED.
> Nothing was run. Engine paths are relative to the engine's source folder; app paths are
> given in full.
>
> **Who owns what.** This file owns the undo DESIGN: what is undoable, whose step it is, the
> engine's audit chain and its locks (never over later work, across windows, devices, agents
> and runs), one step undone once, redo, the command line and agents. The APP path (the one
> helper, the window's step stack, the Edit menu, typing and the image editor, naming,
> showing a refusal in words, iPhone and iPad, the coverage guard) is owned by
> `../ui/undo-everywhere.md` (#5658). A behaviour lives in one of the two files; the other
> links to it. The table "Moved on 2026-10-10" at the end lists what left this file.

## Intent

Command-Z takes back **my last step**, and says what it took back. It never takes back
someone else's step. It never writes an old copy over later work: if the thing has changed
since, by anyone, from any window or device, it stops and says so. Shift-Command-Z puts my
step back, and the thing that comes back is the same thing, not a copy. While I am typing,
Command-Z belongs to the text field, exactly as on every Mac, and never reaches the project.

In the app, "my last step" means the last step made **in this window**
(`undo.window` in `../ui/undo-everywhere.md`, a provisional decision of 2026-10-10). The
engine does not care which window asked: it judges every reversal against the one record,
under the rules below. That is what makes a per-window stack safe.

This is the slice where a person loses work today. It is built first.

## Prior art

- **The Mac.** Undo is per document window; typing undo belongs to the field editor; the Edit
  menu names the step. How the app follows this is `../ui/undo-everywhere.md`.
- **Shared editors** (Google Docs, Figma). Undo is always "my own last step", never the
  document's last step, and a step that can no longer apply is skipped or refused rather than
  forced. We adopt "mine only" and choose **refuse** over skip, because a silent skip on
  research data hides what happened.
- **Databases.** Optimistic concurrency: a change names the version it was made against and is
  refused if the version has moved. The source-model set already uses this for segments.
- **What we do differently.** Most apps keep the undo stack, and the data to undo with, in
  memory in the app. Ours keeps the data in the engine's one record. An app stack holds only
  the ids of record rows and asks the engine every time, so that the app, the command line and
  an agent all reverse steps the same way, and so that the server may be remote.

## What exists (engine)

The app's half is surveyed in `../ui/undo-everywhere.md`, "What exists".

| What | State | Evidence |
| --- | --- | --- |
| One route reverses any reversible action, and redoes when the row is itself an inverse | built | VERIFIED `api/routes/system/actions_registry.py:284-422` (2026-10-10) |
| 382 registered actions; 240 undoable with an inverse | built | counted from `registry.all()` on 2026-10-10 (`../ui/undo-everywhere.md`) |
| Record row ids are random (UUID v4 hex), so an id is never reused, even after a project is returned to a snapshot | built, and right | VERIFIED `models/__init__.py:158-160` |
| The undo route checks write access only | anyone may undo anyone; a test pins this as intended | VERIFIED `actions/registry.py:259-265`; test per survey |
| No check that the thing is unchanged | later work is overwritten; a test pins it | VERIFIED `actions_registry.py:393-396` (the inverse runs with no check); `fichero-server/tests/unit/api/test_action_undo.py:453` |
| "Undone" is saved after the transaction closes | a crash or a second request can undo twice | VERIFIED `actions_registry.py:414-415`, after `registry.invoke` returns |
| The database nests transactions and rolls the whole back when any inner level fails | built; what a set of reversals in one transaction needs | VERIFIED `db/__init__.py:1830-1845` |
| Redo and undo-of-redo replay recorded requests, except actions that opt into their own inverse | #4957 | VERIFIED `actions_registry.py:323-370`; opted in: segment actions and `document.delete` (`api/routes/document/documents.py:3858-3866`) |
| The history list loads the whole record and sorts it in memory | slow at size | VERIFIED by survey (2026-09-20) |
| The command line's audit command reads the older record; agents have no undo tool | wrong / not built | VERIFIED by survey |

## The two halves of the work

**Engine (this file; no app change needed to be safe):** who may undo (A); refuse when changed
(B); one step undone once, and a set undone whole (C); redo through the step's own inverse (D);
the stack for the command line and agents, worked out by the engine, and the history paged in
the database (E); what one step is (G); the same from everywhere (J).

**App (`../ui/undo-everywhere.md`):** the one helper; the window's step stack; the Edit menu's
order; typing and the image editor; naming; showing what was taken back; a refusal in words;
iPhone and iPad; the coverage guard.

The engine half can ship alone. It makes every client safe at once, including agents.

## Behaviours

### A. Whose step it is

- `safety.undo.mine-only` — **[GAP]** (#5242) the undo route reverses a step only for the account that made it.
  Anyone else is refused, with a message that names who made the step. *Data:* the record
  already stores the actor on every row; the actor of the request comes from sign-in, never
  from the request body. *Existing data:* every old row already has its actor; rows made by
  "system" before accounts existed can be reversed only by the owner (next behaviour).
  *Note:* this rule protects one PERSON from another. It does not protect one of my windows
  from another of my windows (same account); the lock of B does that. *Test:* editor A makes a
  step; editor B's undo of it is refused and nothing changes; A's succeeds. The existing test
  that pins "any editor may undo anyone" is replaced, not deleted quietly: that was a past
  decision, and it goes to the maintainer as a question.
- `safety.undo.owner-may-reverse-anyone` — **[GAP]** (#5242) the owner of a library may reverse any step, but
  only from the history list, one chosen step at a time, and never with Command-Z. The reversal
  is a new recorded step that names both people: who reversed, and whose step it was. The
  person whose step was reversed can see that it was. *Data:* the reversal row carries the
  reverser as actor and points at the step reversed. *Existing data:* none to move. *Test:*
  owner reverses an editor's step from the list; the record shows both names; the owner's
  Command-Z never offers that step.
- `safety.undo.agents-and-runs-are-not-in-my-stack` — **[GAP]** (#5242) a step made by an AI agent's account or
  by a workflow run is never offered by my Command-Z, even if I started the run, and even when
  the agent works inside my window (the chat). Their work is taken back as a batch
  (`run-take-back.md`). In the app this holds because only calls the person starts are
  registered on a window (`undo.one-path`); in the engine's "what is next" call (E) it holds by
  filtering on the account. *Test:* start a run that writes; press Command-Z; my own previous
  step is offered, not the run's.
- `safety.undo.viewers-have-no-stack` — **[GAP]** (#5242) an account that may not write has nothing to undo; the
  menu item is disabled. The → #4917 access rules apply to undo as to any write: a step on a
  thing I may no longer edit is refused. *Test:* remove A's access to a folder; A's undo of an
  earlier step inside it is refused.

### B. Never over the top of later work

- `safety.undo.refuses-when-changed` — **[PARTIAL]** (#5242) a step is reversed only if it is still the newest live
  step on every thing it touched. If a later step, by anyone, from any window, device, agent or
  run, touched any of the same things and has not itself been taken back, the undo is refused.
  A thing deleted since counts as touched: the refusal says it was deleted and where it is (the
  Trash). Nothing is changed. The message says what changed, who changed it and when, and offers
  the thing's history (`versions-and-restore.md`). This is THE cross-window rule: two windows
  of one person are two clients to the engine, and the later window's step wins until it is
  itself taken back. *Data:* every record row already lists the ids it touched; a small index
  from id to rows makes "is there a later live step on this id" one lookup. *Existing data:*
  the index is built from the existing record on first open, read-only to the record itself.
  *Test:* A edits a page; B edits the same page; A's undo is refused and B's text is
  byte-identical afterwards; B undoes; now A's undo succeeds. The same with A and B as two
  windows of one account. The test that pins the overwrite today
  (`test_action_undo.py:453`, `test_delete_undo_overwrites_later_claim_mutation_with_snapshot`)
  is inverted, not deleted. *Built (2026-10-10):* the record's lock, `later_step_in_effect` in
  `actions/undo.py`, for undo and redo (`fichero-server/tests/unit/api/test_action_undo.py`, `TestUndoRefusals`). *Not built:* the id
  index (a later-rows scan today), the words for a thing deleted since, the history offer; the
  overwrite test at `:453` changes the row outside the record, so it waits for the version lock.
- `safety.undo.version-is-the-second-lock` — **[GAP]** (#5242) where a kind of thing carries a version number
  (segments today, on the source-model branch; the other kinds of `versions-and-restore.md`
  as they gain versions), the reversal also names the
  version it expects and is refused if the version has moved. This catches a change that did
  not go through the record (a route still outside the action layer). *Data:* the version
  columns of the source-model set; no new store. *Existing data:* kinds without versions rely
  on the first lock alone. *Test:* bump a version behind the record's back; the undo is
  refused.
- `safety.undo.refusal-loses-nothing` — **[PARTIAL]** (#5242) a refused undo leaves the step where it was in my
  stack, not skipped and not marked. I can look, decide, and try again. Two refusals are final
  and say so, so that a client can drop the step: the step **was already taken back** (from the
  history list, another window, or another device), and the step **is no longer in the
  project's history** (the project was returned to a snapshot). The refusal carries which of
  the three it is as a field, never only as words. *Data:* `reason` on the refusal: `changed`,
  `already-undone`, `gone`. *Test:* after a `changed` refusal, the same step is still the next
  one offered; an `already-undone` answer names who took it back and when. *Built:* 404 and 409
  are declared on both undo routes with `{detail, reason, audit_id}` (also `not-undoable`), the
  messages rewritten as sentences, and a `changed` refusal leaves the step unmarked
  (`fichero-server/tests/unit/api/test_action_undo.py`). *Not built:* naming who took it back.

### C. One step is undone once; a set is undone whole

- `safety.undo.marked-inside-the-transaction` — **[PARTIAL]** (#5242) reversing a step and marking it reversed happen
  in one transaction. Either both are stored or neither. *Data:* the mark moves inside the
  registry's own transaction; it is written by the registry, not by the route afterwards.
  *Test:* force a failure after the inverse runs; neither the inverse nor the mark is stored.
  Two undo requests for one step at the same moment: exactly one succeeds, the other is refused
  as already undone. *Built:* the mark is written inside the set's transaction
  (`fichero-server/tests/unit/api/test_action_undo.py`, `test_a_failure_after_the_inverse_leaves_neither_inverse_nor_mark`). *Not
  built:* the concurrent test; the row is read before the write gate is taken.
- `safety.undo.a-set-is-undone-whole` — **[OK]** (#5658) the engine reverses a SET of rows in one
  request: newest first, in one transaction, all or none. If any one is refused (B, A, or a
  restore with nowhere to land), nothing is changed and the refusal names the thing that
  refused. The answer names the new rows the reversal wrote, and reversing THOSE rows as a set
  is the redo. A single undo is a set of one, so this route also delivers
  `safety.undo.marked-inside-the-transaction`. *Why:* a person's batch (delete three notes) is
  one step; reversing it row by row from the app would leave half a batch when the second row
  refuses, and the app would have to remember which half. Keeping it whole is the engine's job,
  not the app's. *Data:* none new; the database already nests transactions and rolls the whole
  back on any inner failure (VERIFIED `db/__init__.py:1830-1845`). *Existing data:* none.
  *Test:* three rows, the second made stale by a later step: the set is refused, all three are
  unchanged, and the refusal names the second; a set of three that succeeds, reversed again as
  a set, restores all three with their ids. Built: `POST /api/actions/audit/undo`
  (`fichero-server/tests/unit/api/test_action_undo.py`, `TestASetIsUndoneWhole`).

### D. Redo brings back the same thing

- `safety.undo.reversed-through-its-own-inverse` — **[GAP]** (#5242) when the step being taken back is itself a
  reversal or a redo, and its own action is reversible, it is reversed through ITS OWN inverse,
  worked out from what it actually did. A recorded request is replayed only when the step has
  no inverse of its own. *Why:* TRACED for entities with the registrations as they stand:
  undoing a create records a delete; a delete is reversible by a restore from its own
  snapshot; so redo becomes a restore of the same entity with the same id; undoing that redo
  falls back to replaying the delete, which is now right because the entity exists again. No
  action needs rewriting. *Existing data:* old chains in the record keep working; the rule
  only changes what the NEXT reversal does. *Where it stands:* agreed with the source-model
  set (2026-09-20), which owns one user of the rule. The rule exists today as a switch an
  action opts into (`redo_via_own_invert`), on for segment actions and `document.delete`
  (VERIFIED `actions_registry.py:338`; `documents.py:3858-3866`), so other actions are
  unchanged. This slice makes it THE rule of the route: on for every action, and the switch
  removed once the last action has moved. *Test:* the next behaviour.
- `safety.undo.every-action-on-the-rule-has-a-four-lap-test` — **[GAP]** (#5242) no action moves onto the rule
  without a test that runs do, undo, redo, undo through the real route and asserts on ROWS,
  not status codes: after the second undo the rows equal the rows after the first undo, and no
  live row is left that no later undo can remove. This is the source-model set's condition,
  adopted. The app's build order (`../ui/undo-everywhere.md`) wires a domain only after its
  actions pass this test. *Test:* a guardrail: every action with the rule on is named by such a
  test.
- `safety.undo.redo-keeps-the-id` — **[GAP]** (#5242) what the rule promises about ids, precisely, in three
  parts. **(1) Always:** the thing a step was ABOUT comes back under the id it had. Redoing a
  create restores the same thing; it never makes a second one; everything that pointed at it
  still does. **(2) Always:** no lap leaves a stray. Whatever a redo makes, the next undo
  removes all of it. **(3) The aim, not yet true everywhere:** things a step makes as a
  BY-PRODUCT also keep their ids. Today, on the source-model branch, the parts of a split, the
  copies of a carry and a proposed match get NEW ids on each redo and are cleaned up correctly
  on the next undo (their second review, 2026-09-20). That is safe, because of the first lock:
  if anything had come to point at an old by-product (an annotation on a part), a later live
  step would have touched it and the undo that removed it would have been refused. It becomes
  part (1) when those inverses remove softly and the redo restores, as create already does.
  Until then such an action says so in its registration, and its four-lap test asserts
  "nothing left over" instead of "same ids". *Test:* create an entity; link a statement to it;
  undo both; redo both; the statement points at the original id and exactly one entity exists.
  For a split: after each lap exactly one live segment covers the line, or exactly the parts
  do, never both.
- `safety.undo.a-restore-checks-where-it-lands` — **[GAP]** (#5242) a step that brings something back (an undo of
  a delete, an unmerge, an unsplit, a Put Back, a redo) first checks that what it restores INTO
  still exists and is live: the folder, the document, the pass, the parent. If not, it refuses
  with a reason, and brings nothing back into a place where it would be invisible. *Why:* the
  source-model review found that undelete, unmerge and unsplit do not check that the pass or
  the parent is still live, so a segment can return into a deleted pass and never be seen.
  The same holds for any kind. *Test:* delete a thing; delete its container; undo the first
  delete: refused, with the container named; put the container back; now it succeeds.
- `safety.undo.inverses-are-locked-too` — **[GAP]** (#5242) an inverse obeys the two locks like any other step.
  It names the versions it expects of everything it will change or remove, and it never
  hard-deletes something a later step has touched. On the source-model branch merge, split
  and carry take no expected version, and neither do unmerge, unsplit and uncarry; unsplit
  hard-deletes the parts it is given even if someone has since edited or annotated one
  (VERIFIED by that set's review). Agreed with that set: all six take the token. *Test:* split;
  someone annotates a part; undo the split: refused, the part and its annotation untouched.
- `safety.undo.redo-is-refused-when-changed` — **[GAP]** (#5242) redo obeys the same two locks as undo (B).
  *Test:* undo an edit; someone else edits the thing; redo is refused.

That a new step clears Redo is the app's stack rule (`undo.redo.new-step-clears`).

### E. The stack outside the app, and the history

- `safety.undo.the-engine-says-what-is-next` — **[GAP]** (#5242) one read call returns, for the account and
  sitting asking: the next step an undo would take back, the next step a redo would put back,
  and a short name for each. The command line and agents use it; they have no window. The app
  does not use it for Command-Z (its stack is the window's, `undo.window`); it uses the same
  call's names and filters for the history list. A step that was redone counts as live again
  (today the app's history-based Command-Z skips it). *Data:* worked out from the record:
  chains of reversals are followed to their newest row. *Test:* do, undo, redo; "next to undo"
  is that same step, not the one before it.
- `safety.undo.this-sitting-only` — **[GAP]** (#5242) a quick undo reaches back through my steps of **this
  sitting** only. For the command line and an agent, a sitting is one session, named by a
  sitting id the client sends with every step; the record stores it as attribution only, never
  as an authorization input. In the app the same boundary holds by construction: a window's
  stack lives in memory and ends with the window or the app (`undo.window`). Older steps stay
  reversible from the history list, deliberately, one at a time, under the same locks.
  *Existing data:* old rows have no sitting id, so they are never in a quick-undo stack and are
  still reversible from the list. *Test:* make a step from the command line, start a new
  session, `undo` finds nothing, the step is in the list and can be reversed there.
- `safety.undo.history-is-paged-in-the-database` — **[GAP]** (#5242) the history list and the "what is next" call
  read only the rows they return, by index, newest first, filtered by account. *Data:* indexes
  on time, on account, and the id index of B. *Test:* load leg: with a million rows, both calls
  stay within the perf ratchet.

Which stack the app's Command-Z reads, and how the window and the history list relate, is
`undo.window` and its provisional decision in `../ui/undo-everywhere.md`.

### G. What one step is

- `safety.undo.canvas-moves-are-recorded-steps` — **[GAP]** (#5242) moving or resizing a note on a canvas, and
  editing a workflow's graph, are recorded actions with inverses, one step per gesture (a drag
  is one step, not one per frame). *Test:* drag, Command-Z, the note is back; the record has
  two rows.
- `safety.undo.every-action-says-how-it-comes-back` — **[GAP]** (#5242) every registered action is one of:
  reversible; sends its thing to the Trash; or carries a written reason why neither, in which
  case the app asks before doing it and says plainly that it cannot be taken back. *Data:* a
  field on the registration. The coverage guard's "one-way by design" list
  (`undo.guard.three-lists`) takes its reason from this field for every route that invokes an
  action, and keeps its own reason only for routes that invoke none (reads, sign-in). *Test:*
  a guardrail over the registry.
- `safety.undo.commits-are-not-per-keystroke` — **[GAP]** (#5242) autosave must not turn one sitting at a field
  into dozens of steps. Commits from one uninterrupted stay in a field fold into one step.
  *Data:* the commit carries the field's editing-session id; the engine folds a commit into the
  previous row when the account, the thing and the session match and nothing else touched the
  thing between, and answers the SAME row id, so an app stack that already holds that id
  coalesces rather than adds a step (`undo.typing.commit-is-one-step`). *Test:* three autosaves
  in one stay; one step in the stack; undo returns to the text before the first.

### J. The same from everywhere

- `safety.undo.command-line-and-agents` — **[GAP]** (#5242) the command line and the agent tools can ask "what is
  my next step to undo", take it back, put it back, and list their own history. Each acts as
  its own account: an agent can take back only the agent's own steps. The command line's
  audit command reads the one record. *Test:* CLI leg and MCP leg; an agent's undo of a
  person's step is refused.

A move or copy between projects is undone as ONE transfer by the engine, both sides or
neither; that rule is `transfer.action.undo-move` and `transfer.action.undo-copy` in
`../source/moving-between-projects.md`, under the locks of B.

## Things to try by hand

1. Type in a transcription. Press Command-Z. Only the typing goes. Click away. Press Command-Z.
   The whole edit goes.
2. Start a workflow, then rename a document, then press Command-Z while the workflow writes.
   The rename is undone; the workflow's work is untouched.
3. With a second account: both edit one page. The first person's Command-Z is refused with a
   sentence that names the second.
4. With two windows of one account: rename a note in each. Command-Z in the first window is
   refused with a sentence; Command-Z in the second works; now the first works.
5. Create an entity, undo, redo, undo, redo. There is one entity, and it is the first one.

The app's own things to try (the menu's title, Back never undone, a refusal shown) are in
`../ui/undo-everywhere.md`.

## Test matrix

| Leg | This slice? | Pins | File |
| --- | --- | --- | --- |
| Backend (pytest) | y | A to E, G, through the real route and a real database, two accounts, two clients of one account | extends `fichero-server/tests/unit/api/test_action_undo.py` |
| Guardrail | y | every action says how it comes back; four-lap test per action on the rule | over the registry |
| MCP / CLI | y | J | the MCP and CLI suites |
| Load | y | history paged | the perf suite |

The app's legs (pure Swift, availability, click-around, iPhone and iPad) are in
`../ui/undo-everywhere.md`.

## Open questions

See the questions file. From this slice: who may undo whose step; how far back Command-Z
reaches and whether it survives quitting; redo keeps the id. "Per person per library or per
window" is answered provisionally in `../ui/undo-everywhere.md` (per window).

**Answered** (design lead 2026-10-04, applying the spec's lean): Redo of a create returns the same thing with the same id, never a new copy.

## Moved on 2026-10-10

Reconciled with `../ui/undo-everywhere.md` (#5658). Each line left this file; the new owner
holds the behaviour, and nothing below is stated twice.

| Was here | Now | Why |
| --- | --- | --- |
| `safety.undo.one-stack-per-person-per-library` | `undo.window` (provisional: per window) | the two specs contradicted each other; ruled provisionally per window |
| `safety.undo.routing-order` | `undo.edit-menu` | the Edit menu is the app path |
| `safety.undo.command-z-never-navigates` | `undo.edit-menu.never-navigates` | same |
| `safety.undo.no-library-step-lives-in-the-window-undo-manager` | `undo.one-path.no-local-closures` | reversed: a window stack is allowed, but it holds only record ids, never data or closures |
| `safety.undo.menu-names-the-step` | `undo.naming` | naming is the app path; the words come from the registration |
| `safety.undo.shows-what-it-took-back` | `undo.shows-what-it-took-back` | app |
| `safety.undo.offered-after-a-removal` | `undo.offered-after-a-removal` | app |
| `safety.undo.refusal-is-plain` | `undo.refusal.in-words` | one owner for the sentence |
| `safety.undo.typing-belongs-to-the-field` | `undo.window.own-stack` | app |
| `safety.undo.commit-hands-over` | `undo.typing.commit-is-one-step` | app; the engine's folding stays here (`safety.undo.commits-are-not-per-keystroke`) |
| `safety.undo.image-editor-owns-its-steps` | `undo.image-editor` | app |
| `safety.undo.iphone-and-ipad` | `undo.ios` | app |
| `safety.undo.a-new-step-clears-redo` | `undo.redo.new-step-clears` | the app's stack rule |
| `undo.coverage-guard-measures-the-engine-inverse` (#5109) | `undo.guard.measure`, `undo.guard.three-lists` | one guard spec |
