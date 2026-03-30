# STATE.md — Fichero

Last updated: 2026-03-30

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

- Ongoing 0.0.1 hardening across SwiftUI + backend: feature-gating alignment, persistence behavior cleanup, workflow reliability, and provider/model settings UX
- Backend runtime consistency work in progress: Python 3.12 alignment across envs, Briefcase dev hot-reload behavior, and dependency parity
- Active bug loop includes sidebar/inspector state persistence, workflow selection behavior, and log/runtime noise reduction

## Blocked

- Developer ID Application certificate (notarization)
- Notarytool credentials
- Sparkle key pair

## Next Session — Start Here

1. Verify runtime behavior after latest gating fixes: confirm SwiftUI no longer calls gated `/api/chains`, `/api/triggers`, `/api/schedules` when those features are off.
2. Rebuild Briefcase dev runtime and re-check workflow runs for `PIL` import success from declared deps (not manual env drift).
3. Continue 0.0.1 bug pass with manual checklist in `docs/qa/0.0.1-manual-qa-checklist.md`, prioritizing drag/drop, image import, window-state persistence, and workflow execution on folders/selections.
4. Keep `main` focused on 0.0.1 stabilization only; do not pull 0.0.2 planning artifacts into this worktree.
5. Before any release-ready checkpoint, run SwiftLint + xcodebuild + backend tests/lint and capture remaining blockers explicitly.
