(AI generated. Not reviewed.)

# How Fichero Is Built

Fichero is built openly with the help of AI coding agents. This page documents
how that actually works, as the concrete process
the project follows. It is grounded in the workflow files that live in the
repository: `AGENTS.md` (the canonical agent constitution + operational manual),
`CLAUDE.md`, `MEMORY.md`, `agents/ROADMAP.md`, and the skills under
`agents/skills/`.

## Why document this

The project is transparent about its construction for the same reason the app
itself treats AI as an **instrument, not an interlocutor**: you should be able to
see what the machine actually did. The agent workflow has guardrails, review
gates, and verification steps precisely so that AI assistance does not mean
unreviewed code.

## The two core roles

Work is organized around a **manager / worker** split. In the current repo, the
canonical reusable skills live under `agents/skills/`:

- **Manager** (`session-start-manager`): the control lane. It reads project
  state and the roadmap, triages GitHub issues, decides what to do next, and
  dispatches work. The manager **does not write product code**; it coordinates.
- **Worker** (`session-start-worker`): the implementation lane. A worker picks
  up exactly one assigned issue, implements it completely, writes tests, runs the
  required verification gates, commits, and reports back.

GitHub Issues and Milestones are the source of truth for the backlog. The
project works **one milestone at a time** (groom it, work it to done, then move
on) rather than against a version number.

## The manager loop

The manager runs a deterministic loop built from two skills:

1. **`choose-next`**: reads `agents/ROADMAP.md` (the priority tiers: Gates →
   Infrastructure → Observable approaches → Features → Domain → Mac polish →
   Testing → Profiling → UI consistency) and the open GitHub milestones, then
   returns the next batch: either one large keystone issue, or 3–10 small issues
   from the **same** milestone, sized to fit a worker's context.
2. **`dispatch-worker`**: spawns that batch the right way, then integrates the
   result.

## Worktree-isolated workers

Each worker runs in its own **isolated git worktree** so parallel work never
collides:

- Worktrees live under a single dedicated parent directory, created with
  `git worktree add`. They are **never** bare siblings of the repo, and risky
  filesystem operations are gated by an explicit safety rule (`git worktree
  remove --force` only; never `rm -rf` a sibling path).
- Before fanning out more than one worker, the manager **partitions work by
  file-set** so lanes touch disjoint files; parallelism is only free when two
  lanes don't both rewrite the same module.
- Cheap models are the default; more capable models are reserved for keystones
  (new data stores, the action layer, high-blast-radius changes).

## Resource discipline

A few hard rules keep the machine usable while agents run:

- **Workers verify their own diff; integrators own the full gate.** Backend
  workers run focused `ruff` and `pytest` on the area they changed. Swift
  workers run `swiftlint` on the touched surface. The manager/integrator owns
  the full Xcode build, the full `FicheroTests` run, and the cross-stack
  verification gate before merge.
- Build, lint, and test logs are pushed **off** the lead agent's context: the
  lead reads a pass/fail verdict, not the full log.

## Three execution modes

The workflow picks the lightest tool that fits the task:

| Mode | What it is | Use when |
|---|---|---|
| **Single session** | The lead does the work inline | Sequential edits, overlapping files, many dependencies |
| **Subagent** | A helper spawned to report one result back | Focused build/lint/test or "trace why X happens" where only the result matters |
| **Agent team** | Peer sessions sharing a task list | Work that needs discussion: parallel review, competing-hypothesis debugging, disjoint cross-layer features |

## The QA review gate

Before a sweep of changes is committed, the project runs a **review gate** rather
than self-certifying. The current workflow files point the manager at distinct
review passes before merge, including a code-review pass, a simplification
pass, and then the build/test integration gate.

The lead **synthesizes** the findings, applies fixes, and only then commits. In
autonomous (unattended) runs, this review team *is* the gate, since there is no
human at the keyboard.

## Build-gate before merge, verify before push

Two non-negotiable rules close the loop:

- **Never mark work complete without build + test + lint passing.** The exact
  commands live in `CLAUDE.md` (fichero-server `pytest` with `PYTHONPATH=fichero-server/src`,
  `ruff` for Python, `swiftlint` and an Xcode build for Swift).
- **Never push on top of an unverified commit.** The verification summary is read
  and parsed; work is pushed **only** when the suite is green. A change always
  reaches `main` through a pull request, never a direct push.

## Durable memory

What the agents learn persists. `MEMORY.md` indexes durable lessons and decisions
(recurring bug patterns, hard rules such as "iterate, never replace"
existing code, and architectural facts) so that future sessions start informed
rather than relearning the same mistakes. The `session-end` skill is what writes
those lessons down at the end of a working session.

---

*This page describes the development workflow, not a feature of the app. For
the detailed operating rules, see `AGENTS.md` and the current skills under
`agents/skills/`.*
