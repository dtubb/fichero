# Contributing

Fichero uses a worktree-based agent workflow. Start with the repo guidance in
[AGENTS.md](AGENTS.md), then use the folder-specific guidance in
[fichero/AGENTS.md](fichero/AGENTS.md) and [fichero-engine/AGENTS.md](fichero-engine/AGENTS.md).

## Workflow

- Claim the issue before editing (`/claim-task <N>` or `gh issue edit <N> --add-assignee @me --add-label "status:in-progress"`).
- Work on the current milestone branch in the assigned worktree; do not create per-task branches.
- Keep changes small and scoped to the issue.
- Worker lanes verify only the touched area:
  - backend: `ruff check` plus focused `pytest`
  - Swift: `swiftlint lint`
- If you change the backend API or schema, sync the generated OpenAPI/client artifacts in the same change.
- Do not edit generated files by hand.

## More Detail

For the fuller repo conventions, see [site/docs/developer/setup-and-contributing.md](site/docs/developer/setup-and-contributing.md).
