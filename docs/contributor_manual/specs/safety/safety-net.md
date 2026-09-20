# The Safety Net: snapshots, library updates, and returning a library to yesterday. Design Spec (#TBD)

> Milestone: undo-trash-rollback
> Manual: TBD. "Snapshots and returning to an earlier day": what a snapshot holds and what it
> does not; when Fichero takes one for you; what it costs in disk space; what Fichero does
> when there is no room; returning the whole library to a snapshot and what is lost by doing
> so; what happens when an update to a library cannot be completed.
>
> Slice 5 of the safety set. Read `undo-trash-rollback.md` first. **Status: DRAFT,
> 2026-09-20.** Behaviours carry no tag and no issue yet, by instruction; two defects this
> slice designs the answer to are already filed and cited (#4982, #4983). Claims about the code
> are VERIFIED (line given), TRACED or INFERRED. Nothing was run.

## Intent

Some steps cannot be reversed: emptying the Trash, updating a library's format, resetting the
knowledge graph, merging two libraries. Before any of them, Fichero takes a snapshot of the
library. **If it cannot take one, it does not take the step, and says why.** It never carries on
without one. A person can also take a snapshot by hand, keep it, and return the whole library to
it. An update to a library either completes or leaves the library exactly as it was.

This is the last line. Slices 1 to 4 are for ordinary regret. This one is for the day
something goes badly wrong.

## Prior art

- **Time Machine and APFS snapshots.** Cheap because unchanged data is shared, not copied; the
  system thins old ones; a restore is deliberate. We adopt "cheap by sharing" where the disk
  allows it and "deliberate restore".
- **Database migration tools** (Alembic, Flyway, Rails). A version table; each migration in a
  transaction; stop on failure; never run a half-applied schema. Fichero has none of the three
  today. We adopt all three.
- **The draft-purge action already in Fichero** is the right shape for a destructive bulk step:
  a dry run by default, a set of protected ids, counts shown first. The knowledge-graph reset
  adopts it.
- **What we do differently.** A backup tool's failure is usually a log line. Here a snapshot
  that cannot be taken **refuses the step it was protecting**.

## What exists

| What | State | Evidence |
| --- | --- | --- |
| Library snapshots: per-table files, a copy of the database file and of the vector folder; ten kept; pinning; a Settings screen; routes to create, list, restore, delete | built | VERIFIED by survey (`db/storage_snapshots.py:34`, `:139`, `:374`; `fichero/fichero/Views/Settings/Snapshots/SnapshotsView.swift`; `fichero/fichero/Models/BackupStore.swift`) |
| Restore stages first and sets the current files aside rather than deleting them | built, and right | VERIFIED by survey (`:423-441`) |
| The set-aside copies are ever cleaned up | no | INFERRED: no removal of them in the module |
| Original files in a snapshot | left out by default; the screen cannot include them; a restore leaves files at the later state, and a test pins that as designed | VERIFIED by survey (`:148`, `:694`; `fichero-server/tests/unit/db/test_snapshot_include_files_hardening.py:83`) |
| A snapshot is taken automatically before | orphan cleanup, purge, and library merge; nothing else | VERIFIED by survey (`api/routes/document/documents.py:2054`, `:2544`; `api/routes/library/registry.py:795-805`) |
| When the automatic snapshot fails | a warning is logged and the destructive step goes ahead | VERIFIED by survey (`db/storage_snapshots.py:705-712`) |
| The copy is a full copy | yes (`shutil.copy2`, `shutil.copytree`); no use of the disk's ability to share unchanged data | VERIFIED by survey (`:202`, `:234`) |
| Snapshots live in a folder on the engine's own machine, outside the library | built; reached only through routes, so a remote engine works | VERIFIED by survey (`:7`, `:154-156`) |
| Library updates (schema migrations) | no version table, no transaction, no snapshot first; a failure is caught and logged as a warning and the library opens half updated | VERIFIED `db/migrations/schema.py:230-231`; applied unconditionally per survey (`db/__init__.py:1026-1037`). **#4983** |
| The knowledge-graph reset | would delete every entity, statement and link with no filter, no record, no confirmation; cannot run today because it calls a one-argument delete with two (`api/routes/kg/rebuild.py:50-55` against `db/__init__.py:3306`); its only test fakes the wrong shape; the app cannot reach it | VERIFIED. **#4982. Nobody is to repair the call as written.** |
| Transactions | nested ones are flattened; no savepoints; the database, the vector store and file storage share no transaction and nothing reconciles them | VERIFIED by survey (`db/__init__.py:1525-1563`, `:1003-1006`) |
| Stored bytes with no row, after a failed import | possible; no sweep exists | VERIFIED by survey |
| Who may delete a snapshot | anyone who may write, including the snapshot that is the only way back from a purge | VERIFIED by survey (`security/authz.py:255-260`) |

## Behaviours

### A. What a snapshot is, and what it costs

- `safety.net.what-a-snapshot-holds`: a snapshot holds the library's rows (research, versions,
  the record) and its search vectors, and a **list** of the stored original files with their
  sizes and content fingerprints. It does **not** copy the original files. *Why that is safe:*
  stored originals are never rewritten: image edits are settings, and no code deletes stored
  bytes today. After this set, exactly one step removes them: emptying the Trash. So rows
  returned to an earlier day still find their files, unless the Trash was emptied in between,
  and in that case the restore says exactly which files are gone (D). *Existing data:* present
  snapshots already have this shape, minus the list; they stay valid. *Test:* snapshot, edit,
  restore: every row finds its file.
