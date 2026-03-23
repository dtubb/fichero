# STATE.md — Fichero

Last updated: 2026-03-23 (session end)

## Current Branch

`main` — 14 commits ahead of origin (not pushed)

## Source of Truth

- Scope/status/priorities are on GitHub only:
  - Milestones: https://github.com/dtubb/fichero/milestones
  - Issues: https://github.com/dtubb/fichero/issues
  - Project: https://github.com/users/dtubb/projects/5
- Local `PLAN.md`/`TASKS.md` are pointer files only.

## Completed This Session

- Built full build/release pipeline: 9 scripts in `scripts/`
- Created Eleventy site with home page and FAQ (`site/`)
- Added AppInstaller (move-to-Applications prompt)
- Replaced app icon with card-file cabinet
- Added backend icon (gears) for Briefcase build
- Disabled app sandbox for DMG distribution
- Fixed Briefcase to use Python 3.13 via `.briefcase-venv`
- Switched to `briefcase package` (single command, matching original flow)
- Slimmed Briefcase bundle: split deps into core vs dev extras
- Styled installer DMG (app + Applications symlink, volume icon)
- Created skills: `/fichero-build`, `/fichero-release-prep`, `/fichero-release`
- Removed dev instructions from BackendConnectionView and ContentView
- Migrated bundle identifier: `ca.tubb` → `com.tubb` across 128 files
- Rebuilt `.venv` with Python 3.14 + all deps

## Blocked

- **Developer ID Application certificate** — needed for notarization. Daniel needs to create one in Apple Developer portal.
- **Notarytool credentials** — `xcrun notarytool store-credentials "notarytool"` not yet configured.
- **Sparkle key pair** — not yet generated for release signing.

## Not Pushed

14 commits on main are not pushed to origin. Daniel should review and push.

## Next Session — Start Here

1. Push the 14 commits on main (or review first).
2. Set up Developer ID Application certificate + notarytool credentials for notarization.
3. Run `/fichero-release-prep` to produce a full release candidate.
4. Test: install from DMG → move to Applications → backend starts → health check passes.
5. Consider data migration for existing `~/Library/Application Support/ca.tubb.fichero/` if any data exists there.
