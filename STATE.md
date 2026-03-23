# STATE.md — Fichero

Last updated: 2026-03-23 (session end, second update)

## Current Branch

`main` — 15 commits ahead of origin (not pushed)

## Source of Truth

- Scope/status/priorities are on GitHub only:
  - Milestones: https://github.com/dtubb/fichero/milestones
  - Issues: https://github.com/dtubb/fichero/issues
  - Project: https://github.com/users/dtubb/projects/5
- Local `PLAN.md`/`TASKS.md` are pointer files only.

## Completed This Session

- Full build/release pipeline (9 scripts, 3 skills, Eleventy site)
- AppInstaller (move-to-Applications), card-file icon, sandbox disabled
- Briefcase backend working with Python 3.13, slim deps, `briefcase package`
- Styled installer DMG (app + Applications symlink)
- Bundle ID migration: `ca.tubb` → `com.tubb` (128 files)
- Removed dev instructions from backend connection views

## Blocked

- Developer ID Application certificate — needed for notarization
- Notarytool credentials — not configured
- Sparkle key pair — not generated

## Next Session — Start Here

1. **Enable 0.0.1 sidebar modes**: Update `FeatureManager.swift` to enable Workflows and Activity alongside Library and Search.
2. **Enable workflow tools**: Ensure transcribe, named entity recognition, and catalogue tools are registered and available in the release tier.
3. **Backend feature tier**: Verify `release` tier includes workflow routes (currently may be gated to `dev` only).
4. **Fix document viewer**: Image not centered (left-aligned), scrollbars overlay image instead of container edge, background should be Preview-style gray, default zoom should fit-to-window (not 100%). Affects image viewer at all zoom levels.
5. Push the 16 commits on main after review.
