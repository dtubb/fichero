# The Record: who did what, kept honest and kept small. Design Spec (#TBD)

> Milestone: undo-trash-rollback
> Manual: TBD. "The history of a library": opening the list of who changed what; filtering by
> person, by kind, by run, by date; taking back an older step of your own; what an owner may
> reverse; what "the record has been checked" means.
>
> Slice 6 of the safety set. Read `undo-trash-rollback.md` first. **Status: DRAFT,
> 2026-09-20.** Behaviours carry no tag and no issue yet, by instruction. Claims about the code
> are VERIFIED (line given), TRACED or INFERRED. Nothing was run.
>
> **One part of this slice is not this slice's to settle alone:** whether the record may hold a
> researcher's words. The source-model set has the same question open (its questions 8, 17 and
> 23). Section C states the collision and one joint proposal, for the maintainer.

## Intent

Undo, Trash and Rollback all read one record. This slice makes that record worth relying on.
It is checked, not just written. It shows who did what, to a person who asks. It holds what
happened, not a second copy of the research. It is the only record: the two older ones are
folded away. And it can be read by other tools in a standard form.

This supersedes `audit.blame-and-rollback-view` (#1691, #4636) in the action-layer spec.

## Prior art

- **W3C PROV** (PROV-O, PROV-JSON). Activities, the agents responsible, the entities used and
  generated, revision and invalidation. This is the standard for exactly this record. We map to
  it; we do not store in it.
- **Certificate transparency and append-only logs.** Chain each entry to the last; publish the
  head somewhere else; **verify on a schedule**, because a log nobody checks proves nothing.
  Fichero has the first two and not the third.
- **Event sourcing.** Keep events small; keep state elsewhere; refer by id and version. We
  adopt that for new rows.
- **What we do differently.** Logs of this kind usually cannot forget. Research data sometimes
  must (a rights purge). Section C proposes how the chain can stay verifiable while content is
  removable.

## What exists

| What | State | Evidence |
| --- | --- | --- |
| One record row per action, not best-effort, inside the action's transaction | built | VERIFIED per the action-layer spec |
| A keyed hash chain over each row, with an outside anchor that detects a record cut short | built | VERIFIED by survey (`actions/audit_chain.py:27-44`, `:217-228`, `:382-400`) |
| Anything ever verifies the chain | **no**: the verify function has no caller outside tests | VERIFIED by survey (`:292`) |
| "Which tool made the change" is covered by the hash | no | VERIFIED by survey (absent from the hashed fields, `:32-44`) |
| "This step was undone" is covered by the hash | no, on purpose; it is a separate flag that can be flipped without trace | VERIFIED by survey (`:88-98`) |
| The record holds research content | yes, routinely: each transcription edit stores the page's full text twice; a folder delete stores every document row in it | VERIFIED by survey (`api/routes/document/artifacts.py:890-910`; `api/routes/document/documents.py:2501-2526`, the second VERIFIED directly) |
| Anything ever trims the record | no | VERIFIED by survey |
| A list of the record in the app, with Undo per row | built (#2085) | VERIFIED `fichero/fichero/Models/AuditStore.swift` |
| That list filters by person, kind, run or thing | no; it loads the newest hundred of everything | VERIFIED same file `:42-52` |
| The engine's list route reads the whole table and sorts in memory | yes | VERIFIED `api/routes/system/actions_registry.py:217` |
| Two older records beside it: the mutation log (with its own undo route, matched to the action record by entity id and a 30-second window) and the merge audit (its undo now a thin caller of the registry) | built; the first is the duplicate, the second is already folded the right way | VERIFIED by survey (`api/routes/kg/mutations.py:75-123`, `api/routes/kg/entity_curation.py:784-791`); #4864 |
| One place reads all the records together to decide "did a person touch this" | built | VERIFIED by survey (`workflows/curation_guard.py:200-250`) |
| Mutating routes still outside the action layer | 9 in the graph and entity routes (#4831), plus run delete, folder hard delete, snapshot delete, account delete, schedules | VERIFIED per the action-layer spec and by survey |
| The command line's audit command | reads the older record | VERIFIED by survey |

## Behaviours

### A. Checked, not just written

- `safety.record.verified-on-a-schedule` — **[GAP]** (#5247) the chain is verified in the background when a
  library is opened and at most once a day after, throttled, and on demand from Settings and
  the command line. The result is shown in Settings: "Record checked today, 09:14. 48,210
  entries. Intact." *Data:* none new; the verify function exists. *Test:* behaviour test that
  the open path calls it; load leg that it does not peg the machine on a million rows.
- `safety.record.a-break-is-loud` — **[GAP]** (#5247) a failed check stops nothing and hides nothing. The app
  says which entry and when, offers the snapshots from before that time, and the record keeps
  being written. Nothing is repaired automatically. *Test:* tamper with a row in a fixture;
  the sentence names it.
- `safety.record.everything-that-matters-is-in-the-hash` — **[GAP]** (#5247) for new rows the hash also covers
  which tool made the change and the sitting it belonged to. *Data:* a new chain mode number;
  old rows verify under their old mode, as legacy rows already do. *Existing data:* nothing is
  rehashed. *Test:* change the tool field on a new row; verification fails.
- `safety.record.undone-is-worked-out` — **[GAP]** (#5247) whether a step has been taken back is worked out from
  the chain itself: a step is undone when a live reversal row points at it. The stored flag
  becomes a cache that can be rebuilt, never the truth. So it cannot be flipped without trace.
  *Existing data:* old flags agree with their chains or are rebuilt from them. *Test:* flip
  the flag by hand; the engine still reports the step's true state.

### B. Small

- `safety.record.rows-hold-what-happened-not-the-research` — **[GAP]** (#5247) a new record row holds the action,
  who, when, the run and sitting, the ids touched, the version numbers before and after, and
  small settings. It does not hold page text, note text, or whole rows of kinds that keep
  versions. A reversal returns to a version (`versions-and-restore.md`) instead of restoring a
  copy from the record. *Data:* the version store. *Existing data:* old rows keep their
  copies and their undo keeps working from them; nothing is rewritten. *Test:* edit a long
  transcription; the new record row is under a fixed small size and undo still works.
- `safety.record.kinds-without-versions-keep-a-copy-beside` — **[GAP]** (#5247) a kind that has no version
  history (a tag, a board position, a link) still needs its earlier state to be reversed. That
  state is small and is kept in the row's content part (see C). *Test:* undo a tag change.
- `safety.record.never-trimmed` — **[GAP]** (#5247) once rows are small, the record is never trimmed or thinned.
  It is the library's memory of who did what. *Test:* a guardrail refuses a sweeper.

### C. The collision: words in a record that can never be rewritten

**The collision.** The chain exists so that the past cannot be quietly rewritten. The
source-model set plans a purge for rights reasons that must remove a segment's content
everywhere. A record that holds the content and can never be rewritten cannot honour that
purge. The source-model set found that existing actions already put researchers' words in the
chain, and that short typed reasons go there too (its questions 17 and 23), and took the
default "no words in new segment actions" pending a ruling (its question 8). Section B above
wants the same thing for a different reason (size). The two sets agree on direction. What
neither can settle alone is the old rows, and the small typed reasons.

**One proposal, for both sets.** Split each new row into two parts. The **chained part**
holds who, what, when, the ids, the version numbers, and a **fingerprint** of any content. The
**content part** holds the content itself (an earlier state for a kind without versions; a
typed reason) and sits beside the row, outside the hash. Verification checks the chained part,
and checks the content part against its fingerprint when the content is present. A purge
blanks the content part and writes its own recorded row saying so. The chain still verifies;
the words are gone; the fact that something was removed, by whom and why, is kept.

**The fingerprint is keyed, and the key is blanked with the content.** This is the
source-model set's condition, and it is a real security point. A plain fingerprint of a short
reason or a single typed word can be reversed by trying every likely word until one matches,
so the chain would go on giving the words away after a purge. So each content part carries its
own random value; the fingerprint is made from the content AND that value; the value lives in
the content part and is blanked with it. After a purge nothing remains to test a guess
against.

For **old rows**, whose content is inside the hash: they are left alone unless a purge needs
one. Then the content is blanked, and the purge's own row lists the blanked entries, so the
check reports them as "removed by a recorded purge" rather than as tampering.

- `safety.record.content-sits-beside-the-chain` — **[GAP]** (#5247) as proposed above. *Data:* two parts per new
  row; a new chain mode number. *Existing data:* old rows untouched until a purge reaches one.
  *Test:* blank a content part through the purge action: the chain verifies and reports one
  recorded removal; blank one by hand: the chain reports tampering.
- `safety.record.the-fingerprint-cannot-be-guessed` — **[GAP]** (#5247) the fingerprint of a content part is
  keyed with a random value of at least 128 bits, made per row, stored in the content part
  and blanked with it. *Test:* purge a row whose content was one common word; with the chained
  part alone, trying a word list finds no match; before the purge, with the content part
  present, verification still passes.
- `safety.record.a-typed-reason-is-content` — **[GAP]** (#5247) a reason or note typed by a person with a step is
  content, not chained text. *Test:* it can be purged.

**Where it stands.** The source-model set's author agreed this as the joint proposal on
2026-09-20, with the keyed fingerprint as their condition (their commit b5b8fa925). It is
still the maintainer's to rule. It would unblock the purge in their rights slice. Version rows
are already outside the chain on their branch, so a purge can reach those today.

### D. Seeing who did what

- `safety.record.a-history-of-the-library` — **[GAP]** (#5247) one view lists who changed what, newest first,
  filtered by person, by kind of thing, by run, by date, or for one thing (the Inspector's
  History section links here). Each row is a sentence: "Ana moved Letter 12 to Box 3." Rows
  made by a machine say so and name the run. *Data:* the record, paged and filtered in the
  database; the name templates of `safety.undo.menu-names-the-step`. *Test:* the list equals
  the record under each filter; load leg.
- `safety.record.you-see-what-you-may-see` — **[GAP]** (#5247) a row about a thing a person may not see is not
  shown to them, names included. The → #4917 rules apply to the record as to the thing. *Test:*
  deny a viewer on a folder; rows about its documents are absent from their list.
- `safety.record.reverse-from-here` — **[GAP]** (#5247) from this view a person can take back an older step of
  their own, and an owner can reverse anyone's (`safety.undo.owner-may-reverse-anyone`), one
  chosen step at a time, under the same two locks. Reversing here is never bulk; bulk is a run's
  take-back. *Test:* in `undo.md`.

### E. The only record

- `safety.record.one-record` — **[GAP]** (#5247) nothing new is written to the older mutation log. Its rows stay
  readable for ever. Its undo route first refuses what the action layer owns, naming the right
  route (→ #4864), then is removed once no client calls it. The 30-second matching goes with it.
  The merge audit stays as the merge's own working data (which aliases moved), reached only
  through the registry. *Existing data:* kept and readable; nothing converted. *Test:* an
  entity delete writes one row in one record; the older undo route refuses it by name.
- `safety.record.one-reader-of-the-past` — **[GAP]** (#5247) "has a person touched this" is answered from the
  record, and from the older tables only for rows older than this slice. *Test:* the curation
  guard's tests pass with the mutation log empty for new rows.
- `safety.record.every-change-is-in-it` — **[GAP]** (#5247) every route that changes a library goes through the
  registry: the nine graph and entity routes (→ #4831), deleting a run, deleting a folder's
  contents, deleting a snapshot, schedules. The guardrail that checks this covers every route
  folder, not two. Deleting an account is outside any one library; it is recorded in the
  server's own record. *Test:* the guardrail at zero.
- `safety.record.the-command-line-reads-it` — **[GAP]** (#5247) the command line's audit command reads this
  record. *Test:* CLI leg.

### F. A standard form

- `safety.record.reads-as-prov` — **[GAP]** (#5247) the record can be exported as W3C PROV with the library's
  other linked-data exports. A row is an activity. The account is the agent: a person, or a
  software agent acting on behalf of the person who started it. A run is an activity that the
  rows were informed by. A thing at a version is an entity; the next version is a revision of
  it; a reversal invalidates what it took back; a restore is derived from the version it
  returned to. *Data:* a mapping only; nothing is stored in PROV. *Test:* the export validates
  against the PROV constraints for a small fixture.

## Things to try by hand

1. Settings says when the record was last checked, how many entries, and "Intact".
2. Open the library's history. Filter to yourself, then to one run, then to one document.
3. Edit a long transcription ten times. The library file has grown by about the size of the
   versions, not by twenty copies of the page.
4. As an owner, reverse another person's step from the history. Both names appear.
5. As a viewer denied on a folder, open the history. Nothing about that folder is listed.

## Test matrix

| Leg | This slice? | Pins | File |
| --- | --- | --- | --- |
| Backend (pytest) | y | A, B, C, E with a real database | extends `fichero-server/tests/unit/actions/test_action_audit_chain.py` |
| Guardrail | y | every mutating route in every folder uses the registry; no sweeper of the record | extends `scripts/check_routes_use_action_layer.py` |
| MCP / CLI | y | list and filter the record; verify the chain | the MCP and CLI suites |
| Availability (Swift) | y | the history view; the "record checked" line | the availability suite |
| Click-around (Mac) | y | the five things above | the UI suite |
| Load | y | a million rows: list, filter and verify within the ratchet, machine not pegged | the perf suite |

## Open questions

**Answered** (source/source-model.md Rulings 2026-09-20 item 5): No words in the chained record; content part outside the chain that a purge can blank. See the questions file. From this slice: words in the record (jointly with the source-model
set); the record is never trimmed; the older record retires.
