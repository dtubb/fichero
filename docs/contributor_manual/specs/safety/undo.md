# Undo: take back my last step. Design Spec (#TBD)

> Milestone: undo-trash-rollback
> Manual: TBD. "Undo and Redo": what Command-Z takes back; that it is always your own step;
> what happens while you are typing; what "this has changed since" means and what to do then;
> how to take back an older step from the history list.
>
> Slice 1 of the safety set. Read `undo-trash-rollback.md` first. **Status: DRAFT,
> 2026-09-20.** Behaviours carry no tag and no issue yet, by instruction. Claims about the code
> are VERIFIED (line given), TRACED or INFERRED. Nothing was run. Engine paths are relative to
> the engine's source folder; app paths are given in full.

## Intent

Command-Z takes back **my last step**, in the library I am working in, and says what it took
back. It never takes back someone else's step. It never writes an old copy over later work: if
the thing has changed since, it stops and says so. Shift-Command-Z puts my step back, and the
thing that comes back is the same thing, not a copy. While I am typing, Command-Z belongs to
the text field, exactly as on every Mac, and never reaches the library.

This is the slice where a person loses work today. It is built first.

## Prior art

- **The Mac.** Undo is per person and per document window; typing undo belongs to the field
  editor; the Edit menu names the step ("Undo Typing", "Undo Move of 3 Items"). Finder's undo
  is app-wide and names the step. We follow both: the field owns typing; everything else is one
  named step at a time.
- **Shared editors** (Google Docs, Figma). Undo is always "my own last step", never the
  document's last step, and a step that can no longer apply is skipped or refused rather than
  forced. We adopt "mine only" and choose **refuse** over skip, because a silent skip on
  research data hides what happened.
- **Databases.** Optimistic concurrency: a change names the version it was made against and is
  refused if the version has moved. The source-model set already uses this for segments.
- **What we do differently.** Most apps keep the undo stack in memory in the app. Ours is a
  filtered view of the engine's one record, so that the app, the command line and an agent all
  see the same stack, and so that the server may be remote.

## What exists

| What | State | Evidence |
| --- | --- | --- |
| One route reverses any reversible action | built | VERIFIED `api/routes/system/actions_registry.py:235-332` |
| 155 of 244 actions reversible, each with a real inverse | built | VERIFIED by survey |
| The app replaces the system Undo and Redo with its own | built | VERIFIED `fichero/fichero/FicheroApp.swift:462-465` |
| A focused text field keeps Command-Z; an empty typing stack does nothing rather than fall through | built, and right | VERIFIED `fichero/fichero/App/Menus/UndoRouting.swift:45-50` |
| The image editor takes Command-Z ahead of the library | built, and right; it has no Redo | VERIFIED same file `:51`; no Redo per survey |
| Going Back outranks undo | built, and wrong | VERIFIED same file `:52-53` |
| No route to the window's undo manager | the registrations are dead | VERIFIED same file `:38-55` |
| Command-Z picks the library's newest reversible step, anyone's | built, and wrong | VERIFIED `fichero/fichero/Models/AuditStore.swift:119-121` |
| A redone step is skipped as an undo target | wrong | INFERRED from the same lines |
| The undo route checks write access only | anyone may undo anyone; a test pins this as intended | VERIFIED `actions_registry.py:305-322`; test per survey |
| No check that the thing is unchanged | later work is overwritten | VERIFIED `:297`; whole-row restore per survey |
| "Undone" is saved after the transaction closes | a crash or a second request can undo twice | VERIFIED `:324-325` |
| Redo and undo-of-redo replay recorded requests | #4957 | VERIFIED `:275-283` |
| The history list loads the whole record and sorts it in memory | slow at size | VERIFIED `:217` |
| No notice after a delete or a merge offers Undo | not built | VERIFIED by survey |
| The command line's audit command reads the older record; agents have no undo tool | wrong / not built | VERIFIED by survey |

## The two halves of the work

**Engine (no app change needed to be safe):** who may undo (A); refuse when changed (B);
"undone" inside the transaction (C); redo through the step's own inverse (D); the undo stack
worked out by the engine, paged in the database (E).

**App:** Command-Z routing (F); the dead registrations deleted (G); naming and showing the
step (H); typing and the image editor (I).

The engine half can ship alone. It makes every client safe at once, including agents.

## Behaviours

### A. Whose step it is

