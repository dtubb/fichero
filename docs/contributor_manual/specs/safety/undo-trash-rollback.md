# Undo, Trash and Rollback: taking things back, as one system. Design Spec (#TBD)

> Milestone: undo-trash-rollback
> Manual: TBD. The user manual needs a "Taking things back" section, written for a researcher:
> what Command-Z takes back and what it never touches; where deleted things go, how to put them
> back, and what emptying the Trash really removes; how to see what a page or a statement used
> to say and return to it; how to take back everything one run did; and how to return a whole
> library to an earlier day.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT, first pass, 2026-09-20. This is the FOUNDATION of the
> safety set: the honest answer, the three words, the design on one page, what exists, the map
> of the slices, the build order, what gets deleted, and the questions. Nothing is approved.**
> The milestone name is proposed, not ruled; no GitHub milestone of that name exists yet, by
> instruction.
> Tags (when behaviours are tagged): **[OK]** built and tested · **[PARTIAL]** built, partly
> proven · **[GAP]** intended, never built · **[BROKEN]** code contradicts the rule.
> **Behaviours in this set are written in full but carry NO tag and NO issue yet.** Every one
> is designed and not built unless its line says otherwise. They are tagged and given issues
> after the maintainer rules on the questions. That is deliberate; do not "fix" it by adding
> tags without issues (the guardrail `scripts/check_spec_broken_has_issue.py` would, rightly,
> refuse them).
>
> Every claim about Fichero's own code is marked **VERIFIED** (read in the file, line given),
> **TRACED** (worked through by hand from code that was read, not run) or **INFERRED**. Nothing
> in this set has been run. Engine paths are relative to the engine's source folder
> (`fichero-server/src/fichero_server/`); app paths are given in full.

**Why this set has its own folder.** Taking things back is not a screen and it is not
plumbing. It reaches the engine (what is recorded and what can be reversed), the app (what a key
press does), the command line, the agent tools, and every kind of thing a library holds. A home
under `ui/` would hide the engine rules that make it safe. A home under `harness/` would hide
the promises a person is given. `harness/audited-action-layer.md` stays the spine: it says HOW
a change is made and recorded. This set says what a person may TAKE BACK, and it builds only on
that layer.

## The question, and the honest answer

The maintainer does not think undo, trash and rollback are done properly. **That judgement is right, and
the reason is the same in all three.** The engine has most of the parts. They were built one at
a time, by different hands, for different needs. They were never designed as one system, and
the half a person touches is the weakest half.

**What is wrong today, in plain words:**

1. **Command-Z does not mean "take back my last step".** In the library it goes Back a folder
   instead of undoing. When it does undo, it takes back the newest change in the whole library,
   whoever made it: another person, a workflow, or an AI agent. Several places in the app
   register an undo that the key can never reach.
2. **The app promises a Trash it does not have.** Deleting a document says "you can put it back
   later". The engine keeps the document safely. The app has no Trash to open, so there is no
   way back that works. Meanwhile the deleted document's statements and search entries carry on
   as if nothing happened.
3. **Undo can silently destroy later work.** Undoing an old edit writes the old copy over the
   top of everything done since, without asking and without saying so. Anyone who may edit may
   undo anyone else's work.
4. **There is no real rollback.** Nothing keeps earlier versions of a page or a statement. A
   workflow run cannot be taken back, and most of what a run writes does not even record which
   run wrote it. Library snapshots exist but leave out the original files, are not taken before
   the riskiest steps, and fail without a word. A library update that fails half way is logged
   as a warning and the library opens anyway.

**What it should be:** three plain ideas, one record underneath, and one rule that holds them
together.

## The three words

These are the words the manual, the menus and every slice of this set use. A non-programmer
should be able to hold all three.

| Word | What it means | How far back | Who |
| --- | --- | --- | --- |
| **Undo** | Take back **my last step**. Then the one before. | My own steps, in this sitting. | Only me, only mine. |
| **Trash** | **I removed a thing** and may want it back. | Until someone empties the Trash. | Whoever could see the thing can see it in the Trash. |
| **Rollback** | Return **this thing**, **this run's work**, or **this whole library** to how it was at a point in time. | As far as history is kept. | Anyone who may edit the thing; the whole library, only its owner. |

