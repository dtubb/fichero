# Dev Orchestration Harness — how we work — Design Spec (#TBD)

> Milestone: dev-orchestration-harness
> Manual: TBD — the contributor manual has no "how the agent team works" page. It needs one:
> the manager/worker split, how a lane is dispatched, which model each role runs, and how work
> is claimed so two lanes never take the same issue. `AGENTS.md` holds the rules today.
>
> Design-led. **Status: DRAFT — model RATIFIED by the design lead 2026-09-12** (Fabel manager, sonnet/opus
> workers). Stays DRAFT until its enforcement lands — a guardrail asserting the routing policy is
> in `AGENTS.md` — because a governance spec has no code surface to bind a test to. How the agent
> team is structured to get work done without wasting tokens. Grounded in what this session showed.

## The model — roles, and a swappable model list

Work is **one layer deep**: a MANAGER dispatches WORKERS. Roles are stable; the model bound to each
role is config — **swap a model by editing its row; add/remove a model without touching the prose.**

| Role | Current model | Purpose |
|------|---------------|---------|
| **manager** | `fabel` | always-on driver: coordinate, fast design/routing/review, own the verify gate. Does not grind implementation when a worker can. |
| **worker — default** | `sonnet` | implement a specced feature + its tests, bulk/mechanical edits, doc sweeps. Most writing. |
| **worker — deep** | `opus` | escalation only: hard root-cause debugging, tricky design, deep review. One or two at a time. |

This inverts the usual tree — the manager is *cheaper* than the deep worker, which is correct:
spend the expensive model only on hard reasoning, keep the always-on coordinator fast and cheap.
The `Current model` column is the only thing that changes when the model roster changes.

## The question

Proposal: the design lead → several **opus area-managers** (KG, testing, backend, frontend), each in its
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

- **Keep it FLAT by default.** the design lead → **me (Fabel)** → **sonnet workers** for implementation
  (**opus workers** only for hard reasoning). Me = fast design + routing + review + the verify
  gate. Workers = write to a spec, run their own area tests, report. No standing middle layer.
- **Add a dedicated opus "area lead" ONLY for a large, long-running milestone** whose context is
  too big to hold alongside everything else (e.g. a whole KG or testing milestone). It owns that
  milestone, dispatches its own sonnet workers, and reports up. One or two at a time — not one per
  area on principle. This is the existing `session-start-milestone-worker` pattern; reuse it.
- **Routing (the token policy):** the manager does design/review/routing + the verify gate;
  the **default worker** does the writing (features, tests, bulk edits, doc sweeps); the **deep
  worker** is escalation-only (hard debugging, tricky design, deep review). Route DOWN for writing,
  escalate UP only for hard reasoning, and never spend any model on what a guardrail/script already
  does. (Which model fills each role: the table above.)
- **tmux windows vs subagents:** subagents (the `Agent` tool) for **bounded parallel tasks** that
  report back within a turn (context-isolated, no plumbing). Persistent **tmux lanes** only for
  **long-lived autonomous work that must survive across turns** (an overnight milestone). Don't
  spin tmux windows for tasks a subagent finishes in one pass.
- **jCodemunch for all navigation** (already the rule) — it's the shared, token-cheap index.
- **The verify gate is mine, non-negotiable.** Workers write + run their area tests; I run the
  cross-cutting build/test before anything lands (this session's `-testPlan fichero` +
  isolated-DD CLI path is the recipe). Unverified worker output does not merge.

## Behaviors

- `orch.flat-default` [PROPOSED] — routine work is design lead → manager → default worker, no middle layer.
- `orch.area-lead-on-demand` [PROPOSED] — an opus area-lead only for a large milestone; ≤2 at once.
- `orch.model-routing` [PROPOSED] — the routing table above; route down.
- `orch.verify-gate` — **[CONVENTION]** (retagged 2026-09-18 — previously tagged OK-and-keep) I
  own the cross-cutting verify; unverified worker output blocks. This is a manager discipline about
  WHO runs the gate and WHEN a merge is allowed — the same `verify_all.sh` runs identically no
  matter who invokes it, so there is no code path that could regress independently of a human/
  agent choosing to skip this step. See `git-worktree-workflow.md`'s "Marking a convention"
  section for the same class of tag and the proposal to add real `CONVENTION` support to
  `spec_pipeline.py`.
- `orch.subagent-vs-tmux` [PROPOSED] — subagents for bounded tasks, tmux only for cross-turn lanes.

## Open questions for the design lead

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
- User manual: the design lead documents "how we work" for the guide once the policy is settled.
