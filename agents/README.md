# agents/

The agent harness that builds Fichero — the skills and prompts behind the
**manager-with-workers loop** described in [../AGENTS.md](../AGENTS.md). This is
operational tooling, not product code or user documentation.

## Layout

- **`skills/`** — invocable agent skills, each a `SKILL.md` the agent loads on
  demand:
  - `session-start-manager` / `session-start-worker` / `session-end` — session lifecycle.
  - `choose-next` — pick the next work from the roadmap priority spine.
  - `dispatch-worker` — spin up a worker in its own worktree/tmux window.
  - `gardener-agent` — repo/issue tidying (see `scripts/gardener.py`).
  - `fichero-build` / `fichero-release-prep` / `fichero-release` — build, prep, and ship.
  - `bug` — file a bug as a GitHub issue mid-session.
  - `_shared` — principles shared across skills.
- **`prompts/`** — reusable prompt fragments the skills compose (`manager-loop.md`,
  `worker-loop.md`).

## How it fits together

The **manager** triages GitHub issues, picks the next batch, and dispatches it to
**workers** that grind in isolated worktrees and commit as themselves. The manager
reviews, build-gates, runs `verify_all`, merges via PR, and re-dispatches. See
[../AGENTS.md](../AGENTS.md) for the full operational manual and hard rules.
