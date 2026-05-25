# Four-Agent Worktree Topology + Review Gate

**Author:** Manager Claude · **Date:** 2026-05-25 · **Status:** DECIDED (the "lighter alternative")

> **Decision (2026-05-25):** Daniel chose the 2-extra-worktree shape — frontend Claude +
> manager share the `0.0.2` trunk; only **Codex** (`0.0.2-engine`) and **pi worker**
> (`0.0.2-pi`) get their own worktrees. Frontend is un-gated (commits to trunk directly);
> Codex + pi are gated through the manager review→merge→resync flow. See "Lighter
> alternative" at the bottom — that is now the canonical topology. The four-worktree
> version below is kept for rationale only.

Answers three questions: (1) what work pi takes, (2) how the running backend works
across worktrees, (3) how the review gate runs. Then a concrete setup runbook.

---

## TL;DR

```
                         ┌─────────────────────────────────────────┐
   Manager Claude ──────►│  TRUNK: branch 0.0.2  (I own writes)     │
   (merges + review)     │  ~/code/fichero-0.0.2                    │
                         │  Persistent backend on :8765 runs HERE   │◄── Daniel's app
                         └───────────▲─────────▲─────────▲──────────┘    + pi CLI talk here
                                     │ merge   │ merge   │ merge
                  ┌──────────────────┘     ┌───┘     └───────────────┐
        ┌─────────┴─────────┐   ┌──────────┴────────┐   ┌────────────┴────────┐
        │ 0.0.2-app  (Swift)│   │ 0.0.2-engine (Py) │   │ 0.0.2-pi (simple)   │
        │ ~/…-app worktree  │   │ ~/…-engine worktree│  │ ~/…-pi worktree     │
        │ tmux: claude      │   │ tmux: codex        │  │ tmux: pi-worker     │
        └───────────────────┘   └────────────────────┘  └─────────────────────┘
   pi CLI: NO worktree — points at :8765, operates data (imports/queries). No code writes.
```

One trunk + three lane worktrees. Lanes touch **disjoint files** so merges are
conflict-free. Manager is the only writer to trunk.

---

## Q1 — What is "good-first-issue-style"? (pi's diet)

Simple = **small, self-contained, no judgment calls**. Specifically pi takes an issue only if ALL hold:

- Touches **1–3 files**, none of them god-nodes (`Database`, `KnowledgeClaim`,
  `KnowledgeEntity`, `Document`, `LLMConfig`, `WorkflowDef` — see `.claude/CLAUDE.md`).
- The fix is **fully specified** in the issue — no architecture or design decision left open.
- **Mechanical** in nature: delete dead code, remove a button, fix a string/copy,
  add a missing enum case, a one-file bug with a clear repro, a doc/test tweak.
- Verifiable by an existing command (ruff/pytest or swiftlint/build) with no new test design.

**Not pi work:** anything `needs-design`, cross-layer, touching god-nodes, or requiring
a "decide between A and B" call. Those go to Codex/frontend Claude.

**Reality check (2026-05-25):** the 0.0.2 backlog is mostly features/`needs-design`;
genuinely-simple code tasks are thin right now. Good pi starters that exist today:
- **#1205** — delete dead generated Python CLI client + its regen step (isolated, backend).
- Doc/markdown fixes, lint micro-tasks, and `#1205`-style housekeeping as they arise.

So pi gets its own worktree (per your call) **and** is allowed non-code micro-tasks
(docs, data ops) so it stays useful when the simple-code queue is empty.
Routing: label `agent:pi` + `good first issue`. pi pulls only `--label agent:pi`.

---

## Q2 — The running backend across worktrees (your main worry)

A backend server is three independent things: **which code** (which worktree) ×
**which port** × **which library** (the `.fichero` data dir). Untangling them removes
the "two backends?" problem:

**Rule: exactly ONE persistent backend, on :8765, running TRUNK code, against Daniel's
real test library.** That is the single integration surface. Daniel's app talks to it;
pi CLI talks to it. It runs *reviewed, merged* code — never an agent's in-flight work.

Everything else needs **no persistent server**:

- **Backend Codex / pi verification** = `pytest` (in-process `TestClient`) and Swift
  `EngineHarness` tests spin up their own ephemeral in-process app. No port, no daemon.
