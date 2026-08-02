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

## Sidebar IA — half-migrated, and one question for Daniel (2026-08-02)

Full analysis: `agent-work/status/2026-08-02-sidebar-ia-decision.md` (lane-crash2).

**The finding: the sidebar IA is HALF-MIGRATED, which is worse than either
end state.** The duplicate entry points were removed (pinned bottom nav rows,
#4102's removal half) but the modes they duplicated remain — `ViewSettings`
still declares `.research` and `.knowledgeGraph`, and `SidebarModeIcon`
renders `allCases`. So research and entities are now reachable ONLY through a
mode bar the rest of the design has moved away from. Fewer doors to a room
nobody meant to keep.

`SidebarItem.ItemType` holds 12 node kinds and has NO case for workspace,
research project, or entity — the tree can express most of #4335 and
specifically cannot express the three things this decision is about.

**Recommendation:** close #1686, #1738, #1793, #2446, #2447 as duplicates of
#4102 — but #1686 carries a detail the others lose and it must be transcribed
first: entities should reuse LibraryView's view-mode machinery, not merely
appear in the tree.

**THE QUESTION ONLY DANIEL CAN ANSWER:** an entity is not a container the way
a folder is — its children are a QUERY RESULT. So what does "add photos to a
person" mean?

- If it ASSERTS a claim (this photo depicts this person), the drop is a
  knowledge-graph write and belongs to the SVO/claims spine.
- If it PINS an exception to a query, entities need a membership store that
  folders do not have.

These are different products. Nothing should be built until this is answered,
and no lane may guess it.
