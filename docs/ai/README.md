# AI Guide

Fichero is built by AI agents working under Daniel Tubb's direction. This guide is
what those agents read. It is published rather than hidden because how the software
is made is part of what the software is — see [How It's Built](../user/how-its-built.md).

There are three guides: the [User Guide](../user/README.md) for people using
Fichero, the [Developer Guide](../contributor/README.md) for people building it,
and this one for the agents that write most of the code.

## In this guide

- **[CLAUDE.md](./CLAUDE.md)** — the architecture and development guide. How the
  system is shaped, the conventions, the pitfalls. The longest document an agent
  reads, and the one it re-reads.

## Outside this guide, and canonical

These live at the repository root because tooling and agent harnesses load them by
path. They are not published pages.

- **[`AGENTS.md`](https://github.com/dtubb/fichero/blob/main/AGENTS.md)** — the
  operational manual. Hard rules, key paths, commit attribution, the
  manager-with-workers loop, code-navigation policy. **Read it first.** Where it
  disagrees with anything here, it wins.
- **[`agents/`](https://github.com/dtubb/fichero/tree/main/agents)** — the harness
  itself: the skills each lane loads (`agents/skills/`), the reusable prompt
  fragments they compose (`agents/prompts/`), and `agents/ROADMAP.md`, the priority
  spine that `scripts/choose_next.py` reads to decide what happens next.
- **[`CONSTITUTION.md`](https://github.com/dtubb/fichero/blob/main/CONSTITUTION.md)**
  — the product north star: what Fichero is, what it is not, and the constraints
  that do not change.

## How the work actually flows

A **manager** reads the roadmap spine, picks the next milestone, and dispatches it
to a **worker** running in its own git worktree. The worker drains the milestone
issue by issue, committing as itself — never as Daniel. It never builds and never
runs the full test suite; the machine is slow and the manager owns the single
build-and-gate. Green work is merged by PR; red work becomes tracked issues, one
per failure.

Each worker loads the skill for its lane — `session-start-worker-docs`,
`-tester`, `-release`, or the generic `session-start-worker` — so it configures
itself rather than being hand-briefed each time.

## The rule that matters most

**Documentation describes what is built, not what is planned.** Before writing any
claim, verify it against the tree: a feature is live only if its flag is true in
`FeatureManager.resetToV001()`; a path exists only if `git ls-files` says so; a
script does only what its argument parsing says. The
[feature matrix](../user/features.md) is derived this way, and so should everything
else be.

An AI that writes confident, wrong documentation has done more damage than one that
wrote none.
