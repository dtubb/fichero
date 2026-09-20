# History and Restore: return this thing to how it was. Design Spec (#TBD)

> Milestone: undo-trash-rollback
> Manual: TBD. "Seeing what it said before": opening a thing's history; who changed it, when,
> and whether a person or a machine did; comparing two versions; returning to an earlier one;
> why returning never loses the versions in between.
>
> Slice 3 of the safety set. Read `undo-trash-rollback.md` first. **Status: DRAFT,
> 2026-09-20.** Behaviours carry no tag and no issue yet, by instruction. Claims about the code
> are VERIFIED (line given), TRACED or INFERRED. Nothing was run.
>
> **This slice builds ON the source-model set** (branch `spec/page-model`, its slices 4 and 5
> and its slice 6 build notes, commit 76c6c0146). That set owns the version store. This slice
> adds no second store. Where a rule here would change theirs, it is written as a request in
> the foundation file, not as an edit to their files.

## Intent

Every thing a researcher works on keeps its earlier versions. From the Inspector a person can
see what a transcription, a note, a statement or an entity said before, who changed it, when,
and whether a person or a machine did. They can compare two versions and return to an earlier
one. Returning is a new version on top, so nothing in between is lost and the return can itself
be undone.

Undo is for the last few minutes. History is for last month.

## Prior art

- **Wikis and Google Docs.** Version history per page; restore makes a new revision; nothing is
  ever removed from the middle. We adopt exactly that.
