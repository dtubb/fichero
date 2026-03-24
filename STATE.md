# STATE.md — Fichero

Last updated: 2026-03-24

## Current Branch

`main` — clean. 8 feature branches with PRs awaiting review.

## Source of Truth

- GitHub Issues + Milestones: https://github.com/dtubb/fichero/milestones
- Project board: https://github.com/users/dtubb/projects/5

## Completed This Session (2026-03-24)

- **PR #329** — #314: Table Size column shows actual file size (ByteCountFormatter)
- **PR #331** — #315: Replace print() error logging with ErrorService in LibraryView
- **PR #333** — #332: Enable AI Providers & Models menu item for 0.0.1
- **PR #334** — #313: Add connection error banner to Library view
- **PR #335** — #322: Center image using frame expansion instead of contentInsets
- **PR #336** — #324: Add font, line spacing, and margin settings with reset
- **PR #337** — #327: Show folder contents grid in preview pane
- **PR #338** — #330: Fix icon view default scale + preview pane on launch

## Blocked

- Developer ID Application certificate (notarization)
- Notarytool credentials
- Sparkle key pair

## Recent PRs (all awaiting review)

- PR #329 (#314), PR #331 (#315), PR #333 (#332), PR #334 (#313)
- PR #335 (#322), PR #336 (#324), PR #337 (#327), PR #338 (#330)

## Next Session — Start Here

1. **Review and merge PRs** — 8 PRs awaiting Daniel's review. Merge approved ones to main.
2. **#326** — Keyboard shortcuts: verify all navigation shortcuts work end-to-end (needs app running).
3. **#317** — Document viewer: existing worktree at `fichero-issue-317`. Assess if #322 PR resolves this too.
4. **#320** — Bundle identifier migration: low priority, needs human oversight for keychain migration.
5. **Wire font settings** — PR #336 adds the settings UI; a follow-up wires them to EditorView.
