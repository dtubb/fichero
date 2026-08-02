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

5. **CLI + MCP** — instruments. Worth finishing because they make 1–4 testable
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
