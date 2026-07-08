# agents/

The agent harness that builds Fichero — the skills and prompts behind the
**manager-with-workers loop** described in [../AGENTS.md](../AGENTS.md). This is
operational tooling, not product code or user documentation.

## Layout

- **`skills/`** — invocable agent skills, each a `SKILL.md` the agent loads on demand.

  *Manager lane* (coordinates; writes no product code):
  - `session-start-manager` — control-lane session start.
  - `choose-next` — pick the next batch from the roadmap priority spine.
  - `dispatch-worker` — spin up a worker in its own worktree/tmux window.
  - `gardener-agent` — deterministic verify + guardrail + roadmap triage.
  - `fichero-test` — run the `verify_all` gate at the right tier and file failures.
  - `fichero-release` — build, notarize, and ship (wraps `scripts/release-all.sh`).

  *Worker lane* (implements one thing at a time, commit-only):
  - `session-start-worker` — the shared worker contract.
  - `session-start-worker-docs` / `-tester` / `-release` — specializations. Each
    narrows `session-start-worker` to one lane's files, gates, and hard rules, so a
    worker configures itself instead of being hand-seeded each time.
  - `session-end` — session wrap-up.

  *Any lane, mid-session:*
  - `bug` — file something that is broken.
  - `feature` — file a capability that does not exist yet.

  Both file through `scripts/file_issue.sh`, never raw `gh issue create`.

- **`prompts/`** — paste-into-tmux templates, not skills: `worker-loop.md` (the
  standing contract for a worker draining a whole milestone) and `manager-loop.md`
  (the manager's cadence). They stay here rather than under `skills/` because
  `../AGENTS.md` dispatches by pasting them, and a skill is something an agent
  *loads*, not something a human pastes.
- **`ROADMAP.md`** — the `## Tier` priority spine. Read by path by
  `scripts/choose_next.py` (`DEFAULT_ROADMAP`) and `scripts/gardener.py`
  (`ROADMAP_PATH`). It lives here, not in `docs/`, because it is agent/manager
  planning: every `.md` under `docs/` is published as a public page.

## Where the coding standards live

Not here. `agents/skills/_shared/` used to hold copies; nothing loaded them and they
had decayed into describing directories that no longer exist. The maintained
standards are in the contributor manual:

- [`docs/contributor/swiftui-principles.md`](../docs/contributor/swiftui-principles.md)
- [`docs/contributor/swiftui-development-standards.md`](../docs/contributor/swiftui-development-standards.md)
- [`docs/contributor/backend-development-standards.md`](../docs/contributor/backend-development-standards.md)
- [`docs/contributor/architecture-overview.md`](../docs/contributor/architecture-overview.md)

The hard rules an agent must not break are in [`../AGENTS.md`](../AGENTS.md).

## How it fits together

The **manager** triages GitHub issues, picks the next batch, and dispatches it to
**workers** that grind in isolated worktrees and commit as themselves. The manager
reviews, build-gates, runs `verify_all`, merges via PR, and re-dispatches. See
[../AGENTS.md](../AGENTS.md) for the full operational manual and hard rules.
