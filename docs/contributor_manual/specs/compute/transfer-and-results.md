# Remote Compute — What leaves, how it travels, and what comes back — Design Spec (#TBD)

> Milestone: remote-compute
> Manual: TBD — "Before anything leaves your Mac": what the sheet tells you and what your yes
> covers; a collection that may never leave; what is sent (only what the work needs); what
> happens if the network drops; what Fichero removes from the other machine afterwards and
> what it cannot promise; how results appear, and why they never replace your own work.
>
> Design-led (Testing Constitution). **Status: DRAFT — first pass, 2026-09-20.** A slice of the
> compute set: read `remote-compute.md` first. Behaviours carry **no tag and no issue yet**, by
> the rule stated there. **VERIFIED / INFERRED** for our code; **CITED / UNVERIFIED** for
> outside services, with S-numbers from "Sources" in `remote-compute.md`.

## Intent

Archival material is not ordinary data. Some of it is restricted by an archive; some is held
by a community whose protocols outrank any default in an app. So nothing leaves the Mac until
a person has been told, in plain words, what will go, how much, to where, who runs that place
and how long it will stay, and has said yes. A collection marked as never to leave cannot be
sent at all. What is sent is the least the work needs: a training set, or the page images of
the selected sources, never the whole collection because it was easier. It travels in pieces
named by their content, so a dropped connection costs only the piece in flight. Afterwards
Fichero removes what it put there and says what it cannot vouch for. What comes back is not a
changed copy of the collection. It is a list of proposed changes, replayed on the Mac through
the same audited actions as a person's own edits, each marked as made by a machine, on that
target, by that model. It adds; it never overwrites.

## What exists today

- **The transfer core, pure and tested.** `workflows/library_sync.py`: `SyncObject` (path,
  sha256, size; the file time is only a hint) (VERIFIED `:47-98`); `SyncManifest` (`:100-157`);
  `diff_manifests` giving add, change, delete, and refusing two different libraries
  (`:214-242`); `SyncCheckpoint` and `pending_objects`, where the same content is sent once
  (`:250-349`).
- **Disk halves.** `library_sync_io.py`: hashing in chunks, listing `files/`, landing a received
  object atomically with its hash re-checked (VERIFIED `:36`, `:54`, `:110-118`).
  `library_sync_db.py`: a consistent copy of the database as one object (`:41`).
- **Two read-only routes.** `GET /library/sync/manifest`, `GET /library/sync/object`, gated by
  the ordinary library-read permission (VERIFIED `api/routes/library/sync.py:1-18`, `:81`,
  `:111`). No push, no commit (`:14`).
- **A second, weaker manifest.** `BundleManifest` in `remote_jobs.py`: a list of bare input
  paths and a `library_path`, no hashes, no resume (VERIFIED `:39-81`). It is only ever built
  in memory by the dry-run route (VERIFIED `api/routes/ai/hpc.py:308-315`); nothing is stored
  in that shape.
- **"Completed" already waits for landing.** A Slurm job that has finished is still *running*
  to Fichero until its results have landed (VERIFIED `remote_jobs.py:281-293`).
