# STATE — overnight handoff 2026-06-14 (late)

Branch `0.0.2`, tracking `origin/0.0.2`. Keep `0.0.2 == origin` (gate before every push).

## ⛔ Do NOT touch overnight
- **Port `:8765` and the ICANH libraries** — Daniel is running his OWN backend and testing
  `ICANH-Clean.fichero` himself. No CLI transcribe/import/export, no backend on 8765.
- Mac / SwiftUI / Xcode (no-xcodebuild-on-Daniel's-machine rule — launches GUI windows).
- Held worktrees `entitytable-2020` (#2020), `lan-tls-2157` (#2157); `.claude/worktrees/agent-aaf4fec2eced9c821`.

## Current Focus — overnight autonomous BACKEND milestone work
Work backend milestones via Claude workers in external worktrees (`~/code/fichero-worktrees/`),
3–10 issues per batch, gate+merge in batches (don't over-verify — it's slow). Priority order:
1. **#2222 (TOP)** — Transcribe *cloud* path saves combined transcript to the PARENT PDF, not
   page children. Fix: cloud/Gemini transcribe must OCR each page image separately and write
   each page's text to its page child (build `per_page_texts` for the single-call path, like
   #2215 did for the Apple/LLM path). Add a unit test asserting per-page page_content. No live
   backend needed to gate (mock vision). Daniel re-tests live in the morning.
2. **Observable Data Layer** (4 open, 77% done) — nearly complete, backend-safe.
3. **AI Infrastructure** (4 open, 82% done) — nearly complete.
4. **Remote & Self-Hosting** (16 open) — engine-remote / storage-HTTP / configurable host (backend).
5. **Developer Experience** (27 open) — docs + tooling (verify_all, sync_openapi, gates, CI).

## In Progress
- tmux lanes `f_importer_fixes` (worktree `importer-fixes`, branch `ms/importer-fixes`) and
  `f_icanh_cli` (stood down). importer-fixes was told to fix #2222 — verify it has the
  CORRECTED diagnosis (cloud path per-page, not "vision never runs").
- Uncommitted OpenAPI surface regen on `0.0.2` (5 files) committed at this session-end.

## Next Session — Start Here
1. `git status`, `git worktree list`, `tmux ls`. Confirm NOT on :8765; don't touch ICANH libs.
2. Drive the overnight loop: `/choose-next` → `/dispatch-worker` (Claude sonnet default, opus
   for hard like #2222), 3–10 issues/batch, gate with full unit suite only after a risky/DB/
   god-node batch (focused checks fine for docs/small slices), cherry-pick to 0.0.2, push if green.
3. #2222 fix is gateable via unit test (per-page page_content) — do NOT run live transcribe.
4. Read MEMORY.md "Live transcription gotchas": transcribe ~420s/page, restart backend after
   merges (reload unreliable), tmux multi-line needs a 2nd Enter, verify DB yourself.
