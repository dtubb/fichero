# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — Catalogue workflow complete; shippable pending Xcode smoke test + search decision.

**Goal:** Ship 0.0.2 with Transcribe + Catalogue + reliability fixes.

## Open Issues (0.0.2 milestone)

| # | Title | Status |
|---|---|---|
| #661 | Fichero download page on tubb.ca | Ready to do |
| #662 | tubb.ca/fichero release notes + download | Ready to do |
| #658 | fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build + sign + notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool creds |
| #660 | Dry-run install 0.0.2 on Daniel's machine | Blocked on #659 |
| #665 | Dev blog post — 3 years AI coding | Content filing only |

## Next Session — Start Here

1. **Xcode build + smoke-test Catalogue.** Right-click a folder → Run Workflow → Catalogue. Confirm nine-section markdown appears in folder Content tab; per-section artifacts render in inspector; re-run skips transcribed files; editing text then re-running Catalogue preserves the edit.

2. **Decide search backport strategy.** 0.0.3 worktree has search work but also massive refactors (3762 insertions / 12846 deletions vs 0.0.2). Recommendation: lock down 0.0.2, ship, then finish search in the 0.0.3 worktree. If you want search in 0.0.2, cherry-pick commit-by-commit (risky).

3. **Release pipeline** if smoke-test passes — start with #661/#662 (site content, no blockers), then #658/#659 (DMG).

4. **Deferred to 0.0.3**: #670, #673, #674, #675, #680, #683, #684 (per-page PDF fan-out, inspector-refresh storms, signature hashing, metadata typing, first-class Aggregate node, visual fan-out markers, chained per-file steps).

---

*Last updated: 2026-04-23* — session-end after autonomous catalogue build-out.
