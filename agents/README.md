# agents/

The agent harness that builds Fichero — the skills and prompts behind the
**manager-with-workers loop** described in [../AGENTS.md](../AGENTS.md). This is
operational tooling, not product code or user documentation.

## Layout

- **`skills/`** — invocable agent skills, each a `SKILL.md` the agent loads on
  demand:
  - `session-start-manager` / `session-start-worker` / `session-end` — session lifecycle.
  - `session-start-worker-docs` / `-tester` / `-release` — specialized workers. Each
    narrows `session-start-worker` to one lane's files, gates, and hard rules, so a
    worker configures itself instead of being hand-seeded each time.
  - `choose-next` — pick the next work from the roadmap priority spine.
  - `dispatch-worker` — spin up a worker in its own worktree/tmux window.
  - `gardener-agent` — repo/issue tidying (see `scripts/gardener.py`).
  - `fichero-test` — run the `verify_all` gate at the right tier and file failures.
  - `fichero-release` — build, notarize, and ship (wraps `scripts/release-all.sh`).
  - `bug` — file a bug as a GitHub issue mid-session.
  - `_shared` — principles shared across skills.
- **`prompts/`** — reusable prompt fragments the skills compose (`manager-loop.md`,
  `worker-loop.md`).

## How it fits together

The **manager** triages GitHub issues, picks the next batch, and dispatches it to
**workers** that grind in isolated worktrees and commit as themselves. The manager
reviews, build-gates, runs `verify_all`, merges via PR, and re-dispatches. See
[../AGENTS.md](../AGENTS.md) for the full operational manual and hard rules.
