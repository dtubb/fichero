# Dev Orchestration Harness — how we work — Design Spec (#TBD)

> Milestone: dev-orchestration-harness
>
> Design-led. **Status: DRAFT — for Daniel's review.** How the agent team is structured to get
> work done without wasting tokens. Grounded in what this session actually showed.

## The question

Proposal: Daniel → several **opus area-managers** (KG, testing, backend, frontend), each in its
own tmux window, each managing **sonnet workers** that implement+test a feature; everyone uses
jCodemunch. Is a two-layer (opus-manager → sonnet-worker) tree the right shape, and how do we do
it token-efficiently with fabel/opus?

## What this session taught us (the evidence to design from)

1. **The expensive work was THINKING, not writing.** The KG-readable pipeline (writing) was cheap
   and fast. The costly parts were **root-causing the UI harness** (4 hidden layers) and
   **reviewing drifted tests vs code** — judgement, not typing. → Spend opus on reasoning
   (design, debug, review); spend cheap models on mechanical implementation.
2. **Verification is the bottleneck.** Once the CLI build path was unblocked, a full unit run is
   ~2 min and a UI run ~2.5 min, serialized. More *writers* don't help if every change waits on
   one slow verify. → Optimize the verify loop (targeted `-only-testing`, the isolated
   `-derivedDataPath`, headless pytest) before adding parallel writers.
3. **A layer that only coordinates is the waste.** An opus manager whose job is dispatch reads
   context and hands off — high token cost, low reasoning value.

## Ruling proposal (the design)

- **Keep it FLAT by default.** Daniel → **me (opus)** → **sonnet/codex workers** for
  implementation. Me = design + root-cause + review + the verify gate. Workers = write to a spec,
  run their own area tests, report. No standing opus middle layer for routine work.
- **Add a dedicated opus "area lead" ONLY for a large, long-running milestone** whose context is
  too big to hold alongside everything else (e.g. a whole KG or testing milestone). It owns that
  milestone, dispatches its own sonnet workers, and reports up. One or two at a time — not one per
  area on principle. This is the existing `session-start-milestone-worker` pattern; reuse it.
- **Model routing (the token policy):**
  - **opus / me** — design specs, root-cause debugging, code/test review, the merge/verify gate.
  - **sonnet** — implement a specced feature + its tests (the bulk of writing).
  - **codex / haiku** — mechanical/bulk edits, boilerplate, doc sweeps, bounded refactors.
  - **fabel** — fast interactive UI iteration where speed beats depth (visible in Xcode).
  - Route DOWN, never up: never use opus for what sonnet can do; never use sonnet for what a
    guardrail/script can do.
- **tmux windows vs subagents:** subagents (the `Agent` tool) for **bounded parallel tasks** that
  report back within a turn (context-isolated, no plumbing). Persistent **tmux lanes** only for
  **long-lived autonomous work that must survive across turns** (an overnight milestone). Don't
  spin tmux windows for tasks a subagent finishes in one pass.
- **jCodemunch for all navigation** (already the rule) — it's the shared, token-cheap index.
- **The verify gate is mine, non-negotiable.** Workers write + run their area tests; I run the
  cross-cutting build/test before anything lands (this session's `-testPlan fichero` +
  isolated-DD CLI path is the recipe). Unverified worker output does not merge.

## Behaviors

- `orch.flat-default` [PROPOSED] — routine work is Daniel → me → sonnet/codex, no opus middle layer.
- `orch.area-lead-on-demand` [PROPOSED] — an opus area-lead only for a large milestone; ≤2 at once.
- `orch.model-routing` [PROPOSED] — the routing table above; route down.
- `orch.verify-gate` [OK, keep] — I own the cross-cutting verify; unverified worker output blocks.
- `orch.subagent-vs-tmux` [PROPOSED] — subagents for bounded tasks, tmux only for cross-turn lanes.

## Open questions for Daniel

1. Is a standing opus area-lead per area worth its coordination cost, or is on-demand (per big
   milestone) enough? (I lean on-demand — this session was all done flat + fast.)
2. fabel's role: reserve it for visible Xcode UI iteration, or also for cheap bulk writing?
3. **Agents/skills audit:** there are ~31 agents and ~138 skills loaded. Many overlap
   (multiple code-reviewers, multiple session-start variants, several planning skills). Worth a
   pass to cut the ones we never invoke — separate short task, listed as a follow-up below.

## Follow-ups (do when the token budget resets — not now)

- Audit agents + skills; propose a trimmed set (the overlapping reviewers/planners especially).
- Create the `dev-orchestration-harness` GitHub milestone + issues for the routing policy.
- Fold the routing table into `AGENTS.md` (the operational manual) so every lane obeys it.
- User manual: Daniel documents "how we work" for the guide once the policy is settled.
