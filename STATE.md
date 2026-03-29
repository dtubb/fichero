# STATE.md — Fichero

Last updated: 2026-03-29

## Current Branch

`main` — 0.0.1 release/integration worktree.

## Source of Truth

- GitHub Issues + Milestones: https://github.com/dtubb/fichero/milestones
- Project board: https://github.com/users/dtubb/projects/5

## This Week's Focus

- Ship the `0.0.1 - Core Library` milestone from `main`
- Keep all `0.0.2` planning and prototype work in `~/code/fichero-0.0.2` only
- Continue narrowing the release surface to what is stable and testable

## In Progress

- `main` already includes the integrated 0.0.1 branch work from `#317`, `#340`, `#344`, `#345`, and `#346`
- Open 0.0.1 issues now include `#313`, `#320`, `#326`, `#330`, `#341`, `#349`, `#353`, `#354`, `#355`, `#359`, and `#360`
- `~/code/fichero-0.0.2` is the separate worktree for search + semantic layer planning on `codex/0.0.2-planning`
- 0.0.2 plan now includes componentized slices (A-G), explicit undo/snapshot baseline, and 0.0.3/0.1.0 split in `docs/0.0.2-planning/PLAN.md`

## Blocked

- Developer ID Application certificate (notarization)
- Notarytool credentials
- Sparkle key pair

## Next Session — Start Here

1. Stay on `main` in `~/code/fichero` for `0.0.1` release work only.
2. Continue the `0.0.1` issue queue, especially `#313`, `#320`, `#326`, `#353`, `#354`, `#355`, `#359`, and `#360`.
3. Treat Folder Watchers `#359` and XMP sidecars `#360` as 0.0.1 scope discussions.
4. Do not move `0.0.2` planning docs or semantic-layer prototype work back into this worktree; use `~/code/fichero-0.0.2/docs/0.0.2-planning/PLAN.md` there.
5. Remember that `ruff` still fails on pre-existing backend lint issues and `pytest` is missing from the current environment.
