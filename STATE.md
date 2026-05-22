# STATE.md — Fichero

## Snapshot

**Branch: 0.0.2** · Clean working tree, verification-gate fixes committed.

## CRITICAL BLOCKER

**App crashes on sidebar drag operations** — Issue #713 (sidebar drag asymmetry) causing `NSGenericException: Update Constraints in Window pass` crash. The `containerToPush is nil` drag session leaves the app unstable.

## Next Session — Start Here

1. **Run `/session-start` script** to load context files (SOUL.md → MEMORY.md → STATE.md).
2. **Decide direction:**
   - **Continue autoloop** — `~/code/autoloop/bin/worker-loop.sh ~/code/fichero-0.0.2 3` on fresh `agent-work/queue.md`.
   - **Fix autoloop timeout** — workers timeout before commits (60s default). Consider `cascade_loop.py --timeout 7200`.
   - **Vision roadmap** — Issues #1156-1161 created but blocked with `needs-design` label.
3. **ACTIVE THREAD — verification gate complete.** `scripts/verify_python.sh` returns ALL PASS. Swift build + 245 tests pass.
4. **Gotchas:** SwiftLint config updated for current project paths; workers execute tools but need more time per issue.

## Blocked

- **#713** (sidebar drag crash) — `containerToPush is nil` causing AppKit constraint loop crash. Drag from sidebar rows causes app termination. Workaround: drag only from row whitespace (works). Full fix: NSOutlineView wrapper (0.0.3-class change).
- **#1054** (search relevance threshold) — pending, returns every page; needs scoring cutoff.
- **#183** Phase H end-to-end test on LFH_AHJM folder — pending.
- **Vision issues blocked** — #1156-1161 created but require specs and design before free workers can build (labeled `needs-design`).