Undo is a reflex. Trash is a place. Rollback is a decision. They differ in how far back they
reach and in how deliberate they are, and that is why they are three things and not one.

**The one rule that holds them together: taking something back is itself a step.** It is
recorded, with who and when. It never rewrites the past. It can itself be taken back. Nothing
in this set deletes history to make the present look clean.

## The design on one page

**One record.** Every change already goes through the audited action layer and leaves one row
in one record (VERIFIED, `actions/registry.py`; described in
`docs/contributor_manual/specs/harness/audited-action-layer.md`). Undo, Trash and Rollback are
three ways of reading and acting on that one record. No second store is added. Two older
records are folded away (see "What gets deleted").

**Undo reads the record through a filter:** my steps, this sitting, newest first. The record
is shared by the whole library; the undo stack is personal. That filter is the entire
difference, and it is the thing that is missing today.

**Undo refuses rather than overwrites.** If the thing has changed since my step, undo stops
and says so. It never silently discards someone's later work. This needs each changeable thing
to carry a version number, which the source-model set has already built for segments.

**Redo brings back the same thing, not a copy.** Today redo replays the original request, so
redoing a "create" makes a second, different thing. Research data points at things by their
ids: a statement points at an entity, a note points at a line. So redo must return the same
thing with the same id.

**Trash is one rule for every kind.** Anything a person can name and would go looking for
goes to the Trash when deleted: a document, a folder, a note, a workflow, a run, a saved
search, an entity. Small edits (a moved box, a changed word, a tag) are undo only. A thing in
the Trash takes its dependants out of view with it, and brings them back when it is put back.

**Rollback stands on versions.** The source-model set keeps versions of segments and of the
artifacts that hold text. This set does not build a second version store. It extends the same
rule to the few other kinds that need it, and adds the screens: see what it said before,
return to it.

**A run is one step.** Everything a run writes carries the run's stamp, so its work can be
listed, reviewed, and taken back as one step next week. The same stamp serves work that ran on
another machine (the remote-compute set lands a job's results as the same records a local run
makes).

**The safety net is never skipped silently.** Before a step that cannot be reversed, the
engine takes a snapshot. If it cannot (no room on the disk), it refuses the step and says why.
It does not carry on without one.

**The record does not become a second copy of the research.** Today each edit to a
transcription stores the full text of the page twice in the record, for ever. With versions
kept as ordinary data, the record needs only to say which version came before and which after.

## What exists (summary; the full survey is in the working notes)

The survey behind this set is about 2,800 lines with file and line throughout. The points the
design rests on:

**Built, and good.**
- The audited action layer: 244 actions, 155 of them reversible, every one with a real inverse
  and none claiming a reversal it cannot deliver. One route reverses any of them. VERIFIED
  (`api/routes/system/actions_registry.py:235-332`).
- The record is tamper-evident: each row is chained to the one before with a keyed hash, and an
  outside anchor detects a record cut short. VERIFIED (`actions/audit_chain.py:27-44`,
  `:382-400`).
- Documents and folders are soft-deleted with who and when, for the whole subtree, and the
  engine has routes to list the Trash, restore and purge. VERIFIED
  (`api/routes/document/documents.py:2501-2524`).
- Image editing is the model to copy. Edits are stored as settings, not pixels. The original
  file is never opened for writing. Returning to the original is itself reversible. VERIFIED
  (`api/routes/ingest/image_editing.py:1615-1618`).
- Library snapshots exist, with a screen in Settings, a limit of ten, and pinning. Restoring one
  sets the current files aside rather than deleting them. VERIFIED (`db/storage_snapshots.py`,
  `fichero/fichero/Views/Settings/Snapshots/SnapshotsView.swift`).

**Wrong, and where.**
- Command-Z ranks going Back above undo. VERIFIED (`fichero/fichero/App/Menus/UndoRouting.swift:52-53`).
- Command-Z has no route to the window's own undo manager, so every undo the app registers
  there is unreachable. VERIFIED (same file, `:38-55`; the app replaces the system Undo and Redo
  at `fichero/fichero/FicheroApp.swift:462-465`).
