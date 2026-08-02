# Priority order — set 2026-08-02, from Daniel

**Revised after:** *"we want paleography and workflows and sidebar and stuff
new users see."*

That is the through-line: **what Ann actually encounters.** Not infrastructure,
not ratchets, not architecture — the work she does, the way she navigates, and
what the app looks like the first time.

1. **Paleography / historical text** — milestone #265. This is her real work:
   #3320 text normalisation (NFC + ftfy), #3321 normalized_content + folded
   index, #3322 histdate, #3323 cross-script entity variants, #3324 paleography
   fonts + diplomatic render, #3325 translation, #3326 transliteration.
   #3319 is a grounded fabel plan already written for it — read that first
   rather than re-deriving.

2. **Workflows, and the node editor.** *"node editor is not working."*
   Establish WHICH failure before fixing: a graph that does not persist, a run
   that does not match the graph, or a status that lies. All three have
   happened (#4139, #4396, #4457).

3. **Sidebar** — milestone #116. How she navigates. Two delete crashes lived
   here this week.

4. **What a new user sees** — first run, empty states, the launch prompt
   (#4017: the app asks a question before it will show you anything).

5. **Document reader and document inspector** — where she actually reads.
   Daniel, on his way out: *"document inspector, document reader are also
   important. entity editor. SVO."* The inspector lists have a live defect he
   named earlier: *"you can't properly click on an icon and some operations
   don't work properly."*

6. **Entity editor** — how she corrects the knowledge graph. Curation is
   persistent and constrains later imports, so an edit that does not stick, or
   sticks in the wrong place, is worse than one that fails loudly.

7. **SVO / claims** — subject-verb-object extraction and its surfaces.
   The through-line with 5 and 6: this is the READ → THINK → WRITE spine, and
   it is what the app is FOR. Milestones #151 Inspector Knowledge (33 open) and
   the claim/citation surfaces.

8. **CLI + MCP** — instruments. Worth finishing because they make 1–4 testable
   end to end, but they are a means, not the goal.

## Captured, explicitly NOT worked

Daniel on #4463 (managed folder / iCloud sync): *"this is not current
priority."* On #4466 (iOS/iPad ratcheting): *"again this is not priority."*
Also #4464 (interaction matrix). All filed so they are not lost; none gets a
lane until the above is moving.

## Standing constraints

- Exactly TWO lanes. Mostly opus; fabel for genuinely hard reasoning.
- Lanes never build. The manager builds every 4 hours and before any release.
- Nobody runs `pytest tests/perf` outside the gate.
- **Do real stuff.** A user-visible fix beats three triaged closures.

## Blocked on Daniel — Tuesday (added 2026-08-02)

Paleography #265 is six sequenced steps and step 1 cannot start without two
answers. Both are editorial/authority decisions, not engineering ones, so no
lane may guess them.

1. **#3320 Q1 — is NFC-normalised text acceptable as diplomatic content?**
   The text-normalisation choke point cannot be written without this; the
   contract changes depending on the answer. A diplomatic transcription is
   supposed to preserve what the manuscript actually shows, and Unicode
   normalisation silently changes some of it.

2. **#3320 Q6 — backfill sign-off (the #3077 analog).**
   Backfilling normalised text rewrites the Marshall Diaries. Real data,
   never nuked, changes need db_migrations.py. This is authorisation, not
   implementation.

#3321 sits on top of both.

**Unblocked and queued:** #3322 histdate — the largest piece needing neither
answer, and the one Ann would feel first. A diary corpus is navigated by
date, and today sort/filter uses created_at (import time), which is
meaningless for the Marshall Diaries. Green-field, touches no existing
content. Cheap precursor: add ftfy/anyascii/convertdate/jdcal to pyproject
(unblocks three later steps).

**Also for Daniel:** #2397 cross-library drag. There is no cross-library move
action; every path terminates in one library's documentStore.moveDocument,
and a client-orchestrated version cannot be atomic across two databases.
Destructive + Marshall Diaries + a semantics question = his call.