- **Scholarly editing** (TEI's revision description; the apparatus of a critical edition). A
  reading records who made it and on what basis. The source-model set's readings already do.
- **W3C PROV.** A version is an entity; a later version `wasRevisionOf` the earlier; a restore
  `wasDerivedFrom` the version it returned to; the person or model is the agent. We map to it
  (`the-record.md`) rather than invent terms.
- **What we do differently.** Image edits are already history done right: stored as settings,
  original untouched, return-to-original reversible. They need no version rows and get none.

## What exists

| What | State | Evidence |
| --- | --- | --- |
| Version history of anything, on the main line | **none** | VERIFIED by survey |
| Segment and text-artifact version tables; a restore that writes a new version; numbers only go up; an expected-version check on update, delete and restore | built on the unmerged source-model branch only | VERIFIED by survey of that worktree |
| Merge, split and carry take no expected version | gap on that branch | VERIFIED by survey; noted by that set's own reviewer |
| Image edits as settings; original never written; return-to-original reversible | built, and right | VERIFIED `api/routes/ingest/image_editing.py:1615-1618`; byte-level test per survey |
| Undoing an edit restores the whole row from a copy kept in the record | built; this is what the record's size problem comes from | VERIFIED by survey `api/routes/document/artifacts.py:252-255`, `:890-910` |
| A "who changed what" view over documents, entities, statements and notes | not built (#1691; design issue #4636) | VERIFIED by survey |
| Workflow definition history | not built (#4342) | VERIFIED by survey |

## Behaviours

### A. One version store

- `safety.history.one-store`: there is one way versions are kept: the source-model set's. A
  version is an ordinary row beside the thing, holding the content as it was, its number, who,
  when, which recorded step made it, and whether a person or a machine made it. Other kinds
  follow the same shape; none invents its own. *Data:* the source-model tables for segments
  and text artifacts; same-shaped tables for the kinds in B. *Existing data:* see C. *Test:*
  a guardrail: a table that stores earlier content of a thing matches the one shape.
- `safety.history.versions-are-ordinary-data`: versions live with the research, not in the
  tamper-evident record. So access rules reach them, a purge can reach them, and a snapshot
  carries them. The record refers to a version by number (`the-record.md`). *Test:* deny a
  viewer on a document; its versions are refused too (#4917).

### B. What keeps history

- `safety.history.the-kinds`: these keep versions: a **segment** and a **text artifact**
  (source-model set); a **note**; a **statement**; an **entity**'s name, kind, aliases and
  description; a **workflow**'s definition (#4342). These do not: tags, ratings, positions on
  a board, links (they are undo only, and the record shows them); images (their edit settings
  are their history). *Test:* one behaviour test per kind: three committed changes leave three
  versions.
- `safety.history.a-version-per-committed-change`: a version is written when a change is
  committed, not per keystroke. One uninterrupted stay in a text field is one version, by the
  same folding rule as `safety.undo.commits-are-not-per-keystroke`. *Test:* three autosaves in
  one stay leave one new version.
- `safety.history.a-machine-never-writes-over-a-person`: a workflow or an agent that re-reads
  or re-extracts does not replace a person's version. For segments and readings the
  source-model rule holds (a new pass). For statements and entities, a machine's change to a
  thing a person has curated arrives as a proposal, not a new version. *Data:* the existing
  curation guard already reads the record to know what a person touched (VERIFIED by survey,
  `workflows/curation_guard.py:200-250`). *Test:* curate a statement; re-run extraction; the
  statement's text and version are unchanged.

### C. Existing libraries

- `safety.history.history-starts-at-the-first-change`: nothing batch-writes versions into an
  existing library. A thing's present content becomes its first version at the moment it is
  next changed, in the same transaction as that change. Until then its history reads "No
  earlier versions." This is the source-model set's "convert on first edit" rule, applied to
  every kind. *Existing data:* untouched until edited; nothing discarded. *Test:* open an old
  library; no table grows; edit a note; it now has two versions, the first equal to what the
  note said before.
- `safety.history.older-record-copies-stay-readable`: steps recorded before this slice keep
  the full copies they already hold, and undo of those steps keeps working from them. They are
  not converted. *Test:* undo a pre-existing recorded edit after the upgrade.

### D. Looking, comparing, returning

- `safety.history.in-the-inspector`: the Inspector shows a History section for the selected
  thing, only when the thing is of a kind that keeps history: each version with who, when, and
  a person or machine mark, newest first. *Test:* availability; click-around.
- `safety.history.compare`: any two versions can be compared side by side with the changes
  marked; for a transcription, against the page image. *Test:* click-around.
- `safety.history.restore-is-a-new-version`: returning to version 3 writes a new version whose
  content equals version 3. Versions 4 onward remain. Numbers only go up. The restore is one
  recorded step, mine, and Command-Z takes it back. *Data:* as built on the source-model
  branch for segments. *Test:* five versions; restore 3; six versions; content of 6 equals 3;
  undo; content equals 5.
- `safety.history.restore-obeys-the-locks`: a restore names the version it was made against
  and is refused if the thing has moved on since the person opened the history
  (`safety.undo.version-is-the-second-lock`). Merge, split and carry need the same token.
  *Test:* open history; someone else edits; restore is refused with the plain sentence.
- `safety.history.what-rests-on-it-is-shown`: before returning a transcription to an earlier
  version, the app says what rests on the present one: how many statements and annotations
  quote text that the earlier version does not contain. It does not block. After the restore
  those are marked for review, not deleted. *Test:* restore across a removed sentence; the
  statement resting on it is marked.

### E. History and the other two words

- `safety.history.the-trash-keeps-history`: a thing in the Trash keeps its versions, and Put
  Back returns them. Emptying the Trash removes them with the thing. *Test:* both.
- `safety.history.a-purge-reaches-versions`: a purge for rights reasons
  (source-model set, #4953) removes the content of every version of the thing, leaving the
  version rows as stated absences. *Test:* theirs; cited here so the two agree.

### F. From everywhere

- `safety.history.command-line-and-agents`: list a thing's versions, read one, compare two,
  restore one, through the same actions, from the command line and the agent tools. An agent's
  restore is a machine-made version under B's rule. *Test:* CLI and MCP legs.

## Things to try by hand

1. Edit a transcription three times over a day. Open its History. Three versions, your name,
   the times.
2. Compare the first and the last against the page image.
3. Restore the first. There are now four versions. Command-Z. There are still four, and the
   text is the third again.
4. Run a workflow that re-reads the page. Your version is untouched; the machine's reading is
   beside it.
5. Open an old library. Nothing is slow, nothing has changed. Edit a note. It has two versions.

## Test matrix

| Leg | This slice? | Pins | File |
| --- | --- | --- | --- |
| Backend (pytest) | y | A to E, real database, two accounts | beside the source-model set's version tests |
| Guardrail | y | one version shape | new check |
| Availability (Swift) | y | History section only for the kinds that keep it | the availability suite |
| MCP / CLI | y | F | the MCP and CLI suites |
| Click-around (Mac) | y | D and the five things above | the UI suite |
| Load | y | a thing with 10,000 versions lists within the ratchet | the perf suite |

## Open questions

See the questions file. From this slice: which kinds keep history; history starts at the first
change after the update and is not back-filled; how long versions are kept (proposal: always).