- **The gate is designed, not built, elsewhere.** `source.egress.one-gate` (#4949): whether
  content may leave is decided in one place, where a model is called, reading the project's
  rule and a segment's rights record; today's privacy check on model profiles
  (VERIFIED to exist: `llm/model_profiles.py:57-122`) becomes that gate.
  `source.project.stays-local` (#4951): a project marked "pages may not leave this machine"
  refuses cloud models. `source.format.rights-filtered-once` (#4943): restricted material is
  filtered once, in the one export stream.
- **The rights slice is blocked on the maintainer** (`source/rights-and-access.md`, header).
- **Permissions exist** down to a document: owner, editor, viewer, with grants and denies
  walked up through folders (VERIFIED in that spec's header, citing `security/authz.py`).
- **A known fault this slice must not repeat:** claims made by a model were stored as made by
  a person (#4869, #4868). The fix ruled there is that the *server* sets what kind of maker it
  was. Landing uses that, not a field in the package.
- **The "no local paths" rule.** The server may be remote, so nothing passes a file path from
  one machine to another (project rule; `transport/` specs). `BundleManifest.library_path`
  breaks it.

## The design (proposed)

### Before anything leaves: one sheet, one gate

Sending a work package to a target is one more case of content leaving the Mac. It is decided
at the **one gate** the source-model set names, not at a second one here. This slice adds what
that gate must be told and what the person must be shown.

The sheet, shown before the first send of a given collection to a given target, says:

1. **What:** "412 page images and their transcriptions from *Marshall diaries, 1890s*", or
   "a training set of 3,120 lines made from 96 pages you corrected".
2. **How much:** the bytes that will actually travel (after subtracting what is already
   there).
3. **Where, and who runs it:** the target's name and its `operator_note`.
4. **Who else could read it there**, in one sentence for that kind of target.
5. **How long it stays:** "removed when the job's results are back", or "kept until you remove
   it" for a server that holds a collection.
6. **What is left out,** and why: material the rights record restricts. **Until the rights
   slice is unblocked the sheet says instead: "Fichero does not yet know which of these
   sources are restricted. Nothing has been left out."** That sentence is a behaviour, because
   the dishonest alternative is silence.
7. For material that may be community-held, one question, asked once for a collection and
   remembered: "Does any of this come from, or depict, a community that holds rights or
   protocols over it? If so, has someone with the authority to agree said it may be sent to
   *target*?" The answers are *No such material*, *Yes, and it is agreed*, and *Not sure: do not
   send*. This follows the CARE principles and the First Nations principles of OCAP, where the
   community's own protocol outranks a tool's default (CITED, S14, S6). It is a pointer to a
   conversation, not a legal test.

A **yes** is recorded as an audited action naming the person, the collection, the target, the
kind of work and the answers. It covers later sends of the same kind from that collection to
that target. It does not cover another target, and it does not cover **publishing**, which is
always asked again (`jobs-and-fine-tuning.md`).

### The work package

A work package is a folder with two things in it:

- `job.json`: what to run (a workflow and its settings, or a training recipe), the version it
  was made by, the models it needs by card id, and the identities of its inputs;
- `objects/`: the inputs, each stored under its sha256.

Beside them, `manifest.json` is an ordinary `SyncManifest` over those objects. There are no
file paths from the Mac anywhere in it. A package is a **projection**: it can always be made
again from the collection, and it is never the record.

What goes in depends on the work, and is always the least that will do:

| Work | Goes in | Does not go in |
|---|---|---|
| read or segment pages | the page images of the selected sources, at the resolution the model needs; the ids they belong to | other sources; the database; notes; the knowledge graph |
| work over text (entities, normalising) | the text and its ids | images |
| fine-tuning | a **training set**, as `source.train.*` defines it (#4947): line pictures and their human-checked readings, with its own description | anything not in the training set |
| a server that holds a collection | the whole collection, by the existing library sync | (this is the one case where everything goes) |

### One transfer core, two carriers

The manifest, the difference and the checkpoint are the only logic. A **carrier** moves one
object and answers "which of these do you already have":

- **HTTPS carrier:** to a running Fichero server (a Linux machine). The existing read routes
  gain their write half: put an object; commit a manifest.
- **SSH carrier:** to a cluster, where nothing is listening. Objects are written under
  `<base>/fichero/objects/<sha256>` over the one SSH connection. "Which do you have" is a
  listing of that folder. A received object is re-hashed on the far side before it counts.
- **Local carrier:** for `this-mac`, a copy within one disk.
- **Hub carrier:** for Hugging Face Jobs, objects go to a private repository or bucket the job
  mounts (CITED, S12). Proposed last, with the Hugging Face slice.

Objects are stored once for each target, not once for each job. A second job over the same
pages sends nothing. This is also why `rsync` is not used: it would be a second way to decide
what to send, outside the checkpoint, and it is not reachable from a sandboxed app.

The Alliance recommends Globus for large transfers, through its data-transfer nodes (CITED,
S2). For the sizes here (page images, not terabytes) the SSH carrier is enough; a Globus
carrier is possible later under the same core and is not proposed now.

### Sending never pegs the Mac

Hashing and sending run at background priority and with a bounded number of pieces in flight,
by the same rule as embeddings (project rule: the person's machine stays useful).

### Cleaning up the far side

When a job's results have landed, Fichero deletes that job's folder on the target. Objects are
kept while another job still names them and deleted when none does, or at once if the person
chose "remove everything when done" on the sheet. Then it lists the folder to confirm. It says
plainly what it cannot vouch for: a cluster's own snapshots and backups, and an operator's
access while the data was there (CITED, S6).

### Results: the same records a local run makes

A local run writes into the collection's database as it goes, and appends one line for each
model call to the episode ledger, which is JSONL inside the collection's folder (VERIFIED
`execution/runner.py:842-850`, `workflows/completion.py:230-243`,
`observability/episodes.py:10-14`). To keep **one runner**, the far side does the same thing
into a **scratch collection**: a small `.fichero` package made from the work package, holding
only the chosen sources, with their ids unchanged. The unchanged runner runs against it. Then
the engine's one export stream (`iter_export_records`, `export_service.py:124`) writes what the
run added as JSONL records.

So a **result package** holds: `records.jsonl` (the exporter's records for what is new, each
naming the id and the **version** of the source it was computed from); `episodes.jsonl` (the
ledger lines the run appended); and new objects (a model file, line pictures) under their
sha256. The scratch collection itself never comes back and is deleted with the job's folder.

The Mac fetches it with the same transfer core, and **lands** it:

- Each record becomes one audited action, run by the Mac's own server. Nothing in the engine
  reads these records back in today (VERIFIED by search), so this is new code, and the only
  new code on the results side.
- Ledger lines are appended to the Mac's own ledger. Each has its own `episode_id`
  (VERIFIED `observability/episodes.py:97`), so appending the same lines twice is detected. The far side never writes
  to the collection, so the rule that the engine is the only writer holds.
- The server stamps each as **made by a machine**, with the job, the target, the model card and
  its version, and the person who sent the job as the one responsible. The package cannot claim
  otherwise. This is what `source.making.recorded` (#4949) reads later.
- Output arrives as a **new pass** or **new readings** and never replaces a person's
  (`source.chain.output-never-overwrites`, #4949; `source.train.output-is-pass`, #4947).
- Landing is **idempotent**: each record carries an id made from the job and its position;
  landing the same package twice adds nothing.
- Landing is **all of a source or none of it**: a failure half-way through one source undoes
  that source's lines and reports it; other sources stand.

### When the collection changed while the work was away

Work can be away for days. Meanwhile a person may correct a page, redraw a line, or delete a
source. Because results only ever *add* a pass, most of this is harmless. The rules:

| Meanwhile | On landing |
|---|---|
| nothing changed | lands |
| the source's text or segments were edited | lands as a new pass, marked "computed from an earlier version", with that version named |
| the segment a reading belongs to no longer exists | follows the forwarding note if the source model left one (`source-model.md`, slice 4); otherwise the line is **set aside** |
| the source was deleted | its lines are **set aside** |
| the collection is now marked "may not leave" | results still land (they are coming home); nothing more is sent |

**Set aside** means kept in the job's folder on the Mac, listed on the job with the reason,
never dropped silently, and removable by the person.

## Behaviors

All untagged and unbuilt unless stated.

### Leaving

- `compute.leave.one-gate` — a send to any target is allowed or refused by the one egress gate
  (`source.egress.one-gate`), called with the collection, the target and the kind of work. This
  slice adds no second check. *Routed:* the gate itself is #4949's. *Test:* with the gate faked
  to refuse, no carrier is ever called.
- `compute.leave.stays-local-is-absolute` — a collection marked "may not leave this machine"
  (`source.project.stays-local`) can be sent only to targets of kind `this-mac`. A
  `local-container` counts as this Mac. The refusal names the collection's rule. *Test:* each
  kind of target against a collection so marked.
- `compute.leave.sheet-before-first-send` — before the first send of a kind of work from a
  collection to a target, a sheet shows the seven things listed above, computed from the actual
  package and the target's record. *Data:* the package manifest; the target's `operator_note`.
  *Test:* pure Swift: a package of 3 images and a cluster target yields those strings; bytes
  shown equal the pending set, not the package total.
- `compute.leave.says-when-it-cannot-tell` — until a rights record exists to read, the sheet
  carries the sentence "Fichero does not yet know which of these sources are restricted.
  Nothing has been left out." When the rights slice is built, this behaviour is replaced by
  `compute.leave.restricted-left-out`. *Test:* the sentence is present; a guardrail ties its
  removal to the rights behaviour being tagged built.
- `compute.leave.restricted-left-out` — once a rights record can mark a source or segment as
  not to leave, the package builder leaves it out in the one export stream
  (`source.format.rights-filtered-once`, #4943), and the sheet lists what was left out and why.
  **Blocked** with `source/rights-and-access.md`. *Test:* to be written with that slice.
- `compute.leave.community-question-once` — the community question is asked once for a
  collection, its answer is stored on the collection, and "Not sure: do not send" refuses every
  send from it to any target but this Mac until changed. *Data:* a collection setting
  `compute.community_answer` with values `none` · `agreed` · `unsure`, and who set it and
  when. *Existing data:* collections with no answer are asked at their first send. *Test:* each
  answer against a send.
- `compute.leave.yes-is-recorded-and-scoped` — a yes is an audited action (person, collection,
  target, kind of work, the answers shown). It covers later sends of that kind from that
  collection to that target only. It can be withdrawn in the collection's settings, after
  which the sheet appears again. *Test:* second send: no sheet; other target: sheet; after
  withdrawal: sheet; the audit log holds one record for each yes.
- `compute.leave.nothing-in-the-background-without-a-yes` — automatic work (a collection's
  default chain, `source.project.automatic-after-first-yes`) never chooses a remote target by
  itself. A remote target is used only when a person chose it for that run or set it as that
  collection's default after a yes. *Test:* an automatic run with a remote default and no
  recorded yes runs on this Mac and says why.

### The package

- `compute.package.least-needed` — a package holds only the objects its kind of work needs, by
  the table above. *Test:* for a segmentation job over 3 of 40 sources: exactly 3 images, no
  database object, no text. For a fine-tune: exactly the training set's objects.
- `compute.package.is-a-sync-manifest` — a package's `manifest.json` is a `SyncManifest`; its
  objects are `SyncObject`s with sha256 and size. `BundleManifest`, `build_bundle_manifest` and
  `write_manifest` are removed from `remote_jobs.py`, and the dry-run route builds a package
  instead. *Existing data:* none is stored in the old shape (VERIFIED above). *Test:* the old
  names no longer import; the dry-run answer lists object hashes.
- `compute.package.no-paths-cross` — no absolute path from the Mac appears in `job.json`,
  `manifest.json` or any log line sent to a target; inputs are named by source id and sha256.
  *Test:* build a package from a library under a temp folder; assert that folder's path is in
  none of the package's text files.
- `compute.package.names-its-models` — `job.json` names every model the work will use by card
  id and version, so staging (`compute.connect.models-staged-before-a-job`) can happen before
  submit and a job never discovers a missing model half-way. *Test:* a workflow with two model
  steps yields two model entries.
- `compute.package.is-a-projection` — a package is never the record: it can be deleted at any
  time and made again, and two packages made from the same collection state and the same job
  are byte-identical. *Test:* build twice, compare hashes.
- `compute.package.no-secrets` — no token, key or provider API key is ever in a package or a
  job script. Work that needs a cloud provider's key cannot be sent to a target; it is refused
  with "this step needs your *provider* key, which never leaves this Mac". *Test:* a workflow
  with an OpenRouter step is refused before packaging; a scan of a built package for the
  seeded test keys finds none.

### Transfer

- `compute.transfer.one-core` — every send and every fetch, on every carrier, goes through
  `diff_manifests`, `SyncCheckpoint` and `pending_objects`. No other code decides what to send.
  *Test:* a guardrail: no `rsync`, `scp` or `sftp put` call exists outside the SSH carrier, and
  the carrier's only entry points take a `SyncObject`.
- `compute.transfer.only-what-is-missing` — before sending, the target is asked which object
  hashes it already holds; only the rest travel. *Test:* a second job over the same pages sends
  zero object bytes.
- `compute.transfer.resumes` — an interrupted send or fetch, restarted, moves only objects not
  yet confirmed. The checkpoint is stored on the Mac for each (target, direction) and survives
  a restart of the app. *Data:* `<server state dir>/compute/<target_id>/checkpoint-<dir>.json`.
  *Test:* kill the carrier after 2 of 5 objects; restart; 3 objects move.
- `compute.transfer.verified-on-arrival` — an object counts as arrived only after the receiving
  side has re-hashed it and the hash matches; a mismatch deletes it and reports it, and a retry
  sends it again. Built for landing on disk (VERIFIED `library_sync_io.py:110-118`); this id
  extends it to the far side. *Test:* corrupt one object in flight on the fake carrier.
- `compute.transfer.https-write-half` — the library sync routes gain `PUT` of an object and a
  commit, needing the write role, no more permissive than the sharing surface (the existing
  header rule of `api/routes/library/sync.py`). *Existing data:* the two read routes are
  unchanged. *Test:* a viewer's token is refused; an editor's succeeds; a partial upload is
  invisible until commit.
- `compute.transfer.ssh-carrier` — over the one SSH connection, objects are written to
  `<base>/fichero/objects/<sha256>` by way of a temporary name and a rename, and "which do you
  have" is a listing. *Test:* against the SSH fixture.
- `compute.transfer.stays-in-the-background` — hashing and sending run at background priority
  with at most a fixed number of objects in flight, and a 5 GB send does not raise the app's
  main-thread latency above the perf ratchet. *Test:* load leg (#4634).
- `compute.transfer.progress-is-the-checkpoint` — the progress a person sees (objects and bytes
  done of total) is read from the checkpoint, so it is right after a restart. *Test:* restart
  mid-send; the bar resumes at the same figure.

### After the work

- `compute.transfer.far-side-cleaned` — when a job's results have landed, its folder on the
  target is deleted and the deletion confirmed by listing. Shared objects are deleted when no
  unfinished job names them, or at once if the person chose "remove everything when done".
  A failure to delete is shown on the job as "could not remove *n* files from *target*", never
  ignored. *Test:* fixture: folder gone; with a read-only folder: the message appears.
- `compute.transfer.says-what-it-cannot-vouch-for` — the sheet and the job's finished state
  carry one sentence for cluster and Hugging Face targets: that the operator's backups and
  access are outside Fichero's reach. *Test:* pure.

### Landing

- `compute.land.same-records-as-a-local-run` — a job's `records.jsonl` is written by the one
  export stream from a scratch collection the unchanged runner wrote into; no second writer of
  run output exists. *Data:* `iter_export_records`; the scratch package under the job's folder.
  *Test:* the same three-page workflow run on this Mac directly, and as a job on the `this-mac`
  target, leaves identical readings and identical ledger lines apart from ids and times.
- `compute.land.ledger-lines-merge` — a job's `episodes.jsonl` lines are appended to the
  collection's ledger under their own `episode_id`s; a line whose id is already present is
  skipped. *Existing data:* the ledger is append-only and is never rewritten. *Test:* land
  twice; line count unchanged the second time; the training export
  (`episodes.export_training_pairs`) sees the remote calls.
- `compute.land.only-the-mac-writes` — the far side produces a result package and never writes
  to a collection; every change is an audited action run by the Mac's server. *Test:* a result
  package that tries to name an action outside the allowed list for its job kind is refused
  whole.
- `compute.land.allowed-actions-by-job-kind` — each job kind has a fixed list of actions its
  results may propose (a reading job: add a pass, add segments to that pass, add readings; a
  fine-tune: add a model file, add a card, add scores). Anything else refuses the package.
  *Data:* a table in code beside the job kinds. *Test:* one refusal for each kind.
- `compute.land.server-sets-the-maker` — every landed action is stamped by the Mac's server as
  machine-made, with job id, target id, model card and version, and the sending person as
  responsible. A `created_by` or similar field inside the package is ignored. This is the rule
  of #4869 applied here. *Test:* a package claiming `created_by: human` lands as machine-made.
- `compute.land.never-overwrites` — results arrive as a new pass or new readings; no existing
  pass, reading, segment or claim is changed or removed by landing. *Test:* land onto a source
  with a person's pass; that pass's rows are byte-identical afterwards.
- `compute.land.idempotent` — every line has an id made from the job id and its position;
  landing a package again adds nothing and reports "already landed". *Test:* land twice; row
  counts equal.
- `compute.land.whole-source-or-none` — a failure while landing one source undoes that source's
  lines and reports it; other sources stand; the job's state is *landed, with problems*.
  *Test:* inject a failure on the second of three sources.
- `compute.land.stale-is-marked-not-refused` — a result computed from an earlier version of a
  source lands as a new pass marked with the version it was computed from. *Data:* the version
  in each result line, against the segment versions of `source-model.md` slice 5. *Test:* edit
  a page after sending; the landed pass carries the old version and a visible mark.
- `compute.land.orphans-set-aside` — a line whose source or segment no longer exists (and has
  no forwarding note) is kept in `<server state dir>/compute/jobs/<job_id>/set-aside.jsonl`,
  counted on the job with the reason, and never dropped silently. *Test:* delete one of three
  sources while the job is away.
- `compute.land.completed-means-landed` — a job is *done* only when its result package has been
  fetched, verified and landed. Built as a pure rule for Slurm (VERIFIED
  `remote_jobs.py:281-293`); this id makes it true for every kind of target. *Test:* the state
  machine never reaches *done* from *finished there* without a landing record.
- `compute.land.change-stream-tells-the-app` — landing emits the ordinary change events, so open
  windows show the new pass without a reload. *Test:* a subscriber sees one event for each
  source landed.
- `compute.land.undoable-as-one` — a landed job can be undone as one step: its passes, readings
  and cards are removed by the inverse actions, and the audit log keeps both the landing and
  the undo. *Test:* land, undo, compare with the state before.

## Test matrix

| Leg | This slice? | Pins | File |
|-----|-------------|------|------|
| Pure rule (Swift) | y | the sheet's seven lines from a package and a target; bytes shown are pending bytes | a new `compute` group under the Swift unit tests |
| Backend (pytest) | y | package contents by job kind; no paths, no secrets; one core; resume; verify on arrival; every `compute.land.*` | `fichero-server/tests/unit/workflows/`, marker `remote_compute` |
| Fixture (continuous integration) | y | SSH carrier; far side cleaned | `.github/workflows/` |
| MCP / CLI | y | a job's "what will leave" is readable as data before sending, so an agent is asked the same question a person is | `fichero-mcp/tests/`, `fichero-cli/tests/` |
| Click-around (Mac) | y | the sheet appears on the first send and not on the second | `fichero/Tests/UI/` |
| Load (#4634) | y | `compute.transfer.stays-in-the-background` | `fichero-server/tests/perf/` |

One rule for agents: an MCP or command-line caller cannot say yes on a person's behalf. A send
with no recorded yes is refused with the sheet's contents as data and the words "a person must
agree in the app".

## Open questions

1. **Is the community question right, and are its three answers right?** *Proposal: as written;
   the wording is the maintainer's to change, and the rights slice may later replace it with
   something richer (Local Contexts labels).*
2. **Does a yes cover later sends of the same kind to the same target?** *Proposal: yes. Asking
   every time trains people to click through.*
3. **Remove shared objects at once, or keep them for the next job?** *Proposal: keep until no
   unfinished job names them; "remove everything when done" is a choice on the sheet, off by
   default on a machine we control, on by default on a cluster and on Hugging Face.*
4. **Should a send be refused outright for a collection that has not answered the community
   question?** *Proposal: yes; it is asked at the first send, so nobody is blocked for long.*
5. **An agent cannot say yes.** *Proposal: agreed as a hard rule.*
