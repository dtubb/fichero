# Agent workflow skills

These skills describe Fichero's manager-with-workers development loop. A **manager**
session reads project state and the roadmap, decides what to do next, and
dispatches **isolated workers** in external Git worktrees. Each worker implements
one issue (or a small milestone slice), writes tests, and commits. The manager/
integrator then runs the build / test / lint gates and lands the work to the
working branch.

The loop is intentionally split into narrow lanes so parallel agents don't
collide: a manager picks work, workers claim issues via the `status:in-progress`
label, a reviewer checks the diff, and an integrator verifies and merges.

## The manager-with-workers loop

1. **Start the manager**: [`session-start-manager`](session-start-manager.md) loads
   context and decides what to work on.
2. **Choose the next batch**: [`choose-next`](choose-next.md) reads the roadmap and
   returns the highest-priority, ready-to-work issues.
3. **Dispatch a worker**: [`dispatch-worker`](dispatch-worker.md) creates an external
   worktree and briefs a coding agent (cheap model by default, Opus/codex-5.5 only
   for keystones).
4. **Implement**: lane-specific workers pick up the brief and do the work
   ([`session-start-worker`](session-start-worker.md),
   [`session-start-milestone-worker`](session-start-milestone-worker.md), or
   domain lanes like engine, SwiftUI, CLI, docs, etc.).
5. **Review + integrate**: [`session-start-reviewer`](session-start-reviewer.md) and
   [`session-start-integrator`](session-start-integrator.md) gate the diff before it
   lands.
6. **End the session**: [`session-end`](session-end.md) updates durable memory and
   leaves a clear entry point for the next run.

Special lanes: [`session-start-planner`](session-start-planner.md) for big/ambiguous
feature shaping, [`session-start-bugtriage`](session-start-bugtriage.md) for unclear
bug reports, [`session-start-team`](session-start-team.md) for headless multi-agent
orchestration, and [`status`](status.md) for a quick project pulse check.

## Placeholders used here

- **`<repo-root>`** — root of the cloned Fichero repository.
- **`<worktrees-root>`** — directory that holds Git worktrees (e.g.
  `<repo-root>/../worktrees` or any path you choose).
- **`<code-dir>`** — your local projects parent directory (e.g. `~/code`).
- **`<agent-inbox>`** — your agent's inbox directory (e.g. `~/.claude/inbox` or
  `~/.pi/agent/inbox`).

## Skill index

| Skill | Role |
|-------|------|
| [bug](bug.md) | File a structured bug report |
| [choose-next](choose-next.md) | Pick the next batch from the roadmap |
| [dispatch-worker](dispatch-worker.md) | Spawn an isolated coding worker in a worktree |
| [session-end](session-end.md) | Wrap up and leave durable state/memory |
| [session-start-bugtriage](session-start-bugtriage.md) | Reproduce and shape bug reports |
| [session-start-cli](session-start-cli.md) | CLI/import agent orientation |
| [session-start-docs](session-start-docs.md) | Documentation/website agent orientation |
| [session-start-engine](session-start-engine.md) | Backend/engine agent orientation |
| [session-start-integrator](session-start-integrator.md) | Verify and prepare merges |
| [session-start-manager](session-start-manager.md) | Control-lane manager orientation |
| [session-start-milestone-worker](session-start-milestone-worker.md) | Autonomous multi-issue milestone worker |
| [session-start-planner](session-start-planner.md) | Feature/roadmap planning lane |
| [session-start-reviewer](session-start-reviewer.md) | Independent code review lane |
| [session-start-swiftui](session-start-swiftui.md) | SwiftUI/frontend agent orientation |
| [session-start-team](session-start-team.md) | Headless multi-agent team orchestration |
| [session-start-worker](session-start-worker.md) | Single-issue implementation worker |
| [status](status.md) | Quick project status summary |
