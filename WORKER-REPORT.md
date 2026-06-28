# Docs lane worker report — Docs Review batch 2 (milestone #108)

Worker: Claude, in worktree `~/code/fichero-worktrees/ms-docs`, branch `lane/docs`.
Reset to `origin/main` at start. All commits authored as Claude, Co-Authored-By
Daniel. Nothing pushed; the manager merges.

## Milestone state (important)

All 6 issues in `Docs Review` (#108) still show OPEN, but **4 are already
implemented and merged** into `origin/main` from my previous batch; the manager
merged the work without closing the issues. Verified present in the current tree:

| issue | state |
|---|---|
| #2686 README using-the-app framing | DONE (merged, not closed) |
| #2688 landing + FAQ copy | DONE (merged, not closed) |
| #2689 User Guide voice | DONE (merged, not closed) |
| #2691 API Reference page | DONE (merged, not closed) |

Those four can be closed. The two with genuine remaining defects, which I fixed
this batch:

| issue | title | status |
|---|---|---|
| #2690 | Developer docs + 'How It's Built' | DONE this batch |
| #2687 | Governance docs (CONSTITUTION / AGENTS / USER) | DONE this batch |

After this batch the milestone is effectively drained of fresh implementation
work.

## What changed

### #2690 — Developer docs + How It's Built
The published `docs/how-its-built.md` referenced `docs/agent-workflow/` six times,
but origin/main relocated that folder to `agent-work/agent-workflow/`, so every
reference was stale. Repointed all six, and swept the same broken path in the two
internal sibling docs (`docs/CLAUDE.md`, `docs/architecture/swiftui/workflow_checklist.md`).

Accuracy review: the developer docs carry no stale platform/provider language (no
tvOS/visionOS/web-client, no LiteLLM-routing or Ollama-only claims). Voice: the
curated developer-guide pages (`contributor/README`, `architecture-overview`,
`action-registry`, `security-model`, `setup-and-contributing`, etc.) use no em
dashes. The four dense engineering-reference docs (`swiftui-principles`,
`appkit-interop`, `swiftui-development-standards`, `backend-development-standards`)
do use em dashes, including inside code-block comments. I deliberately did NOT
blanket-sweep those: a mechanical em-dash removal across deep technical reference
risks corrupting code comments and is over-reach for established engineering style.
Flagged for Daniel if he wants the voice rule extended there.

### #2687 — Governance docs
`CONSTITUTION.md` listed `docs/agent-workflow/ notes` as a non-source-of-truth
planning location; that folder moved to `agent-work/agent-workflow/`. Repointed it.
The governance docs are otherwise accurate with no stale platform/provider claims;
`CONSTITUTION.md` and `USER.md` use no em dashes. `AGENTS.md` keeps its established
operational-manual style (27 em dashes left intact, same rationale as above).

## Gate results

- Changes are docs/Markdown only; no `.py` or `.swift` touched, so no ruff/pytest
  needed.
- `~/.venv/bin/mkdocs build --strict` exits **0** after every commit.
- No em dashes or `not-X-but-Y` introduced.

## Commits (newest first)

- `docs: fix stale agent-workflow path in CONSTITUTION (#2687)`
- `docs: fix stale agent-workflow paths in How It's Built (#2690)`
