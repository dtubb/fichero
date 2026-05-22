# STATE.md — Fichero

## Snapshot

**Branch: 0.0.2** · Session-end notes are uncommitted; code branch was otherwise clean and pushed.

## CRITICAL BLOCKER

**App crashes on sidebar drag operations** — Issue #713 (sidebar drag asymmetry) causing `NSGenericException: Update Constraints in Window pass` crash. The `containerToPush is nil` drag session leaves the app unstable.

## Current Focus

Autoloop repair and current-release bug triage. Daniel's priority is **#1166** (Catalogue workflow fails: Extract All Entities returns "No text input").

## In Progress

- **Autoloop runner fixes** are implemented in `~/code/autoloop` but uncommitted there:
  - `agent-autonomous-loop.py`
  - `bin/cascade_loop.py`
  - `bin/cascade_router.py`
- **#958** remains `in_progress` in `agent-work/queue.md` from a prior loop.
- **#714** remains pending after the paused test run.

## Next Session — Start Here

1. **Run `/session-start` script** to load context files (SOUL.md → MEMORY.md → STATE.md).
2. **Restart Codex** so newly symlinked skills (`bug`, `feature`, `feature-future`, `autonomous-loop`, `extract-bib`) appear in the automatic skill list.
3. **Finish autoloop verification:** inspect and commit `~/code/autoloop` changes, then run a 2-iteration loop with `#1166` first in the queue.
4. **Prioritize #1166** before older queue items; newly filed current bugs/features are #1162-#1168.
5. **ACTIVE THREAD — verification gate complete.** `scripts/verify_python.sh` returns ALL PASS. Swift build + 245 tests pass.

## Blocked

- **#713** (sidebar drag crash) — requires NSOutlineView wrapper (0.0.3-class change).
- **#1166** (Catalogue workflow "No text input") — Daniel's current priority.
- **#1167** (artifact inspector CancellationError) — filed from rapid PDF page switching.
- **#1054** (search relevance threshold) — pending.
- **#183** Phase H end-to-end test on LFH_AHJM folder — pending.
- **Vision issues blocked** — #1156-1161 created but require specs and design before workers can build (labeled `needs-design`).
