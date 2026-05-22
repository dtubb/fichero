# STATE.md — Fichero

## Snapshot

**Branch: 0.0.2** · Clean working tree, fixes committed and pushed.

## CRITICAL BLOCKER

**App crashes on sidebar drag operations** — Issue #713 (sidebar drag asymmetry) causing `NSGenericException: Update Constraints in Window pass` crash. The `containerToPush is nil` drag session leaves the app unstable.

## Completed This Session

**Two issues fixed and closed:**

1. **#1150** - CLI `entity top` table view showed `(missing)` — Fixed by adding `render_top_entity()` formatter that matches `TopEntityRow` fields.
   - Commit: `58010218`
   - Files: `fichero/cli/formatters.py`, `__main__.py`, `test_cli_commands.py`

2. **#1142** - Security: Upgraded liquidjs to >=10.25.7 for CVE-2026-41311 circular block DoS vulnerability.
   - Commit: `d97608ab`
   - Files: `site/package.json`, `site/package-lock.json`

## Next Session — Start Here

1. **Run `/session-start` script** to load context files (SOUL.md → MEMORY.md → STATE.md).
2. **Decide direction:**
   - **Vision roadmap** — Issues #1156-1161 created but blocked with `needs-design` label.
   - **#713** (sidebar drag crash) — requires NSOutlineView wrapper for proper fix.
3. **ACTIVE THREAD — verification gate complete.** `scripts/verify_python.sh` returns ALL PASS. Swift build + 245 tests pass.
4. **Gotchas:** SwiftLint config updated for current project paths.

## Blocked

- **#713** (sidebar drag crash) — requires NSOutlineView wrapper (0.0.3-class change).
- **#1054** (search relevance threshold) — pending.
- **#183** Phase H end-to-end test on LFH_AHJM folder — pending.
- **Vision issues blocked** — #1156-1161 created but require specs and design before workers can build (labeled `needs-design`).