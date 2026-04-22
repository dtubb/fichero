# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — All code tasks done. Working through release pipeline.

**Goal:** Build + notarize 0.0.2 DMG → dry-run install on Daniel's machine → set up fichero-releases repo → push to site → merge to main → start 0.0.3.

## Open Issues (0.0.2 milestone)

| # | Title | Status |
|---|---|---|
| #658 | Set up fichero-releases GitHub repo | Next: needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool credentials |
| #660 | Dry-run: install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Can do now (page content ready in site/) |
| #662 | Update tubb.ca/fichero with release notes + download | Can do now (draft in site/src/apps/fichero/index.md) |
| #665 | Dev blog post: 3 years of AI-assisted coding | Content filing only — write when ready |

## Moved to 0.0.3
- #619 / #605 — startup/backend perf (need on-device Instruments)
- #520 — Sparkle auto-update (needs Apple cert + feed URL)

## Next Session — Start Here

1. **#661/#662**: Push updated site content (site/src/apps/fichero/index.md already drafted). Commit + push.
2. **#658**: Daniel creates `fichero-releases` public GitHub repo (Claude can do the rest once it exists).
3. **#659**: Xcode Archive → `xcodebuild -exportArchive` → notarytool → staple → create DMG. Ask Daniel for Apple ID + app-specific password for notarytool.
4. **#660**: Install DMG on Daniel's machine, confirm app launches and connects to backend.
5. When Daniel is happy: `git checkout main && git merge 0.0.2 && git push` — create PR for audit trail.
6. Then fetch + merge main into 0.0.3 worktree to start 0.0.3 with full 0.0.2 history.

---

*Last updated: 2026-04-22* — All code tasks closed (#644 #650 #651 #653). Release pipeline next.