- Command-Z picks the newest reversible change in the library with no filter on who made it.
  VERIFIED (`fichero/fichero/Models/AuditStore.swift:119-121`).
- The undo route checks neither who is asking nor whether the thing has changed since, and it
  marks a step as undone after the transaction has closed. VERIFIED
  (`api/routes/system/actions_registry.py:297`, `:305-325`).
- Redo, and undoing a redo, replay recorded requests instead of reversing what actually
  happened. VERIFIED (`:275-283`). On shipped actions this fails loudly: the second undo is
  refused and the redone thing is stranded. TRACED for entities
  (`api/routes/entity/entities.py:125-132`, `:153-161`, `:716-718`) and documents
  (`api/routes/document/documents.py:2765-2773`, `:418-423`); INFERRED for the other create
  actions. On segment split and carry it corrupts silently (traced by the source-model
  reviewer; not reachable from the app yet). This is #4957.
- The app has no Trash, although its delete dialog promises one. VERIFIED
  (`fichero/fichero/Views/Sidebar/Sections/SidebarDeleteConfirmation.swift:8-55`; the only
  restore call is at `fichero/fichero/Views/Sidebar/Components/SidebarActions.swift:216`).
- A deleted run is marked deleted and nothing reads the mark. VERIFIED by the survey
  (`workflows/activity_store.py:1297`, `:1311-1354`). This is #4960.
- The knowledge-graph reset would delete every curated entity, statement and link with no
  filter, no record and no confirmation. It is safe today only because it is broken. VERIFIED
  (`api/routes/kg/rebuild.py:50-55` against `db/__init__.py:3306`). This is #4982. **Nobody is
  to repair the call as written.**
- A library update that fails is caught and logged as a warning, and the library opens half
  updated. VERIFIED (`db/migrations/schema.py:230-231`). This is #4983.
- There is no version history on the main line. It exists only on the unmerged source-model
  branch, for segments. VERIFIED by the survey.
