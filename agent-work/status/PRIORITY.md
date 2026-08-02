# Priority order — set 2026-08-02, from Daniel

1. **CLI + MCP.** Instruments first. *"I say MCP/CLI so you can do stuff, test,
   etc."* Once the CLI drives a live engine — local, UDS, and remote with auth
   enforced — everything below becomes testable end to end instead of by
   inspection. One real test through it is worth more than a plan for tests.

2. **Workflows, and the node editor.** *"node editor is not working either and
   needs more testing and a fabel review."* Establish WHICH failure it is before
   fixing: a graph that does not persist, a run that does not match the graph,
   or a status that lies. All three have happened here (#4139, #4396, #4457).

3. **Import.** Where a user loses files. Four instances this month of an import
   that appeared to work and did not.

4. **Everything else, filed and not worked:** #4466 iOS/iPad ratcheting,
   #4464 the interaction matrix (every surface × every interaction), #4463 the
   managed folder + iCloud sync.

## Not priority, explicitly

Daniel on #4463: *"however this is not current priority."* And on #4466:
*"again this is not priority."* Both are captured so they are not lost, and
neither gets a lane until 1–3 are done.

## Standing constraints

- Exactly TWO lanes. Mostly opus; fabel for genuinely hard reasoning.
- Lanes never build. The manager builds every 4 hours and before any release.
- Nobody runs `pytest tests/perf` outside the gate.
- Do real stuff: a user-visible fix beats three triaged closures.