- `safety.net.cheap-where-the-disk-allows`: where the disk can share unchanged data between
  two files (APFS on a Mac; reflinks on a Linux server that has them), a snapshot is made that
  way and takes almost no space at first. Elsewhere it is a full copy. Either way the engine
  knows the cost before it starts. *Data:* the copy goes through one function that tries the
  sharing copy first. *Test:* on APFS, free space falls by far less than the database size.
- `safety.net.says-what-it-costs`: the Settings screen shows each snapshot's size on disk and
  the total, and the size the next one would need. *Test:* availability.
- `safety.net.never-pegs-the-machine`: a scheduled snapshot runs at background priority and
  yields to the person's work. A snapshot taken before a step the person just asked for runs at
  once, shows progress, and can be cancelled (which cancels the step). *Test:* load leg.

### B. Before every step that cannot be reversed

- `safety.net.the-steps`: a snapshot is taken before: Empty Trash and Delete Permanently; an
  update to the library's format; the knowledge-graph reset; a library merge; orphan cleanup;
  any bulk action that is not reversible (pruning trivial statements, purging machine drafts,
  rewriting stored text); and a snapshot restore itself. **Not** before a workflow run or an
  import: those are reversible by `run-take-back.md`, and a snapshot per run would fill the
  disk. *Data:* the action registration's "how it comes back" field
  (`safety.undo.every-action-says-how-it-comes-back`) gains the value "snapshot first"; the
  registry takes the snapshot, not each action's own code. *Test:* a guardrail: every action
  that is neither reversible nor Trash-bound is "snapshot first" or carries a written reason.
- `safety.net.no-snapshot-no-step`: if the snapshot cannot be taken, the step is **refused**.
  The message says why in a sentence and what would help: "There is not enough room to make a
  safety copy first (needs about 2.1 GB, 0.8 GB free). Nothing was deleted. You can free space
  by removing older snapshots: 6 unpinned, 9.4 GB." The present behaviour (log a warning and
  carry on) is removed. *Existing data:* none. *Test:* fill the disk in a fixture; Empty Trash
  is refused; nothing is removed; the sentence names the numbers.
- `safety.net.room-is-checked-first`: before starting, the engine compares what the snapshot
  needs with what is free, and leaves a margin so the machine stays usable. It does not start
  a copy it cannot finish. *Test:* no partial snapshot folder is left behind by a refusal.
- `safety.net.a-step-and-its-snapshot-are-linked`: the record row for the step names the
  snapshot taken before it, and that snapshot is exempt from thinning until the person removes
  it or ten newer protected steps exist. *Test:* eleven plain snapshots later, the one before
  an Empty Trash is still there.

### C. Updating a library (#4983)

- `safety.net.an-update-completes-or-changes-nothing`: each update to a library's format runs
  in a transaction with a number, recorded in a version table in the library. On failure the
  transaction is rolled back, the version is unchanged, and **the library does not open for
  writing**. The person is told which update failed, that nothing was changed, and that the
  snapshot from before the update is in Settings. A failure is never a warning in a log.
  *Data:* a version table; updates numbered in order. *Existing data:* a library with no
  version table is measured once (which columns and tables it has), given the number that
  matches, and updated from there; the existing updates are already written to be safe to run
  twice. Nothing is discarded. *Test:* an update that fails half way: the library's tables are
  byte-identical to before, the version is unchanged, the open is refused with the sentence.
- `safety.net.an-update-is-snapshotted-first`: the snapshot rule of B applies; with no room,
  the update does not start and the library opens read-only in its present format if the app
  can read it, or not at all, and says which. *Test:* no room: no update attempted.