- Two older undo records sit beside the action record and disagree with it (#4864).

## The slices, in build order

Each slice stands alone: it can be built, tested and shipped without the ones after it.

| # | File | What a person gains | Depends on |
| --- | --- | --- | --- |
| 1 | `undo.md` | Command-Z takes back my last step, never someone else's, never over the top of later work. Typing undo is untouched. | nothing |
| 2 | `trash.md` | A Trash you can open, put things back from, and empty. One rule for every kind. | nothing (better after 1) |
| 3 | `versions-and-restore.md` | See what a thing said before and return to it. | the source-model versions |
| 4 | `run-take-back.md` | Take back everything one run did, today or next week. | 1 (safe reversal), 2 (runs go to the Trash) |
| 5 | `safety-net.md` | A snapshot before every step that cannot be reversed; a library update that stops rather than half-applies; return the library to yesterday. | nothing |
| 6 | `the-record.md` | The record is checked, stays small, shows who did what, and maps to a standard. | 3 (versions let the record shrink) |

**Slice 1 comes first because it is where a person loses work today.** Its engine half and its
app half are separate pieces of work and are listed separately in that file. Slice 5 has two
items that do not wait for their slice: #4982 and #4983 are filed and should be fixed as soon
as their design here is agreed.

## What gets deleted as the paths are folded

One code path per thing. These go:

- **The window undo manager as a home for changes to the library.** The app's registrations
  for sidebar delete, workflow canvas edits and canvas move and resize are unreachable today.
  They are deleted, and those steps become ordinary recorded actions reversed through the one
  record. The system's own undo stays for exactly two things: typing inside a text field, and
  steps inside the image editor before they are committed. (Slice 1.)
- **The older mutation record and its undo route**, and the 30-second guess that tries to match
  its rows to the action record. Its rows are kept and readable; nothing new is written to it;
  its undo route first refuses what the action layer owns (#4864), then retires. (Slice 6.)
- **The data-repair rollback that walks the older record**, once data repairs run as recorded
  actions with a run stamp and are taken back the same way a run is. (Slice 4.)
- **The folder delete that hard-deletes every workflow, search or conversation inside it** with
  no record. It becomes the same Trash action as any other folder. (Slice 2.)
- **The undo coverage scan as it stands** (`scripts/check_undo_coverage.py`). It counts a route
  as covered when its path appears in a Swift file that mentions the undo manager. It is
  replaced by a check against the action registry: every action is reversible, or goes to the
  Trash, or states why neither. (Slice 1.)

Nothing here discards user data. Old records stay readable. Trashed documents already in a
library appear in the new Trash on first open.

## Requests to other specs

These are requests, not edits. The files belong to their authors.

- **To the source-model set** (`fabel-spec-writer`): (a) adopt one rule for redo in the shared
  undo route (a step is reversed through its own inverse when it has one), which this set
  specifies in `undo.md` for every action, so the segment-only fix now in hand becomes the
  general rule rather than a special case; (b) confirm that the version store built for
  segments and artifacts is THE version store, and that this set may extend the same tables'
  rule to notes, statements and entities rather than build another; (c) a deleted segment is
  "undo only" under this set's Trash rule (a person does not go looking for a line in a Trash);
  confirm that matches their intent; (d) questions 8, 17 and 23 (words in the record) collide
  with `the-record.md`; one joint proposal is written there.
- **To the remote-compute set:** `compute.land.undoable-as-one` and
  `compute.land.server-sets-the-maker` should cite the run stamp defined in `run-take-back.md`
  instead of defining a second one. A landed job is a run.
- **To `harness/audited-action-layer.md`:** `audit.undo-redo-is-generic` is tagged OK and
  describes replay as correct. After #4957 and the trace above, it is not. `audit.run-scoped-undo`
  and `audit.blame-and-rollback-view` are superseded by slices 4 and 6 here and should point to
  them. `audit.one-operation-has-one-undo` (#4864) is answered by "What gets deleted" above.
- **To `ui/menus-and-commands.md`:** it calls Command-Z through the record shipped. It is
  wired, and wrong in the four ways listed above. `undo.md` becomes the source for what
  Command-Z does.
- **To `ui/activity.md`:** deleted runs join the Trash (slice 2); a run's own "take back"
  control is slice 4.

## How this is tested from the maintainer's side

Each slice ends with a short list of things to try by hand, in words, in the running app: press
this, expect that. A source scan is not a test of any behaviour in this set. Where a behaviour
is about what a key press does, its test mounts the view or drives the app.

## Test matrix

| Leg | This set? | Pins | File |
| --- | --- | --- | --- |
| Pure rule (Swift) | y | the Command-Z routing order; the Trash rule by kind | slice 1, slice 2 |
| Availability (Swift) | y | Trash reachable from the sidebar; history reachable from the Inspector | slices 2, 3 |
| Backend (pytest) | y | every engine behaviour below, through the real routes and a real database | all slices |
| MCP | y | an agent can list its own steps, take one back, list the Trash, put back | slices 1, 2, 4 |
| CLI | y | the same four, from the command line | slices 1, 2, 4 |
| Click-around (XCUITest, Mac) | y | delete, open Trash, Put Back; Command-Z after a delete | slices 1, 2 |
| iPhone / iPad | y | shake or the on-screen undo; Trash in the sidebar | slices 1, 2 |
| Load | y | the history list and the Trash list stay fast with a million record rows | slices 1, 6 |

Hard-gate: the same step, taken from the app, the command line and an agent, leaves the same
record and is reversed the same way.

## Open questions for the creative director

One list, most consequential first, each with a proposal so that "agreed" is a complete answer,
is kept with the working notes as "questions for the maintainer". The three to read first:
what Command-Z takes back; where deleted things go and how they come back; how to take back a
whole run or return a library to yesterday.

## Sources folded in

- The Step 1 survey of 2026-09-20 (working notes, not in the repository).
- The source-model reviewer's read of the redo fix (#4957).
- The activity system review of 2026-09-20 (#4960).
- Standing rulings: one audited action layer; one code path per thing; prefer raise over silent
  fallback; accounts are people; the model is a user; dead-simple UX; the server may be remote;
  the user's machine is always useful.