- **If a builder must poke a live server manually** → ephemeral uvicorn on **:8766**
  against a **scratch library**, killed when done. Never :8765, never Daniel's library.
  (MEMORY: *"RunAllTests pollutes the shared dev backend"* / *"don't run against a backend
  Daniel is live-testing on"* — this rule is exactly why.)

So: **not two persistent backends.** One stable :8765 (trunk) + ephemeral in-process or
:8766 scratch servers for verification. After I merge a backend change into trunk, **I
restart :8765** so Daniel's app sees the new code. uvicorn is not hot-reloading here.

**Owner of :8765 = Manager.** I start/stop it on trunk. If an agent silently relaunches
it from a lane worktree, that lane's unreviewed code leaks into Daniel's testing — so
agents must NOT run a server on :8765. (This already happened today — PID 31841.)

---

## Q3 — The review gate (how)

Gate at the **merge boundary**, not continuously. Flow per lane:

1. **Lane signals done** → writes `.ai/inbox/done-<lane>-<date>.md` (issue #, branch, one-line summary).
2. **Manager pulls the diff** → `git -C <trunk> diff 0.0.2..0.0.2-<lane>`.
3. **Spawn read-only review subagents** on that diff (parallel, one message):
   - `code-reviewer` (always)
   - `silent-failure-hunter` (always — Fichero's recurring bug class is swallowed errors)
   - `backend-reviewer` *or* type/contract focus for Python lanes
4. **Manager synthesizes** the verdicts → ALIGNED → merge; MISALIGNED → kick back via
   `.ai/inbox/review-<lane>.md` with specifics. Lane fixes, re-signals.
5. **Merge** `0.0.2-<lane>` → `0.0.2`. Disjoint files = trivial. **If backend changed,
   restart :8765.** If frontend changed, ping Daniel to rebuild the app.
6. **Lane re-syncs** trunk back (`git -C <lane> merge 0.0.2`) to avoid drift.

I can also live-peek any window any time: `tmux capture-pane -t <window> -p`.

This matches the existing CLAUDE.md QA-gate pattern (#1061) — I'm the right seat because
I'm the merge point and I write no code.

---

## Setup runbook (what to do)

### Phase 0 — Clean cruft first (manager can do after approval)
- `git worktree prune` + remove the 6 stale `.claude/worktrees/agent-*` dirs.
- Delete dead branches: `feature/issue-591/603/616`, `merge-hack`, `merge-temp`, `merged-back`,
  `claude/gracious-elbakyan-b243a2` (confirm none are in use first).

### Phase 1 — Make trunk clean + own :8765 (manager)
- Confirm `0.0.2` is the integration trunk; persistent backend runs from `~/code/fichero-0.0.2`.
- (Re)start :8765 on trunk after kills: `PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765`

### Phase 2 — Create lane worktrees (Daniel runs; restarts the tmux agents in them)
```bash
git worktree add ~/code/fichero-0.0.2-app    -b 0.0.2-app    0.0.2   # frontend Claude
git worktree add ~/code/fichero-0.0.2-engine -b 0.0.2-engine 0.0.2   # backend Codex
git worktree add ~/code/fichero-0.0.2-pi     -b 0.0.2-pi     0.0.2   # pi worker
```
Then relaunch each tmux agent **inside its worktree dir** with its session-start skill.
pi CLI stays where it is (no worktree; talks to :8765).

### Phase 3 — Routing labels (manager)
- Create `agent:pi`; tag #1205 `agent:pi` + `good first issue`.
- Lanes filter: frontend `--label frontend`, backend `--label backend`, pi `--label agent:pi`.

### Phase 4 — Wire the gate (manager, ongoing)
- Watch `.ai/inbox/done-*.md`; run the review-subagent gate; merge; restart :8765 on backend merges.

---

## Lighter alternative (if 4 worktrees feels heavy)

Keep frontend in the shared `0.0.2` tree (it's the only Swift builder, so no *cross-agent*
xcodebuild race if it's alone), and only split **engine** and **pi** into worktrees. Fewer
moving parts; trunk == frontend lane (frontend can't be gated, but it's the surface Daniel
tests directly anyway). Trade-off: frontend commits land un-gated; backend + pi stay gated.
