# Docs lane worker report — Docs Review batch (milestone #108)

Worker: Claude, in worktree `~/code/fichero-worktrees/ms-docs`, branch `lane/docs`.
Reset to `origin/main` at start (prior lane work already merged). All commits
authored as Claude, Co-Authored-By Daniel. Nothing pushed; the manager merges.

## Issues picked

From `Docs Review` (milestone #108) open issues, I took 4 actionable content
reviews and skipped the two that belong elsewhere:

| issue | title | status |
|---|---|---|
| #2689 | Review: public site — User Guide | DONE |
| #2691 | Review: public site — API Reference page | DONE |
| #2688 | Review: public site landing + FAQ copy | DONE |
| #2686 | Review: README.md — using-the-app framing | DONE |
| #2687 | Review: governance docs (CONSTITUTION/AGENTS/USER) | SKIPPED — owned by the review lane per PLAN-GOVERNANCE |
| #2690 | Review: Developer docs + How It's Built | NOT TAKEN this batch (capacity); no blocker |

## What changed

### #2689 — User Guide voice
`docs/user/interface-tour.md` used the `**Label** — text` definition pattern (29
em dashes). The project voice avoids em dashes; converted all to `**Label**: text`
with no wording change. Verified the rest of the user guide carries no stale
platform/provider language (no tvOS/visionOS/web-client, no LiteLLM-routing or
Ollama-only claims).

### #2691 — API Reference page
The unstable-API warning banner is present and accurate. Reworded the static-render
note to drop the `X, not Y` contrast: it now states the static render, then points
positively at the live local Swagger/redoc docs.

### #2688 — landing + FAQ
The landing copy (`docs/index.md`) and FAQ are already final (Daniel's salvaged
words). The one real defect: the landing's "Full changelog" link pointed at
`CHANGELOG.md`, which was folded into `RELEASE_NOTES.md` and removed, so it 404'd.
Repointed it to `RELEASE_NOTES.md` on GitHub. The version string stays a per-release
placeholder by design. FAQ has no placeholders or em dashes.

### #2686 — README using-the-app framing
Reframed without rewriting: kept the intro (what Fichero is), added an
**Installing and using Fichero** section near the top (download for macOS,
requirements, open and import, links into the user manual; iPad/iPhone noted as in
progress), and demoted the build-from-source steps under **Building from source
(for developers)** with a pointer back to the install section. Removed all 10 em
dashes. Fixed the stale `docs/agent-workflow/` path in Project Structure (origin/main
moved it to `agent-work/`).

## Gate results

- Changes are docs/Markdown only; no `.py` or `.swift` touched, so no ruff/pytest
  needed.
- `~/.venv/bin/mkdocs build --strict` exits **0** after every commit.
- Voice: no em dashes and no `not-X-but-Y` introduced; existing em dashes in the
  touched files removed.

## Commits (newest first)

- `docs: reframe README around using the app (#2686)`
- `docs: fix stale changelog link on landing page (#2688)`
- `docs: tighten API reference note voice (#2691)`
- `docs: remove em-dashes from user-guide interface tour (#2689)`
