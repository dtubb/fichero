# Take Back a Run: everything one run did, as one step. Design Spec (#TBD)

> Milestone: undo-trash-rollback
> Manual: TBD. "Taking back a run": seeing everything a run made or changed; taking it all
> back, today or next week; what is kept because a person has worked on it since; putting the
> run's work back again; the same for an import and for an AI assistant's session.
>
> Slice 4 of the safety set. Read `undo-trash-rollback.md` first. **Status: DRAFT,
> 2026-09-20.** Behaviours carry no tag and no issue yet, by instruction. Claims about the code
> are VERIFIED (line given), TRACED or INFERRED. Nothing was run.

## Intent

A workflow run, an import, an AI assistant's session and a job that ran on another machine are
each **one piece of work by a machine**. A person can open any of them, see everything it made
or changed, and take all of it back as one step, next week as easily as today. What a person
has worked on since is kept, and the app says which things those are before anything happens.
Taking a run back is itself a step that can be reversed.

This supersedes `audit.run-scoped-undo` (#2074, #1831) in the action-layer spec.

## Prior art

- **Version control.** Reverting a commit makes a new commit that undoes it; history keeps
  both. We adopt that: a take-back is a new recorded step.
- **Database migrations and ETL.** A batch carries a batch id on every row it writes, so the
  batch can be found and removed. We adopt the stamp.
- **W3C PROV.** A run is an activity; what it made `wasGeneratedBy` it; the model is the
  software agent; the person who started it is the agent responsible. The remote-compute set
  already states this shape for landed results.
- **What we do differently.** Bulk tools usually force a rollback over later human edits or
  refuse outright. For research data neither is right. We take back what is untouched, keep
  what a person has touched, and show the list first.

## What exists

| What | State | Evidence |
| --- | --- | --- |
| A way to take back a run | **none**; no such route | VERIFIED by survey; already recorded as a gap in the action-layer spec |
| The record stores a run id on each step made through the action layer | built | VERIFIED per the action-layer spec (`ActionContext.run_id`) |
| A run id on the things a run makes | on artifacts and renditions **only** | VERIFIED by survey (`models/__init__.py:710`); the schema file has no run-id column for statements, entities, links, tags or vectors |
| A run writes through the record | **partly**: the runner is handed the open database and writes directly as it goes | VERIFIED per the remote-compute set (`execution/runner.py:842-850`, `workflows/completion.py:230-243`) |
| Deleting a run | marks the run row, hard-deletes its checkpoints, leaves all its output, asks nothing | VERIFIED by survey (`fichero/fichero/Views/Workflow/Execution/WorkflowExecutionView.swift:67-70`) |
| Running again | three different behaviours, depending on the node | VERIFIED by survey |
| A run that fails part way | keeps what it already wrote, and the code says so | VERIFIED by survey (`llm_base.py:813-828`) |
| Machine-made things recorded as made by a person | a known defect (#4869, #4868) | per the maintainer's standing notes |
| An import that fails part way | the cleanup hook never runs on the real path; stored bytes are orphaned; no sweeper | VERIFIED by survey (`importers/ingest.py:354-361`, `api/routes/ingest/core.py:1024`) |
| A data repair can be rolled back | built on the older record; marks rows with an id that points at nothing; swallows failures per row | VERIFIED by survey (`db/migrations/runner.py:960-1065`) |
| Remote results land as recorded actions and can be undone as one | designed, not built (remote-compute set: `compute.land.undoable-as-one`) | read in that set's `transfer-and-results.md` |

## Behaviours

### A. The stamp

- `safety.run.one-stamp` — **[GAP]** (#5245) there is one stamp: the **run id**. A workflow run, an import, an
  AI assistant's session, a data repair, and a landed remote job each get one. It appears in
  exactly two places, for two different reads: on every **record row** the run causes (to take
  the run back), and on every **thing the run makes** (to show "made by this run" without
  reading the record). *Data:* the record's existing run-id field; one `made_by_run` column on
  each kind a run can make. *Existing data:* old rows have no stamp and are never guessed at
  (see D). *Test:* run a workflow that makes one of each kind; every made row and every record
  row carries the run's id. **The remote-compute set's landing uses this same stamp**; a landed
  job is a run (request in the foundation file).
- `safety.run.every-write-of-a-run-is-recorded` — **[GAP]** (#5245) everything a run writes goes through a
  recorded action that carries the stamp. A run may use bulk actions (one record row for a
  batch of many things, listing their ids), so recording does not slow a large run to a crawl.
  A run never writes to the library behind the record's back. *Why:* without this, a run
  cannot be listed, so it cannot be taken back. *Existing data:* none to move. *Test:* a
  guardrail over the workflow tools: no write outside an action; load leg: a run over 10,000
  pages stays within the ratchet.
- `safety.run.the-engine-says-who-made-it` — **[GAP]** (#5245) whether a thing was made by a person or a machine,
  by which model, in which run, and who started the run, is set by the engine from the run,
  never claimed by the writer. This is the #4869 rule, and the remote-compute set's
  `compute.land.server-sets-the-maker`. *Test:* a tool that claims "made by a person" inside a
  run is recorded as machine-made.

### B. Seeing what a run did

- `safety.run.what-it-did-is-listed` — **[GAP]** (#5245) a run's row in the activity window opens a list of
  everything it made and everything it changed, by kind, with counts, each one a link to the
  thing. *Data:* read from the stamp; paged in the database. *Test:* the list equals the rows
  the run wrote.

### C. Taking it back

- `safety.run.take-back-is-one-step` — **[GAP]** (#5245) Take Back reverses everything the run did, newest first,
  as **one recorded step** named for the run. Things the run made go out of view the way
  trashed things do (soft, with the take-back's step id), so nothing is destroyed. Things the
  run changed return to the version before the run (`versions-and-restore.md`). *Test:* run,
  take back, compare with the state before the run: identical, row for row.
- `safety.run.a-persons-later-work-is-kept` — **[GAP]** (#5245) before anything happens, the app shows: how many
  things will be taken back, and how many will be **kept because a person has changed them
  since**, listed by name. A thing a person has edited, curated, linked, or cited since the run
  is never taken back by a run's take-back. The person confirms once. *Data:* the two locks of
  `undo.md`, asked per thing instead of per step. *Test:* run; a person curates two of its
  statements; take back; the two remain with their curation; the rest are gone; the sheet named
  the two.
- `safety.run.any-time` — **[GAP]** (#5245) a run can be taken back as long as it is listed, next week or next
  year. It does not depend on a sitting and it is never offered by Command-Z
  (`safety.undo.agents-and-runs-are-not-in-my-stack`). *Test:* take back a run made under an
  earlier sitting.
- `safety.run.all-or-nothing` — **[GAP]** (#5245) a take-back that fails part way stores nothing. *Test:* force a
  failure half way; the library is unchanged.
- `safety.run.put-it-back` — **[GAP]** (#5245) a take-back can be reversed from the same place: the run's work
  returns, same ids, until the Trash holding it is emptied. *Test:* take back, put back,
  compare with the state after the run.
- `safety.run.who-may` — **[GAP]** (#5245) the person who started a run may take it back. The library's owner
  may take back any run. The #4917 access rules apply: a run's work inside a folder a person
  may not edit is kept and listed as kept. *Test:* two accounts.
- `safety.run.a-failed-run-offers-it` — **[GAP]** (#5245) a run that failed or was stopped keeps what it wrote
  (as today) and its row offers Take Back at once, with the count. *Test:* stop a run half
  way; take back; nothing of it remains.

### D. Old runs

- `safety.run.old-runs-are-honest` — **[GAP]** (#5245) a run made before this slice can be taken back only as far
  as its stamp reaches: its artifacts. The app says so in a sentence: "This run is from before
  Fichero recorded everything a run writes. Its 214 page texts can be taken back. Its
  statements cannot be told apart from others." Nothing is ever attributed to a run by
  guessing from times. *Existing data:* untouched. *Test:* an old-shaped run offers the
  partial take-back with that sentence.

### E. Running again

- `safety.run.again-never-writes-over` — **[GAP]** (#5245) running a workflow again on the same sources adds its
  output beside what is there: a new pass, new readings, new proposals. It never replaces a
  person's work and never silently replaces an earlier run's. The three present behaviours
  become this one. This is the source-model set's `source.chain.output-never-overwrites` and
  the remote-compute set's `compute.land.never-overwrites`, stated once for every kind.
  *Test:* run twice; the first run's rows are byte-identical after the second.

### F. Deleting a run is not taking it back

- `safety.run.delete-and-take-back-are-two-verbs` — **[GAP]** (#5245) deleting a run sends the run's row and
  events to the Trash (`trash.md`) and keeps its work. If the run has live work, the notice
  says so and offers Take Back instead. Checkpoints are scratch and may be removed once a run
  is finished; they are never the only copy of anything. *Test:* delete a run with live work;
  the work is untouched; the notice names the count.

### G. Imports, assistants, repairs, remote jobs

- `safety.run.an-import-is-a-run` — **[GAP]** (#5245) an import gets a stamp. Take Back on an import sends
  everything it brought in to the Trash as one step. Each file is imported whole or not at all:
  its row and its stored bytes are written together, and a failure leaves neither. *Data:*
  the import action becomes atomic per file; stored bytes written before a failed row are
  removed in the same step, through the storage layer. *Existing data:* orphaned bytes already
  in a library are found by the sweep in `safety-net.md`, listed, and never removed without a
  yes. *Test:* fail an import on file 3 of 5; files 1 and 2 are whole, 3 left nothing, 4 and 5
  were not started; take back the import; all are in the Trash.
- `safety.run.an-assistant-session-is-a-run` — **[GAP]** (#5245) everything an AI assistant does in one
  conversation turn, or one agent session over MCP, carries one stamp, and can be reviewed and
  taken back as one. The assistant's account is a user like any other; its steps are never in
  a person's Command-Z stack. *Test:* an agent session makes five changes; Take Back reverses
  the five; the record names the agent's account and the person who asked.
- `safety.run.a-repair-is-a-run` — **[GAP]** (#5245) a data repair shipped with an update runs as a run, recorded
  and stamped, and is taken back the same way. The separate rollback that walks the older
  record is deleted when the last repair that used it has been superseded. *Existing data:*
  past repairs stay as recorded; their old rollback remains until then. *Test:* a repair runs
  through actions; Take Back restores the rows.
- `safety.run.a-remote-job-is-a-run` — **[GAP]** (#5245) a job that ran on another machine lands as a run with
  this stamp and is taken back by this slice's rules. Nothing about take-back is written a
  second time for remote work. *Test:* the remote-compute set's `compute.land.undoable-as-one`
  passes using this slice's route.

## Things to try by hand

1. Run a workflow over ten pages. Open the run. It lists what it made.
2. Correct one of the statements it made. Choose Take Back. The sheet says nine things will go
   and one is kept, and names it. Agree. Check the library.
3. Choose Put Back on the same run. The nine return.
4. Next day, reopen Fichero and take back a different run from yesterday.
5. Import a folder with one broken file. The others import; the broken one leaves nothing.
   Take back the import.
6. Ask the assistant to tag twenty documents. Press Command-Z: it does not touch the tags.
   Take back the assistant's session: the tags go.

## Test matrix

| Leg | This slice? | Pins | File |
| --- | --- | --- | --- |
| Backend (pytest) | y | A to G, real database, a real small workflow, two accounts | beside `fichero-server/tests/unit/workflows/test_completion.py` |
| Guardrail | y | no run write outside an action | new check over the workflow tools |
| MCP / CLI | y | list what a run did; take back; put back | the MCP and CLI suites |
| Click-around (Mac) | y | the six things above | the UI suite |
| Load | y | a 10,000-page run records within the ratchet; its take-back is bounded and does not peg the machine | the perf suite |

## Open questions

See the questions file. From this slice: a person's later work is kept, not overwritten and not
a reason to refuse; old runs are taken back only as far as they were stamped; deleting a run
and taking it back are two verbs.