- `safety.undo.mine-only` — **[GAP]** (#5242) the undo route reverses a step only for the account that made it.
  Anyone else is refused, with a message that names who made the step. *Data:* the record
  already stores the actor on every row; the actor of the request comes from sign-in, never
  from the request body. *Existing data:* every old row already has its actor; rows made by
  "system" before accounts existed can be reversed only by the owner (next behaviour).
  *Test:* editor A makes a step; editor B's undo of it is refused and nothing changes; A's
  succeeds. The existing test that pins "any editor may undo anyone" is replaced, not deleted
  quietly: that was a past decision, and it goes to the maintainer as a question.
- `safety.undo.owner-may-reverse-anyone` — **[GAP]** (#5242) the owner of a library may reverse any step, but
  only from the history list, one chosen step at a time, and never with Command-Z. The reversal
  is a new recorded step that names both people: who reversed, and whose step it was. The
  person whose step was reversed can see that it was. *Data:* the reversal row carries the
  reverser as actor and points at the step reversed. *Existing data:* none to move. *Test:*
  owner reverses an editor's step from the list; the record shows both names; the owner's
  Command-Z never offers that step.
- `safety.undo.agents-and-runs-are-not-in-my-stack` — **[GAP]** (#5242) a step made by an AI agent's account or
  by a workflow run is never offered by my Command-Z, even if I started the run. Their work is
  taken back as a batch (`run-take-back.md`). *Test:* start a run that writes; press Command-Z;
  my own previous step is offered, not the run's.
- `safety.undo.viewers-have-no-stack` — **[GAP]** (#5242) an account that may not write has nothing to undo; the
  menu item is disabled. The → #4917 access rules apply to undo as to any write: a step on a
  thing I may no longer edit is refused. *Test:* remove A's access to a folder; A's undo of an
  earlier step inside it is refused.

### B. Never over the top of later work

- `safety.undo.refuses-when-changed` — **[GAP]** (#5242) a step is reversed only if it is still the newest live
  step on every thing it touched. If a later step, by anyone, touched any of the same things
  and has not itself been taken back, the undo is refused. Nothing is changed. The message says
  what changed, who changed it and when, and offers the thing's history (`versions-and-restore.md`).
  *Data:* every record row already lists the ids it touched; a small index from id to rows
  makes "is there a later live step on this id" one lookup. *Existing data:* the index is
  built from the existing record on first open, read-only to the record itself. *Test:* A
  edits a page; B edits the same page; A's undo is refused and B's text is byte-identical
  afterwards; B undoes; now A's undo succeeds.
- `safety.undo.version-is-the-second-lock` — **[GAP]** (#5242) where a kind of thing carries a version number
  (segments today, on the source-model branch; the other kinds of `versions-and-restore.md`
  as they gain versions), the reversal also names the
  version it expects and is refused if the version has moved. This catches a change that did
  not go through the record (a route still outside the action layer). *Data:* the version
  columns of the source-model set; no new store. *Existing data:* kinds without versions rely
  on the first lock alone. *Test:* bump a version behind the record's back; the undo is
  refused.
- `safety.undo.refusal-loses-nothing` — **[GAP]** (#5242) a refused undo leaves the step where it was in my
  stack, not skipped and not marked. I can look, decide, and try again. *Test:* after a
  refusal, the same step is still the next one offered.

### C. One step is undone once

- `safety.undo.marked-inside-the-transaction` — **[GAP]** (#5242) reversing a step and marking it reversed happen
  in one transaction. Either both are stored or neither. *Data:* the mark moves inside the
  registry's own transaction; it is written by the registry, not by the route afterwards.
  *Test:* force a failure after the inverse runs; neither the inverse nor the mark is stored.
  Two undo requests for one step at the same moment: exactly one succeeds, the other is refused
  as already undone.

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
  set (2026-09-20), which owns one user of the rule. On that set's branch the rule exists
  today as a switch an action opts into, turned on for segment actions only (VERIFIED in that
  worktree: `actions/registry.py:185`, `api/routes/document/segments.py:505`), so shipped
  actions are unchanged. This slice makes it THE rule of the route: on for every action, and
  the switch removed once the last action has moved. *Test:* the next behaviour.
- `safety.undo.every-action-on-the-rule-has-a-four-lap-test` — **[GAP]** (#5242) no action moves onto the rule
  without a test that runs do, undo, redo, undo through the real route and asserts on ROWS,
  not status codes: after the second undo the rows equal the rows after the first undo, and no
  live row is left that no later undo can remove. This is the source-model set's condition,
  adopted. *Test:* a guardrail: every action with the rule on is named by such a test.
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
- `safety.undo.a-new-step-clears-redo` — **[GAP]** (#5242) once I make a new step, my earlier undone steps are no
  longer offered by Shift-Command-Z. They remain in the history list. This is the Mac's rule.
  *Test:* undo, make a new step, Redo is disabled.

### E. The stack is worked out by the engine

- `safety.undo.the-engine-says-what-is-next` — **[GAP]** (#5242) one read call returns, for the account asking:
  the next step Command-Z would take back, the next step Redo would put back, and a short name
  for each. The app, the command line and an agent all use this call; none works it out for
  itself. A step that was redone counts as live again (today the app skips it). *Data:* worked
  out from the record: chains of reversals are followed to their newest row. *Test:* do, undo,
  redo; "next to undo" is that same step, not the one before it.
- `safety.undo.this-sitting-only` — **[GAP]** (#5242) Command-Z reaches back through my steps of **this sitting**:
  since I opened this library in this app, on this device. It does not reach into yesterday.
  Older steps of mine stay reversible from the history list, deliberately, one at a time, under
  the same locks. *Data:* the client sends a sitting id, made when the library is opened, with
  every step; the record stores it; it is attribution only, never an authorization input.
  *Existing data:* old rows have no sitting id, so they are never in a Command-Z stack and are
  still reversible from the list. *Test:* make a step, reopen the library, Command-Z is
  disabled, the step is in the list and can be reversed there.
- `safety.undo.one-stack-per-person-per-library` — **[GAP]** (#5242) the stack is not per window and not per
  pane. With three panes open on one library, Command-Z takes back my last step wherever it
  was, and shows me where (H). Two libraries open have two stacks; the front window's library
  decides. *Test:* a step in pane one, focus pane two, Command-Z reverses the step and pane one
  shows it.
- `safety.undo.history-is-paged-in-the-database` — **[GAP]** (#5242) the history list and the "what is next" call
  read only the rows they return, by index, newest first, filtered by account. *Data:* indexes
  on time, on account, and the id index of B. *Test:* load leg: with a million rows, both calls
  stay within the perf ratchet.

### F. What Command-Z does, in order

- `safety.undo.routing-order` — **[GAP]** (#5242) Command-Z goes to exactly one of these, in this order, and the
  menu item's title says which: (1) a focused, editable text field: its own typing undo; if
  its typing stack is empty, nothing, never the library; (2) the image editor, when open with
  uncommitted steps: its last step; (3) my next step from the engine; (4) nothing, disabled.
  *Test:* pure rule, off the main thread, every combination.
- `safety.undo.command-z-never-navigates` — **[GAP]** (#5242) going Back is not an undo. Command-Z never changes
  what is shown except to reveal the thing a reversal changed. Back keeps its own key. *Data:*
  the navigation case is removed from the routing. *Existing data:* none. *Test:* navigate into
  a folder, delete nothing, press Command-Z: the view does not move.

### G. One undo path in the app

- `safety.undo.no-library-step-lives-in-the-window-undo-manager` — **[GAP]** (#5242) no change to the library is
  registered with the window's undo manager. The sidebar delete, the workflow canvas and the
  canvas move and resize registrations are **deleted**, not wired. Those steps are already
  recorded actions, or become recorded actions, and come back through the one record.
  *Why delete rather than wire:* a second stack in the app could not know about other people,
  other devices, the command line or agents, could not survive a remote server, and would need
  its own refusal rules. One code path per thing. *Existing data:* none; these stacks live in
  memory. *Test:* a guardrail refuses a new registration outside text fields and the image
  editor; the three source-scan tests that cover the dead registrations are deleted with them.
- `safety.undo.canvas-moves-are-recorded-steps` — **[GAP]** (#5242) moving or resizing a note on a canvas, and
  editing a workflow's graph, are recorded actions with inverses, one step per gesture (a drag
  is one step, not one per frame). *Test:* drag, Command-Z, the note is back; the record has
  two rows.
- `safety.undo.every-action-says-how-it-comes-back` — **[GAP]** (#5242) every registered action is one of:
  reversible; sends its thing to the Trash; or carries a written reason why neither, in which
  case the app asks before doing it and says plainly that it cannot be taken back. *Data:* a
  field on the registration. *Test:* a guardrail over the registry replaces the path-string
  scan in `scripts/check_undo_coverage.py`.

### H. Saying what happened

- `safety.undo.menu-names-the-step` — **[GAP]** (#5242) the Edit menu reads "Undo Move of Letter 12", not "Undo".
  *Data:* each action registration gains a short name template, filled by the engine.
  *Test:* the name returned for a move includes the moved thing's name.
- `safety.undo.shows-what-it-took-back` — **[GAP]** (#5242) after an undo or redo, the app reveals the thing
  (selects it, scrolls to it) when it is in an open pane, and shows a short notice naming the
  step either way. Nothing is taken back off-screen in silence. *Test:* click-around.
- `safety.undo.offered-after-a-removal` — **[GAP]** (#5242) after a delete or a merge, a short notice offers
  Undo for a few seconds. It is the same step as Command-Z, not a second path. *Test:*
  click-around.
- `safety.undo.refusal-is-plain` — **[GAP]** (#5242) a refusal reads as a sentence a researcher can act on: "This
  page was changed by Ana at 14:02, after your edit. Your edit was not undone. See history."
  No status codes, no ids. *Test:* the message for each refusal kind.

### I. Typing, and the image editor

- `safety.undo.typing-belongs-to-the-field` — **[GAP]** (#5242) while an editable text field has focus, Command-Z
  and Shift-Command-Z are the system's own typing undo for that field, per field, with the
  grouping Mac users expect. Nothing in this set changes it. It never reaches the library's
  record, even when the typing stack is empty. *Data:* none; built. *Test:* the existing pure
  routing test, plus a mounted test: type, press Command-Z, the typing is undone and the record
  has no new row.
- `safety.undo.commit-hands-over` — **[GAP]** (#5242) when a field commits an edit (focus leaves, or the app
  saves), that whole edit becomes ONE step in my stack, named "Edit Transcription" or the like.
  With focus elsewhere, Command-Z takes the whole committed edit back, under the locks of B.
  With focus still in the field, Command-Z keeps undoing typing, and the next commit is a new
  step. The two never mix in one key press. *Test:* type, click away, Command-Z: the text
  returns to what it was before the edit, and the record shows the edit and its reversal.
- `safety.undo.commits-are-not-per-keystroke` — **[GAP]** (#5242) autosave must not turn one sitting at a field
  into dozens of steps. Commits from one uninterrupted stay in a field fold into one step.
  *Data:* the commit carries the field's editing-session id; the engine folds a commit into the
  previous row when the account, the thing and the session match and nothing else touched the
  thing between. *Test:* three autosaves in one stay; one step in the stack; undo returns to
  the text before the first.
- `safety.undo.image-editor-owns-its-steps` — **[GAP]** (#5242) inside the image editor, Command-Z drops the last
  uncommitted step and Shift-Command-Z puts it back (Redo does not exist there today). On Done,
  the whole session is one recorded step. Returning to the original is itself a step.
  *Test:* crop, rotate, Command-Z, Shift-Command-Z, Done, Command-Z outside the editor: the
  image is as it was before the session.

### J. The same from everywhere

- `safety.undo.command-line-and-agents` — **[GAP]** (#5242) the command line and the agent tools can ask "what is
  my next step to undo", take it back, put it back, and list their own history. Each acts as
  its own account: an agent can take back only the agent's own steps. The command line's
  audit command reads the one record. *Test:* CLI leg and MCP leg; an agent's undo of a
  person's step is refused.
- `safety.undo.iphone-and-ipad` — **[GAP]** (#5242) the system's undo gesture and the on-screen Undo call the same
  engine stack under the same rules. *Test:* iOS leg.

## Things to try by hand

1. Open a folder inside a folder. Press Command-Z. Nothing moves.
2. Move a document. The Edit menu reads "Undo Move of …". Press Command-Z. It moves back and is
   selected.
3. Type in a transcription. Press Command-Z. Only the typing goes. Click away. Press Command-Z.
   The whole edit goes.
4. Start a workflow, then rename a document, then press Command-Z while the workflow writes.
   The rename is undone; the workflow's work is untouched.
5. With a second account: both edit one page. The first person's Command-Z is refused with a
   sentence that names the second.
6. Create an entity, undo, redo, undo, redo. There is one entity, and it is the first one.

## Test matrix

| Leg | This slice? | Pins | File |
| --- | --- | --- | --- |
| Pure rule (Swift) | y | routing order; never navigates | beside `fichero/fichero/App/Menus/UndoRouting.swift` |
| Backend (pytest) | y | A to E, through the real route and a real database, two accounts | extends `fichero-server/tests/unit/api/test_action_undo.py` |
| Guardrail | y | every action says how it comes back; no library step in the window undo manager | replaces `scripts/check_undo_coverage.py` |
| MCP / CLI | y | J | the MCP and CLI suites |
| Click-around (Mac) | y | H, I, the six things above | the UI suite |
| iPhone / iPad | y | J | the iOS plans |
| Load | y | history paged | the perf suite |

## Open questions

See the questions file. From this slice: who may undo whose step; how far back Command-Z
reaches and whether it survives quitting; per person per library, not per window; redo keeps
the id.

## Triaged from the backlog (2026-10-04)
- `undo.coverage-guard-measures-the-engine-inverse` — **[GAP]** (#5109) the undo guard separates 'no inverse anywhere' from 'engine inverse exists, app has not adopted it'; 6b7f91d9f removed the six comment false-positives.