- `safety.net.data-repairs-are-runs`: an update that changes research data (not just its
  format) runs as a stamped run and is taken back as one (`safety.run.a-repair-is-a-run`).
  *Test:* there.

### D. Returning the whole library to an earlier day

- `safety.net.restore-says-what-is-lost`: before a restore, the app shows when the snapshot
  was taken and what has happened since, from the record: how many steps, by whom, how many
  things made, and which stored files the library has removed since (so rows would point at
  nothing). The button says "Return Library to 14 March, 09:12". *Test:* the numbers equal
  the record.
- `safety.net.restore-loses-nothing-for-good`: the present state is set aside first (as
  today), listed in Settings as "Before the restore of …" with its size, and can itself be
  returned to. Set-aside copies count as protected snapshots under B and are thinned by the
  same rule, never silently. *Existing data:* set-aside copies already lying in library
  folders are found and listed on first open. *Test:* restore, then return to the set-aside
  copy: the library is as it was.
- `safety.net.restore-is-written-down`: the record inside a restored library ends at the
  snapshot, so the restore is written as the first new row after it, naming who, when, and
  which snapshot, and the chain's outside anchor is updated so the shortened record is not
  mistaken for tampering. *Test:* the chain verifies after a restore.
- `safety.net.owner-only`: only the library's owner may restore a snapshot or delete one.
  Anyone who may write may take one. *Test:* an editor's restore and delete are refused.
- `safety.net.not-while-others-are-working`: a restore is refused while another person or a
  run is writing, and says who. *Test:* two sessions.

### E. The knowledge-graph reset (#4982)

- `safety.net.reset-never-touches-curated-work`: the reset removes only machine-made entities,
  statements and links that no person has touched, and says how many before it does anything.
  It is a recorded action in the one registry, shaped like the draft purge that exists: a dry
  run unless told otherwise, a set of protected ids worked out from the record, counts first,
  snapshot first, owner only. **The present route is deleted, not repaired.** *Existing data:*
  none at risk; the route has never been able to run. *Test:* against a real database with
  curated and machine-made rows: the curated rows are byte-identical afterwards; the test that
  fakes the delete's shape is deleted with the route.
- `safety.net.rebuild-is-a-run`: rebuilding the graph from sources is a stamped run and is
  taken back as one. *Test:* in `run-take-back.md`.

### F. Three stores that do not share a transaction

- `safety.net.the-database-is-the-truth`: rows are the truth; search vectors and derived
  images are derived and can be made again; stored originals are kept until the Trash is
  emptied. So after any failure: a vector with no row is dropped; a row with no vector is
  embedded again in the background, throttled; neither is ever a reason to change a row.
  *Test:* delete a vector behind the engine's back; it returns; remove a row's vector partner;
  search still works after the background pass.
- `safety.net.orphans-are-listed-never-swept`: stored files that no row points at, and rows
  whose file is missing, are found by a check that runs at background priority and are listed
  in Settings with sizes. Orphaned bytes are removed only when a person says yes; a row whose
  file is missing is shown as such in the library, never hidden. *Existing data:* this is how
  the bytes orphaned by past failed imports are found. *Test:* plant one of each; both are
  listed; nothing is removed without the yes.

## Things to try by hand

1. Open Settings, Snapshots. Each shows its size, and the screen says what the next would need.
2. Empty the Trash. A snapshot appears named for that step.
3. On a nearly full disk, empty the Trash. It refuses, in a sentence with numbers. Nothing is
   gone.
4. Choose a snapshot from yesterday. The sheet says what has happened since. Return to it.
   Then return to "Before the restore".
5. (Contributors, with a test library only.) Install a build whose update fails. The library
   does not open, says why, and is unchanged under the previous build.

## Test matrix

| Leg | This slice? | Pins | File |
| --- | --- | --- | --- |
| Backend (pytest) | y | A to F, real database and vector store, a fixture that limits free space | extends `fichero-server/tests/unit/db/test_storage_snapshots.py` |
| Backend (pytest) | y | C, with a library file from each past format | new migration suite |
| Guardrail | y | every irreversible action is "snapshot first"; no caught-and-logged failure in the update path | new checks |
| MCP / CLI | y | take, list; restore and delete refused for non-owners | the MCP and CLI suites |
| Click-around (Mac) | y | the first four things above | the UI suite |
| Load | y | a snapshot of a large library does not peg the machine | the perf suite |

## Open questions

See the questions file. From this slice: originals are not copied into snapshots, and the Empty
Trash sheet says so; no room means the step is refused; no snapshot before runs or imports; a
failed update means the library does not open; only the owner restores.
